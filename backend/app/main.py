from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.security import RateLimitMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="AeroSecurity AI",
        version=__version__,
        description="Monitor the skies. Detect anomalies. Investigate aviation intelligence.",
        docs_url=None if settings.environment == "production" else "/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute)
    register_error_handlers(app)
    app.include_router(api_router)

    @app.get("/healthz", tags=["system"], include_in_schema=False)
    def liveness() -> dict[str, str]:
        """Process liveness only; does not touch the database."""
        return {"status": "ok"}

    return app


app = create_app()
