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

from .sentry import (
    capture_exception,
    capture_message,
    init_sentry,
    is_sentry_enabled,
)
from .tracing import (
    flush_traces,
    is_tracing_enabled,
    trace_llm_call,
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
