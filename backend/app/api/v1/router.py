from fastapi import APIRouter

from app.api.v1 import (
    analytics,
    anomalies,
    assistant,
    aviation,
    data_sources,
    detection,
    intelligence,
    system,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(data_sources.router)
api_router.include_router(aviation.router)
api_router.include_router(analytics.router)
api_router.include_router(detection.router)
api_router.include_router(anomalies.router)
api_router.include_router(anomalies.emergency_router)
api_router.include_router(anomalies.investigation_router)
api_router.include_router(anomalies.auth_router)
api_router.include_router(intelligence.router)
api_router.include_router(intelligence.settings_router)
api_router.include_router(assistant.router)
api_router.include_router(assistant.intel_router)
