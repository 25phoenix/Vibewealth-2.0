"""Centralized application settings."""

from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


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
    cors_origins: list[str] = ["http://localhost:5173"]

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


@lru_cache

def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()
