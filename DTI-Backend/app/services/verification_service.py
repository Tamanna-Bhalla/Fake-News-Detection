import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.config import settings
from app.dependencies import get_pipeline

_executor = ThreadPoolExecutor(max_workers=4)

_VERDICT_MAP = {
    "TRUE": "True",
    "FALSE": "False",
    "MISLEADING": "Misleading",
    "NOT ENOUGH INFORMATION": "Not Enough Information",
    "UNVERIFIED": "Not Enough Information",
    "UNVERIFIABLE": "Not Enough Information",
}


def _normalize_verdict(value: object) -> str:
    raw = str(value or "Not Enough Information").strip()
    if raw in {"True", "False", "Misleading", "Not Enough Information"}:
        return raw
    return _VERDICT_MAP.get(raw.upper(), "Not Enough Information")

async def run_verification(claim: str, pipeline=None) -> dict:
    """
    Run the verification pipeline on a claim.
    """
    if pipeline is None:
        pipeline = get_pipeline()

    if pipeline is None:
        raise RuntimeError("Pipeline not initialized")

    loop = asyncio.get_event_loop()

    try:
        timeout_seconds = float(settings.VERIFY_TIMEOUT_SECONDS)
        task = loop.run_in_executor(
            _executor,
            pipeline.verify_claim,
            claim
        )

        if timeout_seconds > 0:
            result = await asyncio.wait_for(task, timeout=timeout_seconds)
        else:
            result = await task

        # Pipeline now returns simplified result directly
        # with fields: claim, normalized_claim, verdict, confidence, summary, reason, explanation
        return {
            "claim": result.get("claim"),
            "normalized_claim": result.get("normalized_claim"),
            "claim_type": result.get("claim_type", "current_event"),
            "status": result.get("status", "completed"),
            "verdict": _normalize_verdict(result.get("verdict")),
            "confidence": float(result.get("confidence")) if result.get("confidence") is not None else None,
            "summary": result.get("summary"),
            "explanation": result.get("explanation"),
            "limitations": result.get("limitations", []),
            "evidence": result.get("evidence", []),
            "sources": result.get("sources", []),
            "conflicting_sources": result.get("conflicting_sources", False),
        }

    except asyncio.TimeoutError:
        raise
    except Exception as e:
        raise RuntimeError(f"Pipeline error: {type(e).__name__}") from e