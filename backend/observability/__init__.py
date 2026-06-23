"""
backend.observability
====================

LLM observability (Langfuse) and error tracking (Sentry).

In dev (no LANGFUSE_PUBLIC_KEY or SENTRY_DSN env var), both
integrations are no-ops. In production, every LLM call gets traced
and every unhandled exception gets reported.

The orchestrator code does NOT call these directly — they're
wrapped inside the LLMProvider and FastAPI lifespan respectively.
"""

from .tracing import (
    trace_llm_call,
    is_tracing_enabled,
    flush_traces,
)
from .sentry import (
    is_sentry_enabled,
    init_sentry,
    capture_exception,
    capture_message,
)

__all__ = [
    # Langfuse / tracing
    "trace_llm_call",
    "is_tracing_enabled",
    "flush_traces",
    # Sentry
    "is_sentry_enabled",
    "init_sentry",
    "capture_exception",
    "capture_message",
]