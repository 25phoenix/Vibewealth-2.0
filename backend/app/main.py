"""FastAPI application assembly."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import Settings, get_settings
from app.core.database import dispose_engine, engine
from app.core.rate_limit import InMemoryAuthRateLimiter

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Dispose the SQLAlchemy connection pool during application shutdown."""

    try:
        yield
    finally:
        dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the API with validated security and browser-origin configuration."""

    configured_settings = settings or get_settings()
    if configured_settings.sqlalchemy_url != engine.url:
        raise ValueError("Application settings must match the configured database engine")

    application = FastAPI(
        title=configured_settings.app_title,
        version=configured_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = configured_settings
    application.state.auth_rate_limiter = InMemoryAuthRateLimiter()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured_settings.allowed_frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type", "X-CSRF-Token"],
        max_age=600,
    )
    application.include_router(router)
    return application


app = create_app()
