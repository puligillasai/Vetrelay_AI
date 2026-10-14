"""Structured JSON logging for VetRelay AI.

Produces newline-delimited JSON records compatible with IBM Cloud Logs / IBM Log Analysis.
Each record follows the IBM Cloud Logs ingestion schema:
  https://cloud.ibm.com/docs/log-analysis?topic=log-analysis-ingestion

Usage
-----
    from backend.telemetry import get_logger
    log = get_logger(__name__)
    log.info("event=triage_requested species=canine severity_score=1")

Rules (enforced by convention, not code):
- All log lines MUST use key=value structured pairs.
- NEVER include owner_name, pet_name, or any free-text owner statement in log lines (PII risk).
- Use event= as the first key so IBM Log Analysis can index by event type.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# ---------------------------------------------------------------------------
# JSON formatter
# ---------------------------------------------------------------------------


class _JSONFormatter(logging.Formatter):
    """Emit one JSON object per log record — compatible with IBM Cloud Logs."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Request/response trace middleware
# ---------------------------------------------------------------------------


class _TraceMiddleware(BaseHTTPMiddleware):
    """Log every inbound request and its response status + latency."""

    def __init__(self, app: Any, logger: logging.Logger) -> None:
        super().__init__(app)
        self._log = logger

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        t0 = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        self._log.info(
            "event=http_request method=%s path=%s status=%d latency_ms=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        return response


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that emits structured JSON."""
    return logging.getLogger(name)


def setup_telemetry(app: FastAPI) -> None:
    """Attach the JSON formatter and request-trace middleware to the FastAPI app."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JSONFormatter())

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Replace any existing handlers to avoid duplicate plain-text output
    root.handlers = [handler]

    log = get_logger("vetrelay")
    log.info("event=telemetry_initialised service=vetrelay-ai")

    app.add_middleware(_TraceMiddleware, logger=get_logger("vetrelay.http"))
