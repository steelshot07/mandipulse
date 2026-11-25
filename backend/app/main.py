"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    """Build the FastAPI app with CORS and all routers."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="MandiPulse API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app


app = create_app()
