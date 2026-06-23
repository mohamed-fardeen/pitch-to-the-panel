"""
Sentry error tracking integration (Tier-1b).

Wires Sentry into the FastAPI app and a separate Sentry SDK for the
Node.js frontend. When SENTRY_DSN is unset, both integrations are
no-ops.

Why separate from Langfuse:
- Langfuse = LLM observability (traces, tokens, latency)
- Sentry = error tracking (exceptions, breadcrumbs, performance)

Sentry's FastAPI integration auto-captures:
- Unhandled exceptions in route handlers
- Request context (URL, method, headers, body)
- Response status
- Performance traces (transactions)

We also wire the lifespan to flush Sentry on shutdown.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def is_sentry_enabled() -> bool:
    """True if Sentry is configured (SENTRY_DSN env var set)."""
    return bool(os.getenv("SENTRY_DSN", "").strip())


def init_sentry() -> Any:
    """
    Initialize Sentry for the FastAPI app.

    Idempotent: safe to call multiple times. Returns the Sentry client
    or None if not configured.
    """
    if not is_sentry_enabled():
        logger.info("Sentry disabled (no SENTRY_DSN set).")
        return None

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.warning(
            "SENTRY_DSN is set but sentry-sdk is not installed. "
            "pip install 'sentry-sdk[fastapi]' to enable error tracking."
        )
        return None

    dsn = os.getenv("SENTRY_DSN", "").strip()
    environment = os.getenv("SENTRY_ENVIRONMENT", os.getenv("PANELMIND_ENV", "development"))
    release = os.getenv("SENTRY_RELEASE", "panelmind@0.1.0")
    traces_sample_rate = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    profiles_sample_rate = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0"))

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            integrations=[
                FastApiIntegration(transaction_style="url"),
                StarletteIntegration(transaction_style="url"),
                LoggingIntegration(
                    level=logging.INFO,        # capture info+ as breadcrumbs
                    event_level=logging.ERROR,  # capture errors as events
                ),
            ],
            # Don't send PII by default. Override in production if needed.
            send_default_pii=False,
            # Sample at the trace level (avoids head-of-line blocking).
            enable_tracing=True,
        )
        logger.info(
            "Sentry initialized (env=%s, release=%s, sample_rate=%.2f)",
            environment, release, traces_sample_rate,
        )
        return sentry_sdk
    except Exception as e:
        logger.error("Sentry init failed: %s", e)
        return None


def capture_exception(
    error: BaseException,
    *,
    context: dict[str, Any] | None = None,
    level: str = "error",
) -> None:
    """
    Manually report an exception to Sentry.

    Use this for caught exceptions that you want to track but not
    re-raise. Unhandled exceptions are caught automatically by the
    FastAPI integration.
    """
    if not is_sentry_enabled():
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if context:
                for k, v in context.items():
                    scope.set_extra(k, v)
            scope.level = level
            sentry_sdk.capture_exception(error)
    except Exception as e:
        logger.debug("Sentry capture_exception failed: %s", e)


def capture_message(
    message: str,
    *,
    level: str = "info",
    context: dict[str, Any] | None = None,
) -> None:
    """
    Send a non-exception message to Sentry (for breadcrumbs, alerts).
    """
    if not is_sentry_enabled():
        return
    try:
        import sentry_sdk
        with sentry_sdk.push_scope() as scope:
            if context:
                for k, v in context.items():
                    scope.set_extra(k, v)
            scope.level = level
            sentry_sdk.capture_message(message, level=level)
    except Exception as e:
        logger.debug("Sentry capture_message failed: %s", e)


__all__ = [
    "is_sentry_enabled",
    "init_sentry",
    "capture_exception",
    "capture_message",
]