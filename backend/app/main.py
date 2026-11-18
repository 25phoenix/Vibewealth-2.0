"""FastAPI application assembly."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.assistant_http import AssistantNoStoreMiddleware
from app.core.assistant_rate_limit import AssistantRateLimiter
from app.core.assistant_admission import AssistantAdmission
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
    application.state.assistant_rate_limiter = AssistantRateLimiter()
    application.state.assistant_admission = AssistantAdmission()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=configured_settings.allowed_frontend_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
        expose_headers=["Retry-After"],
        max_age=600,
    )
    application.add_middleware(AssistantNoStoreMiddleware)
    application.include_router(router)
    return application


app = create_app()
