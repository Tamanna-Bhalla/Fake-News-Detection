from typing import Any, Optional
from fastapi import Request, status, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
import structlog

from app.config import settings

logger = structlog.get_logger(__name__)

STATUS_TO_CODE = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    413: "FILE_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMIT_EXCEEDED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
    504: "GATEWAY_TIMEOUT",
}


def make_error_response(
    status_code: int,
    code: str,
    message: str,
    request: Request,
    detail: Optional[Any] = None,
    headers: Optional[dict] = None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    resp_headers = dict(headers or {})
    if request_id:
        resp_headers["X-Request-ID"] = request_id

    content = {
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
            "detail": detail
        },
        "detail": message,
    }
    return JSONResponse(status_code=status_code, content=content, headers=resp_headers)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Formats HTTPException into our standardized error envelope."""
    code = STATUS_TO_CODE.get(exc.status_code, "ERROR")
    msg = str(exc.detail) if exc.detail else "An HTTP error occurred."
    return make_error_response(
        status_code=exc.status_code,
        code=code,
        message=msg,
        request=request,
        headers=exc.headers
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Catches Pydantic 422 errors and formats them into our standardized error schema."""
    errors = exc.errors()
    detail_msg = "Validation error"
    
    if errors:
        first_error = errors[0]
        field = ".".join(str(loc) for loc in first_error.get("loc", []) if loc != "body")
        msg = first_error.get("msg", "")
        detail_msg = f"{field}: {msg}".strip(":") if field else msg

    return make_error_response(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        code="VALIDATION_ERROR",
        message=detail_msg,
        request=request,
        detail=errors
    )


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Catches slowapi 429 errors and formats consistent response."""
    return make_error_response(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        code="RATE_LIMIT_EXCEEDED",
        message=f"Rate limit exceeded: {settings.RATE_LIMIT} allowed.",
        request=request,
        detail={"retry_after_seconds": 60},
        headers={"Retry-After": "60"}
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catches any unhandled 500 errors to prevent unformatted responses and log trace."""
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(
        "unhandled_internal_server_error",
        request_id=request_id,
        path=request.url.path,
        error=str(exc),
        exc_info=True
    )
    return make_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        code="INTERNAL_ERROR",
        message="An unexpected server error occurred.",
        request=request
    )