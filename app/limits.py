"""Small process-local concurrency and authenticated request limits."""

import threading
import time
from collections import deque


class UploadConcurrencyLimit:
    """Limit active uploads and bound how long requests wait for a slot."""

    def __init__(self, max_concurrent: int, wait_timeout_seconds: float):
        self._semaphore = threading.BoundedSemaphore(max_concurrent)
        self.wait_timeout_seconds = wait_timeout_seconds

    def acquire(self) -> bool:
        return self._semaphore.acquire(timeout=self.wait_timeout_seconds)

    def release(self) -> None:
        self._semaphore.release()


class UserRateLimiter:
    """Apply a bounded sliding-window limit per user within one process."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        max_tracked_users: int = 10_000,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.max_tracked_users = max_tracked_users
        self._requests: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def consume(self, user_id: str, now: float | None = None) -> float | None:
        """Return retry seconds when limited, otherwise record and return None."""
        current_time = time.monotonic() if now is None else now
        cutoff = current_time - self.window_seconds
        with self._lock:
            requests = self._requests.get(user_id)
            if requests is None:
                self._remove_expired(cutoff)
                if len(self._requests) >= self.max_tracked_users:
                    return self.window_seconds
                requests = self._requests.setdefault(user_id, deque())
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if len(requests) >= self.max_requests:
                return max(0.0, requests[0] + self.window_seconds - current_time)
            requests.append(current_time)
            return None

    def _remove_expired(self, cutoff: float) -> None:
        expired_users: list[str] = []
        for user_id, requests in self._requests.items():
            while requests and requests[0] <= cutoff:
                requests.popleft()
            if not requests:
                expired_users.append(user_id)
        for user_id in expired_users:
            del self._requests[user_id]
