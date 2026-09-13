from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
import structlog

from app.config import settings
from app.api.v1.router import api_router
from app.middleware.cors import add_cors_middleware
from app.middleware.logging_middleware import LoggingMiddleware
from app.utils.error_handlers import (
    validation_exception_handler,
    rate_limit_handler,
    http_exception_handler,
    global_exception_handler
)
from app.dependencies import init_dependencies, get_pipeline_status, get_image_detector_status
from app.api.v1.endpoints.health import probe_router


logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting DTI backend...", environment=settings.ENVIRONMENT)

    # 1. Enforce strict configuration rules in production
    settings.validate_production_settings()

    # Set transformer env vars before pipeline import
    import os
    os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
    os.environ.setdefault("USE_TF", "0")

    # 2. Preload both text and image models once at startup
    await init_dependencies()

    text_ready = get_pipeline_status()
    image_ready = get_image_detector_status()
    logger.info("subsystems_ready", text_pipeline=text_ready, image_detector=image_ready)

    yield

    logger.info("Shutting down DTI backend")


# Initialize the FastAPI application
app = FastAPI(
    title="DTI News Verifier API",
    description="API for the AI-powered news headline verification system",
    version="1.0.0",
    lifespan=lifespan
)

# 1. Register Middleware (Order matters: CORS should generally be first)
add_cors_middleware(app)
app.add_middleware(LoggingMiddleware)

# 2. Register Error Handlers
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)
app.add_exception_handler(Exception, global_exception_handler)


# 3. Mount Routers
app.include_router(probe_router)
app.include_router(api_router)



# 4. Entry point for running directly via Python
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app", 
        host=settings.HOST, 
        port=settings.PORT, 
        reload=settings.RELOAD
    )