"""Middleware FastAPI: request logging i rate limiting."""

import logging
import time
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Loguje kazdy request: method, path, status, duration."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 1)

        logger.info(
            "%s %s → %d (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Process-Time-Ms"] = str(duration_ms)
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Prosty rate limit per IP: max_requests na minute."""

    def __init__(self, app, max_requests: int = 100):
        super().__init__(app)
        self.max_requests = max_requests
        # {ip: [(timestamp, ...)] }
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = 60.0  # 1 minute

        # Clean old entries
        self._requests[client_ip] = [
            t for t in self._requests[client_ip] if now - t < window
        ]

        if len(self._requests[client_ip]) >= self.max_requests:
            logger.warning("Rate limit exceeded for %s", client_ip)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Max 100 requests per minute.",
                },
                headers={"Retry-After": "60"},
            )

        self._requests[client_ip].append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(
            self.max_requests - len(self._requests[client_ip])
        )
        return response
