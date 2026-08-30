"""Rate limiting: one global limit per caller, plus a per-user limit on AI calls.

Counters are in this worker's memory, so the effective limit multiplies by
the number of workers and replicas. A limit that must hold across processes
needs shared state.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware

DEFAULT_LIMIT = 60
DEFAULT_WINDOW_SECONDS = 60

# Research fans out to several model calls, so it gets its own smaller
# per-user budget on top of the global one.
DEFAULT_AI_LIMIT = 20

# A limited liveness probe turns load into a restart loop.
EXEMPT_PATHS = frozenset({"/health"})


@dataclass
class _Window:
    started_at: float
    count: int


class RateLimiter:
    """Fixed-window counters, keyed by caller.

    Fixed window rather than a sliding log: bounded memory, at the cost of
    a double burst either side of a window boundary.
    """

    def __init__(self, limit: int = DEFAULT_LIMIT, window: int = DEFAULT_WINDOW_SECONDS):
        self.limit = limit
        self.window = window
        self._windows: dict[str, _Window] = {}
        # Requests are served on a thread pool, so two can increment the
        # same counter at once and lose one of them.
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> int | None:
        """Seconds to wait, or None if the request may proceed.

        Returns the wait so the response can carry `Retry-After`; a client
        told only "no" retries immediately.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            window = self._windows.get(key)
            if window is None or now - window.started_at >= self.window:
                self._windows[key] = _Window(started_at=now, count=1)
                return None
            if window.count >= self.limit:
                return max(1, int(self.window - (now - window.started_at)) + 1)
            window.count += 1
            return None

    def prune(self, now: float | None = None) -> int:
        """Drop expired windows. Without this the map grows per distinct
        caller forever, which a rotating source address can drive."""
        now = time.monotonic() if now is None else now
        with self._lock:
            stale = [
                key
                for key, window in self._windows.items()
                if now - window.started_at >= self.window
            ]
            for key in stale:
                del self._windows[key]
        return len(stale)


def client_key(request) -> str:
    """The bucket this request counts against.

    `X-Forwarded-For` only when the deployment says it is behind a proxy:
    in front of one the header is attacker-controlled, and trusting it
    hands every caller unlimited fresh buckets.
    """
    if os.environ.get("LEGAL_AI_TRUST_PROXY_HEADER", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """One limit for every request, keyed by caller address."""

    def __init__(self, app, limiter: RateLimiter | None = None):
        super().__init__(app)
        self.limiter = limiter or RateLimiter()
        self._pruned_at = time.monotonic()

    async def dispatch(self, request, call_next):
        if request.url.path in EXEMPT_PATHS:
            return await call_next(request)

        now = time.monotonic()
        # Amortised cleanup, once per window, on whichever request arrives
        # first: a background task would need a lifecycle this has not got.
        if now - self._pruned_at >= self.limiter.window:
            self._pruned_at = now
            self.limiter.prune(now)

        retry_after = self.limiter.check(client_key(request), now)
        if retry_after is not None:
            from api.utils.errors import rate_limited
            from api.utils.response import respond

            response = respond(rate_limited())
            response.headers["Retry-After"] = str(retry_after)
            return response
        return await call_next(request)


_ai_limiter = RateLimiter(limit=DEFAULT_AI_LIMIT)


def check_ai_quota(user_id: str) -> int | None:
    """Seconds to wait before this user may make another AI call, or None.

    Keyed by user rather than address: the middleware runs before routing
    and does not know who is asking, and one account behind a shared office
    address should not spend everyone else's budget.
    """
    return _ai_limiter.check(f"ai:{user_id}")


def reset_ai_quota() -> None:
    """Clear the per-user counters. For tests."""
    _ai_limiter._windows.clear()
