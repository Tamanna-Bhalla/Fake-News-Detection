import os
import sys
import structlog
from typing import Optional, Any

# Add research package to Python path so backend can import text_verification.
_research_path = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "research", "research"
)
sys.path.insert(0, os.path.abspath(_research_path))

logger = structlog.get_logger(__name__)

# We use a try-except block for the import. 
# If the 'research' folder isn't on your local machine, the server still boots,
# setting pipeline_ready to False so the frontend knows the AI is down.
try:
    from text_verification.pipeline.verify_pipeline import VerificationPipeline
    MODEL_AVAILABLE = True
except ImportError:
    MODEL_AVAILABLE = False
    logger.warning("text_verification_module_not_found", detail="Running without AI model.")

import asyncio
from app.services.image_service import get_image_detector, ImageManipulationDetector

# Module-level singletons and thread-safe lock
_pipeline: Optional[Any] = None
pipeline_ready: bool = False
_image_detector: Optional[Any] = None
image_detector_ready: bool = False
_init_lock = asyncio.Lock()
# Bounded semaphore to prevent concurrent TensorFlow inference memory and CPU exhaustion
image_inference_semaphore = asyncio.Semaphore(2)

async def init_pipeline() -> None:
    """
    Initializes the AI pipeline once at app startup.
    If it fails (e.g., missing API keys, or missing module), we catch the error 
    so the server doesn't crash, allowing the /health endpoint to report the failure.
    """
    global _pipeline, pipeline_ready
    
    if not MODEL_AVAILABLE:
        _pipeline = None
        pipeline_ready = False
        logger.error("pipeline_initialization_failed", error="text_verification module is missing from Python path")
        return

    try:
        loop = asyncio.get_event_loop()
        logger.info("initializing_pipeline")
        _pipeline = await loop.run_in_executor(
            None,
            VerificationPipeline
        )
        # Prewarm the embedding model so verification requests respond instantly
        await loop.run_in_executor(
            None,
            lambda: _pipeline.verdict_generator.embedding_model
        )
        pipeline_ready = True
        logger.info("pipeline_initialized_successfully")
    except Exception as e:
        _pipeline = None
        pipeline_ready = False
        logger.error("pipeline_initialization_failed", error=str(e))

async def init_image_detector_service() -> None:
    """Initializes the image manipulation detector and pre-loads Keras model once at startup."""
    global _image_detector, image_detector_ready
    try:
        loop = asyncio.get_event_loop()
        logger.info("initializing_image_detector")
        _image_detector = await loop.run_in_executor(
            None,
            get_image_detector
        )
        image_detector_ready = _image_detector is not None and getattr(_image_detector, "model", None) is not None
        logger.info("image_detector_initialized", model_ready=image_detector_ready)
    except Exception as e:
        _image_detector = None
        image_detector_ready = False
        logger.error("image_detector_initialization_failed", error=str(e))

async def init_dependencies() -> None:
    """Run all dependency initializations in startup lifespan."""
    await asyncio.gather(
        init_pipeline(),
        init_image_detector_service(),
        return_exceptions=True
    )

def get_pipeline() -> Optional[Any]:
    """FastAPI dependency to inject the pipeline into our routes."""
    global _pipeline, pipeline_ready
    return _pipeline

def get_pipeline_status() -> bool:
    return _pipeline is not None and pipeline_ready

def get_image_service():
    """FastAPI dependency to get the image manipulation detector."""
    global _image_detector
    if _image_detector is None:
        _image_detector = get_image_detector()
    return _image_detector

def get_image_detector_status() -> bool:
    return _image_detector is not None and getattr(_image_detector, "model", None) is not None