"""API hardening: per-IP rate limiting, security headers, generic error responses."""

import threading
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger

logger = get_logger(__name__)

_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")
_STRICT_CSP = "default-src 'none'; frame-ancestors 'none'"
# Swagger UI loads its JS/CSS from jsDelivr and the FastAPI favicon.
_DOCS_CSP = (
    "default-src 'none'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; "
    "style-src 'self' https://cdn.jsdelivr.net; img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; frame-ancestors 'none'"
)


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    """Standard error body from Rules.md §5."""
    return {"error": {"code": code, "message": message}}


class RateLimiter:
    """Fixed-window per-key counter kept in memory (fine for a single API instance)."""

    def __init__(
        self, limit: int, window_seconds: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit = limit
        self.window = window_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._counts: dict[str, tuple[float, int]] = {}

    def hit(self, key: str) -> float | None:
        """Record a request. Return None if allowed, else seconds until the window resets."""
        now = self._clock()
        with self._lock:
            if len(self._counts) > 10_000:  # drop expired windows so memory stays bounded
                self._counts = {k: v for k, v in self._counts.items() if now - v[0] < self.window}
            start, count = self._counts.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            if count >= self.limit:
                return self.window - (now - start)
            self._counts[key] = (start, count + 1)
            return None


def install_security(app: FastAPI, limiter: RateLimiter) -> None:
    """Attach the rate limiter, security headers and generic error handlers to ``app``."""

    @app.middleware("http")
    async def _rate_limit_and_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        retry_after = limiter.hit(client_ip)
        if retry_after is not None:
            response: Response = JSONResponse(
                error_body("rate_limited", "Too many requests. Please slow down."),
                status_code=429,
                headers={"Retry-After": str(max(1, int(retry_after)))},
            )
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        is_docs = request.url.path.startswith(_DOCS_PATHS)
        response.headers["Content-Security-Policy"] = _DOCS_CSP if is_docs else _STRICT_CSP
        return response

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {400: "bad_request", 404: "not_found", 405: "method_not_allowed"}.get(
            exc.status_code, "http_error"
        )
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return JSONResponse(error_body(code, message), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Name the bad parameters, but never echo the submitted values back.
        fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
        message = "Invalid parameters: " + ", ".join(fields) if fields else "Invalid request."
        return JSONResponse(error_body("bad_request", message), status_code=400)

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(error_body("internal_error", "Something went wrong."), status_code=500)
