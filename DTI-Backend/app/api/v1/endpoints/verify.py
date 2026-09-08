import asyncio
import logging
from fastapi import APIRouter, Depends, Request, File, UploadFile, Form
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from typing import Optional

from app.config import settings
from app.models.requests import VerifyRequest
from app.models.responses import VerifyResponse, ImageVerificationResult
from app.dependencies import get_pipeline
from app.services.verification_service import run_verification
from app.services.image_service import get_image_detector

logger = logging.getLogger(__name__)
router = APIRouter()

# Setup rate limiter using the user's IP address
limiter = Limiter(key_func=get_remote_address)

@router.post("/verify", response_model=VerifyResponse)
@limiter.limit(settings.RATE_LIMIT)
async def verify_claim(
    request: Request,
    body: VerifyRequest,
    pipeline = Depends(get_pipeline)
):
    """
    Takes a news headline claim and passes it to the AI verification pipeline.
    """
    if not body.claim:
        return JSONResponse(
            status_code=400,
            content={"error": "missing_claim", "detail": "Either 'claim' must be provided."}
        )
    
    if pipeline is None:
        return JSONResponse(
            status_code=503,
            content={"error": "service_unavailable", "detail": "Verification service is not ready yet."}
        )
        
    try:
        raw_result = await run_verification(body.claim, pipeline=pipeline)
        return VerifyResponse(**raw_result)
        
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content={"error": "verification_timeout", "detail": "Verification timed out. Try a shorter claim."}
        )
        
    except RuntimeError:
        return JSONResponse(
            status_code=500,
            content={"error": "pipeline_error", "detail": "Verification failed due to an internal error."}
        )

    except Exception as exc:
        logger.exception("verify_claim failed")
        return JSONResponse(
            status_code=500,
            content={"error": "response_mapping_error", "detail": "Result could not be processed."}
        )


def _synthesize_joint_assessment(claim_verdict: Optional[str], image_result: ImageVerificationResult) -> str:
    """Generate a combined multimodal evaluation explaining how text veracity and image authenticity relate."""
    if not claim_verdict or image_result.is_fake is None:
        return "Individual assessment available."

    norm_verdict = claim_verdict.strip()
    is_image_fake = bool(image_result.is_fake)
    image_verdict_str = image_result.verdict or ("Manipulated" if is_image_fake else "Authentic")

    if norm_verdict in ("True", "TRUE"):
        if is_image_fake:
            return (
                "The textual claim appears factually supported by sources; however, the attached image "
                f"exhibits evidence of digital tampering ({image_verdict_str}). Exercise caution: the image "
                "may be an illustrative composite, modified graphic, or out-of-context edit."
            )
        else:
            return "Both the textual claim and the associated image are verified as authentic and consistent."
    elif norm_verdict in ("False", "FALSE"):
        if is_image_fake:
            return (
                "High disinformation risk: The textual claim is refuted by fact-checking evidence, "
                f"and the associated image is detected as digitally altered ({image_verdict_str})."
            )
        else:
            return (
                "The news headline is refuted by evidence, even though the image itself does not show "
                "digital tampering artifacts (likely an authentic image reused in a misleading context)."
            )
    else:
        if is_image_fake:
            return (
                f"The textual claim could not be conclusively verified ({norm_verdict}), but the image "
                f"shows evidence of digital manipulation ({image_verdict_str})."
            )
        else:
            return (
                f"Text claim verification status is {norm_verdict}. The accompanying image appears authentic."
            )


@router.post("/verify-image", response_model=VerifyResponse)
@limiter.limit(settings.RATE_LIMIT)
async def verify_image(
    request: Request,
    file: UploadFile = File(...),
    claim: Optional[str] = Form(None)
):
    """
    Verify an image for manipulation/fakeness. Optionally include a text claim to verify alongside.
    
    Args:
        file: Image file (jpg, png, webp, etc.)
        claim: Optional text claim to verify alongside the image
    """
    if not file.filename:
        return JSONResponse(
            status_code=400,
            content={"error": "missing_file", "detail": "Image file is required."}
        )
    
    # Validate file extension
    valid_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp", ".tif", ".tiff"}
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if file_ext not in valid_extensions:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_file_type", "detail": f"Unsupported image format. Use one of: {', '.join(sorted(valid_extensions))}"}
        )
    
    try:
        # Read image bytes with size limit (max 10MB)
        MAX_FILE_SIZE = 10 * 1024 * 1024
        image_bytes = await file.read()
        if not image_bytes:
            return JSONResponse(
                status_code=400,
                content={"error": "empty_file", "detail": "Image file is empty."}
            )

        if len(image_bytes) > MAX_FILE_SIZE:
            return JSONResponse(
                status_code=400,
                content={"error": "file_too_large", "detail": "Image file exceeds the 10MB size limit."}
            )
        
        # Run image detection
        detector = get_image_detector()
        image_result = detector.predict(image_bytes)
        
        # Convert to response model
        image_verification = ImageVerificationResult(**image_result)
        
        # If a text claim was also provided, verify it as well
        if claim and claim.strip():
            clean_claim = claim.strip()
            if len(clean_claim) > 500:
                return JSONResponse(
                    status_code=422,
                    content={"error": "validation_error", "detail": "Claim text exceeds maximum allowed length (500 characters)."}
                )

            try:
                text_result = await run_verification(clean_claim)
            except asyncio.TimeoutError:
                logger.warning("Text verification timed out during multimodal call.")
                text_result = {
                    "verdict": "Not Enough Information",
                    "confidence": 0.5,
                    "summary": "Text verification timed out while querying external knowledge sources.",
                    "explanation": "Image manipulation analysis completed successfully, but claim verification timed out.",
                }
            except Exception as exc:
                logger.warning("Text verification failed during multimodal call: %s", exc)
                text_result = {
                    "verdict": "Not Enough Information",
                    "confidence": 0.5,
                    "summary": f"Text verification was temporarily unavailable ({type(exc).__name__}).",
                    "explanation": "Image manipulation analysis completed successfully, but text verification encountered a transient error.",
                }

            joint_eval = _synthesize_joint_assessment(text_result.get("verdict"), image_verification)

            return VerifyResponse(
                claim=clean_claim,
                verdict=text_result.get("verdict"),
                confidence=text_result.get("confidence"),
                summary=text_result.get("summary"),
                explanation=text_result.get("explanation"),
                image_result=image_verification,
                joint_assessment=joint_eval
            )
        else:
            # Return image verification result
            return VerifyResponse(
                image_result=image_verification
            )
    
    except Exception as exc:
        logger.exception("verify_image failed")
        return JSONResponse(
            status_code=500,
            content={"error": "image_verification_failed", "detail": f"Image analysis failed: {type(exc).__name__}"}
        )