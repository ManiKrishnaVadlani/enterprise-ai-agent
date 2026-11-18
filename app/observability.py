"""Small process-local request metrics that never capture request content."""

import threading
import logging
from collections import Counter
from time import perf_counter
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class RequestMetrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._counts: Counter[str] = Counter()
        self._durations: dict[str, float] = {}

    def record(self, method: str, path: str, status_code: int, seconds: float) -> None:
        key = f"{method} {path} {status_code}"
        with self._lock:
            self._counts[key] += 1
            self._durations[key] = self._durations.get(key, 0.0) + seconds

    def snapshot(self) -> dict:
        with self._lock:
            return {key: {"requests": count, "duration_seconds_total": round(self._durations[key], 6)}
                    for key, count in sorted(self._counts.items())}


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = uuid4().hex
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            duration = perf_counter() - started
            route_path = getattr(request.scope.get("route"), "path", "unmatched")
            request.app.state.request_metrics.record(
                request.method, route_path, status_code, duration
            )
            logger.info(
                "Request completed request_id=%s method=%s endpoint=%s status=%d duration_seconds=%.6f",
                request_id, request.method, route_path, status_code, duration,
            )
