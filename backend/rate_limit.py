"""
Rate limiting configuration (Tier 0f) using SlowAPI.

SlowAPI is a thin wrapper for Starlette/FastAPI. We rate-limit by
client IP, defaulting to 60 requests per minute per IP. The limit is
configurable via RATE_LIMIT_PER_MINUTE.

Tier 0f only adds the limiter skeleton. Per-endpoint limits are wired
in Tier 1 (public API tier). The current default is a soft "everything
is 60/min" limit.
"""

from __future__ import annotations

import os

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request


def _rate_limit_key(request: Request) -> str:
    """Default: rate limit by client IP. Override for authed-user keys."""
    return get_remote_address(request)


_RATE_LIMIT = os.getenv("RATE_LIMIT_PER_MINUTE", "60") + "/minute"

limiter = Limiter(
    key_func=_rate_limit_key,
    default_limits=[_RATE_LIMIT],
    headers_enabled=True,
    storage_uri="memory://",  # in-memory; swap for Redis in production
)


def install_rate_limiter(app) -> None:
    """Wire the limiter into a FastAPI app. Call from main.py."""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


__all__ = ["limiter", "install_rate_limiter"]