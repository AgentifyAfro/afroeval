"""
API key authentication + run rate limiting middleware.

Every request except health/docs must carry:
    X-API-Key: <AFROEVAL_SECRET_KEY>

POST /v1/runs is additionally rate-limited to RUNS_RATE_LIMIT per hour
per key to prevent accidental Azure spend runaway.
"""

import time
from collections import defaultdict, deque

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# In-memory per-key run log: {api_key: deque of monotonic timestamps}
_run_timestamps: dict[str, deque] = defaultdict(deque)

RUNS_RATE_LIMIT = 10          # max evaluation runs per rolling window
RATE_WINDOW_SECONDS = 3600    # 1 hour

# Paths that bypass auth (health probe, API docs)
_PUBLIC_PATHS = {"/v1/health", "/docs", "/redoc", "/openapi.json"}


class APIKeyMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, api_key: str):
        super().__init__(app)
        self._api_key = api_key

    async def dispatch(self, request: Request, call_next):
        if request.url.path in _PUBLIC_PATHS:
            return await call_next(request)

        # ── Auth ──────────────────────────────────────────────────────────────
        provided = request.headers.get("X-API-Key", "")
        if not provided or provided != self._api_key:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing API key. Pass X-API-Key header."},
            )

        # ── Rate limit POST /v1/runs ───────────────────────────────────────────
        if request.method == "POST" and request.url.path == "/v1/runs":
            now = time.monotonic()
            log = _run_timestamps[provided]
            while log and now - log[0] > RATE_WINDOW_SECONDS:
                log.popleft()
            if len(log) >= RUNS_RATE_LIMIT:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            f"Rate limit: max {RUNS_RATE_LIMIT} runs per hour. "
                            "Wait before submitting another run."
                        )
                    },
                )
            log.append(now)

        return await call_next(request)
