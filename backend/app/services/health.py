"""System health checks. Business logic lives here, not in route handlers."""

import logging

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import Settings
from app.schemas.health import ComponentHealth, HealthResponse

log = logging.getLogger(__name__)


def check_database(session: Session) -> dict[str, ComponentHealth]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log.exception("Database health check failed")
        return {"database": ComponentHealth(status="down", detail="connection failed")}
    components = {"database": ComponentHealth(status="ok")}
    try:
        version = session.execute(text("SELECT postgis_version()")).scalar_one()
        components["postgis"] = ComponentHealth(status="ok", detail=str(version))
    except SQLAlchemyError:
        session.rollback()
        components["postgis"] = ComponentHealth(status="down", detail="extension unavailable")
    return components


def system_health(session: Session, settings: Settings) -> HealthResponse:
    components = check_database(session)
    statuses = {c.status for c in components.values()}
    overall = "ok" if statuses == {"ok"} else ("down" if "down" in statuses else "degraded")
    return HealthResponse(
        status=overall,
        version=__version__,
        environment=settings.environment,
        components=components,
    )
