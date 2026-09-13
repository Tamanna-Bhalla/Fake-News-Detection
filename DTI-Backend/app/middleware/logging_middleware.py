import time
import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import structlog

logger = structlog.get_logger(__name__)

class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Measures and logs duration, status, and path with correlation request IDs.
    Strictly avoids logging raw image bytes or sensitive claims.
    """
    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.perf_counter()
        
        # Extract or generate correlation Request ID
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        try:
            response = await call_next(request)
            process_time_ms = (time.perf_counter() - start_time) * 1000
            
            # Attach X-Request-ID header to response
            response.headers["X-Request-ID"] = request_id
            
            logger.info(
                "request_completed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(process_time_ms, 2)
            )
            return response
            
        except Exception as e:
            process_time_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request_failed",
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                duration_ms=round(process_time_ms, 2),
                error=str(e)
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()