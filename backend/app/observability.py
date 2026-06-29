"""Logging setup and request tracing.

Every HTTP request gets an `X-Request-ID` (honored from the client if present, else generated),
made available on `request.state.request_id`, echoed in the response header, and logged with
method, path, status, and duration. Telemetry already logs `run_id`, so a request id plus run id
together correlate an external call to its orchestration trace.

Secrets hygiene: request/response bodies are never logged here — only method, path, and status.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

logger = logging.getLogger("corenexia.access")


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(self.header_name) or uuid.uuid4().hex
        request.state.request_id = request_id

        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = int((time.monotonic() - start) * 1000)
            logger.exception(
                "req=%s %s %s -> ERROR (%dms)",
                request_id,
                request.method,
                request.url.path,
                duration_ms,
            )
            raise

        duration_ms = int((time.monotonic() - start) * 1000)
        response.headers[self.header_name] = request_id
        logger.info(
            "req=%s %s %s -> %d (%dms)",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
