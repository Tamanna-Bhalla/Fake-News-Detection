import asyncio
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Depends, Request, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
import structlog

from app.config import settings
from app.models.requests import VerifyRequest
from app.models.responses import (
    VerifyResponse,
    TextAssessment,
    ImageAssessment,
    ClassificationDetails,
    AnomalyAnalysis,
    LocalizationDetails,
    ClaimMetadata,
    EvidenceCitation,
    ImageVerificationResult,
    ModelVersionInfo,
)
from app.dependencies import get_pipeline, get_image_service, image_inference_semaphore
from app.services.verification_service import run_verification
from app.utils.validators import validate_claim_text, stream_and_validate_image_upload
from app.utils.error_handlers import make_error_response

logger = structlog.get_logger(__name__)
router = APIRouter()

# Setup rate limiter using user remote IP
limiter = Limiter(key_func=get_remote_address)


@router.post("/verify", response_model=VerifyResponse)
@limiter.limit(settings.RATE_LIMIT)
async def verify_claim(
    request: Request,
    body: VerifyRequest,
    pipeline=Depends(get_pipeline)
):
    """
    Takes a news headline claim and passes it to the AI verification pipeline.
    Produces evidence-grounded assessment, source citations, and epistemic classification.
    """
    request_id = getattr(request.state, "request_id", None)

    # 1. Strict claim input sanitization & validation
    try:
        clean_claim = validate_claim_text(body.claim)
    except HTTPException as exc:
        return make_error_response(
            status_code=exc.status_code,
            code="VALIDATION_ERROR",
            message=str(exc.detail),
            request=request
        )

    if pipeline is None:
        return make_error_response(
            status_code=503,
            code="SERVICE_UNAVAILABLE",
            message="Verification service is initializing. Please retry shortly.",
            request=request
        )

    try:
        raw_result = await run_verification(clean_claim, pipeline=pipeline)

        # Build evidence items
        evidence_list: List[EvidenceCitation] = []
        for ev in raw_result.get("evidence", []):
            try:
                evidence_list.append(EvidenceCitation(**ev))
            except Exception:
                continue

        text_assessment = TextAssessment(
            status=raw_result.get("status", "completed"),
            verdict=raw_result.get("verdict", "Not Enough Information"),
            confidence=raw_result.get("confidence"),
            summary=raw_result.get("summary", ""),
            limitations=raw_result.get("limitations", []),
            error_code=None
        )

        claim_metadata = ClaimMetadata(
            original=clean_claim,
            normalized=raw_result.get("normalized_claim"),
            claim_type=raw_result.get("claim_type", "current_event")
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        return VerifyResponse(
            request_id=request_id,
            created_at=now_iso,
            claim_details=claim_metadata,
            text_assessment=text_assessment,
            evidence=evidence_list,
            model=ModelVersionInfo(),
            # Backward-compatible fields
            claim=clean_claim,
            verdict=text_assessment.verdict,
            confidence=text_assessment.confidence,
            summary=text_assessment.summary,
            explanation=raw_result.get("explanation"),
            sources=raw_result.get("sources", [])
        )

    except asyncio.TimeoutError:
        return make_error_response(
            status_code=504,
            code="GATEWAY_TIMEOUT",
            message="Verification timed out while querying external knowledge sources. Try a shorter claim.",
            request=request
        )

    except RuntimeError as exc:
        logger.error("verification_pipeline_runtime_error", error=str(exc), request_id=request_id)
        return make_error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Verification failed due to an internal pipeline error.",
            request=request
        )

    except Exception as exc:
        logger.exception("verify_claim failed", exc_info=exc)
        return make_error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message="Result could not be processed.",
            request=request
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
    claim: Optional[str] = Form(None),
    detector=Depends(get_image_service)
):
    """
    Verify an image for digital manipulation and forensic anomalies.
    Optionally evaluates an accompanying text claim to provide a joint multimodal assessment.
    """
    request_id = getattr(request.state, "request_id", None)

    # 1. Stream image bytes in chunks and perform security checks with Pillow
    try:
        image_bytes, img_meta = await stream_and_validate_image_upload(file)
    except HTTPException as exc:
        code = "FILE_TOO_LARGE" if exc.status_code == 413 else (
            "UNSUPPORTED_MEDIA_TYPE" if exc.status_code == 415 else "VALIDATION_ERROR"
        )
        return make_error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
            request=request
        )

    # 2. Run image forensic detection with bounded concurrency semaphore
    try:
        async with image_inference_semaphore:
            loop = asyncio.get_event_loop()
            image_result_dict = await loop.run_in_executor(None, detector.predict, image_bytes)

        image_verification = ImageVerificationResult(**image_result_dict)

        # Build modern ImageAssessment
        classification_data = image_result_dict.get("classification") or {
            "label": "manipulated" if image_verification.is_fake else "authentic",
            "probability": float(image_verification.confidence)
        }
        anomaly_data = image_result_dict.get("anomaly_analysis") or {
            "ela_score": 0.0,
            "noise_score": 0.0,
            "forensic_details": image_result_dict.get("forensic_details")
        }
        localization_data = image_result_dict.get("localization") or {
            "available": image_verification.heatmap_base64 is not None,
            "heatmap_type": "forensic_anomaly",
            "heatmap_base64": image_verification.heatmap_base64
        }

        image_assessment = ImageAssessment(
            status="completed" if image_verification.error is None else "unsupported",
            verdict=image_verification.verdict or "Unknown",
            confidence=image_verification.confidence if image_verification.is_fake is not None else None,
            classification=ClassificationDetails(**classification_data),
            anomaly_analysis=AnomalyAnalysis(**anomaly_data),
            localization=LocalizationDetails(**localization_data),
            disclaimer=image_result_dict.get(
                "disclaimer",
                "Automated forensic assessment: anomalies indicate statistical compression/noise discrepancies, not definitive proof of manipulation."
            ),
            error_code=None if image_verification.error is None else "FORENSIC_ERROR"
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        # 3. Multimodal: If text claim is provided, verify it concurrently
        if claim and claim.strip():
            clean_claim = validate_claim_text(claim.strip())
            evidence_list: List[EvidenceCitation] = []

            try:
                text_result = await run_verification(clean_claim)
                for ev in text_result.get("evidence", []):
                    try:
                        evidence_list.append(EvidenceCitation(**ev))
                    except Exception:
                        continue

                text_assessment = TextAssessment(
                    status=text_result.get("status", "completed"),
                    verdict=text_result.get("verdict", "Not Enough Information"),
                    confidence=text_result.get("confidence"),
                    summary=text_result.get("summary", ""),
                    limitations=text_result.get("limitations", []),
                    error_code=None
                )
            except asyncio.TimeoutError:
                logger.warning("text_verification_timeout_multimodal", request_id=request_id)
                # Honest failure: confidence is null, status is unavailable
                text_result = {
                    "verdict": "Not Enough Information",
                    "confidence": None,
                    "summary": "Text verification timed out while querying external knowledge sources.",
                    "explanation": "Image manipulation analysis completed successfully, but claim verification timed out.",
                    "limitations": ["Retrieval timeout: external sources did not respond within time limit."],
                }
                text_assessment = TextAssessment(
                    status="unavailable",
                    verdict="Not Enough Information",
                    confidence=None,
                    summary=text_result["summary"],
                    limitations=text_result["limitations"],
                    error_code="RETRIEVAL_TIMEOUT"
                )
            except Exception as exc:
                logger.warning("text_verification_failed_multimodal", error=str(exc), request_id=request_id)
                text_result = {
                    "verdict": "Not Enough Information",
                    "confidence": None,
                    "summary": f"Text verification was temporarily unavailable ({type(exc).__name__}).",
                    "explanation": "Image manipulation analysis completed successfully, but text verification encountered a transient error.",
                    "limitations": [f"Pipeline error: {type(exc).__name__}"],
                }
                text_assessment = TextAssessment(
                    status="unavailable",
                    verdict="Not Enough Information",
                    confidence=None,
                    summary=text_result["summary"],
                    limitations=text_result["limitations"],
                    error_code="PIPELINE_ERROR"
                )

            joint_eval = _synthesize_joint_assessment(text_result.get("verdict"), image_verification)

            claim_meta = ClaimMetadata(
                original=clean_claim,
                normalized=text_result.get("normalized_claim"),
                claim_type=text_result.get("claim_type", "current_event")
            )

            return VerifyResponse(
                request_id=request_id,
                created_at=now_iso,
                claim_details=claim_meta,
                text_assessment=text_assessment,
                image_assessment=image_assessment,
                evidence=evidence_list,
                joint_interpretation=joint_eval,
                model=ModelVersionInfo(),
                # Backward-compatible fields
                claim=clean_claim,
                verdict=text_assessment.verdict,
                confidence=text_assessment.confidence,
                summary=text_assessment.summary,
                explanation=text_result.get("explanation"),
                image_result=image_verification,
                joint_assessment=joint_eval
            )
        else:
            # Standalone image verification response
            return VerifyResponse(
                request_id=request_id,
                created_at=now_iso,
                image_assessment=image_assessment,
                model=ModelVersionInfo(),
                # Backward-compatible fields
                image_result=image_verification
            )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("verify_image failed", exc_info=exc)
        return make_error_response(
            status_code=500,
            code="INTERNAL_ERROR",
            message=f"Image analysis failed: {type(exc).__name__}",
            request=request
        )