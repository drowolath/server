import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.metrics import http_requests, http_request_duration

log = structlog.get_logger()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = str(uuid.uuid4())

        # Clear and bind per-request context
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration = time.monotonic() - start
            log.error("request_failed", duration_ms=round(duration * 1000, 2))
            raise

        duration = time.monotonic() - start
        status_code = response.status_code

        # Prometheus metrics
        # Normalize path to avoid high-cardinality labels (strip UUIDs)
        normalized_path = request.url.path
        http_requests.labels(method=request.method, path=normalized_path, status_code=str(status_code)).inc()
        http_request_duration.labels(method=request.method, path=normalized_path).observe(duration)

        # Structured log
        log.info(
            "request_completed",
            status_code=status_code,
            duration_ms=round(duration * 1000, 2),
        )

        # Add request ID to response headers for traceability
        response.headers["X-Request-ID"] = request_id
        return response
