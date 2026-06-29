"""Per-key sliding-window rate limiter (in-memory).

Adequate for a single-process deployment. For multi-process/horizontal scaling, back this with
Redis in a later hardening pass — the `allow` interface stays the same.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key_id: str) -> bool:
        """Return True if a request for this key is within the limit. 0 disables limiting."""
        if self.per_minute <= 0:
            return True
        now = time.monotonic()
        window_start = now - 60.0
        with self._lock:
            hits = self._hits[key_id]
            while hits and hits[0] < window_start:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True
