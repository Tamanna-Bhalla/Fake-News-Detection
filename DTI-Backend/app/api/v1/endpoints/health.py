from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from app.models.responses import HealthResponse
from app.dependencies import get_pipeline_status, get_image_detector_status
from app.config import settings

router = APIRouter()
probe_router = APIRouter()


@probe_router.get("/livez")
@router.get("/livez")
async def liveness_probe():
    """Liveness probe: verifies process is alive."""
    return {"status": "alive"}


@probe_router.get("/readyz")
@router.get("/readyz")
async def readiness_probe():
    """Readiness probe: verifies text pipeline and image model readiness."""
    text_ready = get_pipeline_status()
    image_ready = get_image_detector_status()
    # Ready if at least one engine is loaded and responsive
    is_ready = text_ready or image_ready

    body = {
        "status": "ready" if is_ready else "not_ready",
        "text_pipeline": "ready" if text_ready else "unavailable",
        "image_model": "ready" if image_ready else "unavailable",
        "environment": settings.ENVIRONMENT,
    }
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=status_code, content=body)


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Checks detailed status of all subsystems."""
    text_ready = get_pipeline_status()
    image_ready = get_image_detector_status()
    overall = "ok" if (text_ready and image_ready) else ("degraded" if (text_ready or image_ready) else "unavailable")

    return HealthResponse(
        status=overall,
        pipeline_ready=text_ready,
        version="1.0.0",
        text_pipeline="ready" if text_ready else "unavailable",
        image_model="ready" if image_ready else "unavailable",
        environment=settings.ENVIRONMENT,
    )