"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import data, health, status
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.security import RateLimiter, install_security


def create_app(limiter: RateLimiter | None = None) -> FastAPI:
    """Build the FastAPI app with CORS, security hardening and all routers."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="MandiPulse API", version="0.1.0")
    install_security(app, limiter or RateLimiter(settings.rate_limit_per_minute))
    # Added last so it is the outermost middleware and also covers 429 responses.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router)
    app.include_router(status.router)
    app.include_router(data.router)
    return app


app = create_app()
