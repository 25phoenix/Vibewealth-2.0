"""Centralized application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from app.core.origins import normalize_origin

_DEVELOPMENT_CSRF_SECRET = "vibewealth-local-development-csrf-secret-rotate-for-production"


class Settings(BaseSettings):
    """Settings loaded from environment variables and an optional .env file."""

    app_title: str = "VibeWealth API"
    app_version: str = "0.1.0"
    database_url: SecretStr | None = None
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "vibewealth"
    postgres_user: str = "vibewealth_app"
    postgres_password: SecretStr | None = None
    app_environment: Literal["development", "test", "production"]
    allowed_frontend_origins: list[str] = ["http://localhost:5173"]
    allow_insecure_cookies: bool = False
    csrf_signing_secret: SecretStr | None = None
    auth_login_ip_limit: int = Field(default=30, ge=1, le=10000)
    auth_login_identity_limit: int = Field(default=5, ge=1, le=10000)
    auth_login_window_seconds: int = Field(default=60, ge=1, le=86400)
    auth_registration_ip_limit: int = Field(default=5, ge=1, le=10000)
    auth_registration_identity_limit: int = Field(default=2, ge=1, le=10000)
    auth_registration_window_seconds: int = Field(default=900, ge=1, le=86400)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: SecretStr | None) -> SecretStr | None:
        """Validate an explicitly configured SQLAlchemy URL without exposing it."""

        if value is None or not value.get_secret_value().strip():
            return None

        try:
            url = make_url(value.get_secret_value())
        except ArgumentError as error:
            raise ValueError("DATABASE_URL must be a valid SQLAlchemy URL") from error

        if url.drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use the postgresql+psycopg driver")
        if not url.host or not url.database:
            raise ValueError("DATABASE_URL must include a host and database name")

        return value

    @field_validator("allowed_frontend_origins")
    @classmethod
    def validate_allowed_frontend_origins(cls, values: list[str]) -> list[str]:
        """Reject wildcard or malformed origins and store canonical exact origins."""

        if not isinstance(values, list):
            raise ValueError("ALLOWED_FRONTEND_ORIGINS must be a list of origins")
        origins = [normalize_origin(value) for value in values]
        if len(set(origins)) != len(origins):
            raise ValueError("ALLOWED_FRONTEND_ORIGINS cannot contain duplicates")
        return origins

    @field_validator("csrf_signing_secret", mode="before")
    @classmethod
    def normalize_csrf_signing_secret(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, SecretStr):
            secret = value.get_secret_value()
        else:
            secret = value
        if not isinstance(secret, str) or len(secret) < 32:
            raise ValueError("CSRF_SIGNING_SECRET must contain at least 32 characters")
        return value

    @model_validator(mode="after")
    def validate_http_security_settings(self) -> "Settings":
        if self.allow_insecure_cookies and self.app_environment != "development":
            raise ValueError("Insecure authentication cookies are allowed only in development")

        if self.app_environment == "production":
            if any(not origin.startswith("https://") for origin in self.allowed_frontend_origins):
                raise ValueError("Production ALLOWED_FRONTEND_ORIGINS must use HTTPS")
            if (
                "allowed_frontend_origins" not in self.model_fields_set
                or not self.allowed_frontend_origins
            ):
                raise ValueError("Production requires explicit ALLOWED_FRONTEND_ORIGINS")
            if "csrf_signing_secret" not in self.model_fields_set:
                raise ValueError("Production requires an explicit CSRF_SIGNING_SECRET")
            if self.csrf_signing_secret is None:
                raise ValueError("Production requires an explicit CSRF_SIGNING_SECRET")
            if (
                self.csrf_signing_secret.get_secret_value()
                == _DEVELOPMENT_CSRF_SECRET
            ):
                raise ValueError("Production cannot use the development CSRF key")

        return self

    @property
    def sqlalchemy_url(self) -> URL:
        """Return the configured URL or safely build one from PostgreSQL fields."""

        if self.database_url is not None:
            database_url = self.database_url.get_secret_value().strip()
            if database_url:
                return make_url(database_url)

        password = (
            self.postgres_password.get_secret_value()
            if self.postgres_password is not None
            else None
        )
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )

    @property
    def auth_cookie_name(self) -> str:
        """Use the browser-enforced __Host- prefix in production."""

        if self.app_environment == "production":
            return "__Host-vibewealth_session"
        return "vibewealth_session"

    @property
    def auth_cookie_secure(self) -> bool:
        """Secure cookies are mandatory except for explicit local HTTP mode."""

        return self.app_environment == "production" or not self.allow_insecure_cookies

    @property
    def csrf_key(self) -> bytes:
        """Return configured CSRF key material, with a dev-only fallback."""

        if self.csrf_signing_secret is not None:
            secret = self.csrf_signing_secret.get_secret_value()
            if secret:
                return secret.encode("utf-8")
        if self.app_environment == "development":
            return _DEVELOPMENT_CSRF_SECRET.encode("utf-8")
        raise ValueError("CSRF_SIGNING_SECRET is required")


@lru_cache

def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()
