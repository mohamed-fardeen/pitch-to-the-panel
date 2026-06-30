"""
LLM tracing — Langfuse integration with a no-op fallback.

Usage:

    from backend.observability import trace_llm_call

    with trace_llm_call(
        name="persona_node_vc",
        provider="anthropic",
        model="claude-3-5-sonnet-latest",
        session_id=session_id,
        metadata={"persona_id": "vc"},
    ) as trace:
        response = await llm.generate_response(...)
        trace.update(output=response, usage=...)

If Langfuse is not configured (no LANGFUSE_PUBLIC_KEY env var), the
context manager is a no-op and `trace` is a `_NoOpTrace` that swallows
all updates. This means production tracing is opt-in via env vars.
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

logger = logging.getLogger(__name__)


# ─── Configuration ────────────────────────────────────────────────


class TracingConfig:
    """Reads Langfuse env vars at module load time. No-op if unset."""

    def __init__(self) -> None:
        self.public_key = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
        self.secret_key = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
        self.host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()
        self.enabled = bool(self.public_key and self.secret_key)
        self._client: Any = None

    def get_client(self) -> Any:
        """Lazy-load the Langfuse SDK. Returns None if not enabled."""
        if not self.enabled:
            return None
        if self._client is not None:
            return self._client
        try:
            from langfuse import Langfuse
            self._client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host,
            )
            logger.info("Langfuse client initialized (host=%s)", self.host)
        except ImportError:
            logger.warning(
                "LANGFUSE_PUBLIC_KEY is set but langfuse is not installed. "
                "pip install langfuse to enable tracing."
            )
            self._client = None
        except Exception as e:
            logger.error("Failed to initialize Langfuse: %s", e)
            self._client = None
        return self._client

    def flush(self) -> None:
        """Flush pending traces. Call on app shutdown."""
        if self._client is not None and hasattr(self._client, "flush"):
            try:
                self._client.flush()
            except Exception as e:
                logger.debug("Langfuse flush failed: %s", e)


_config = TracingConfig()


def is_tracing_enabled() -> bool:
    """True if Langfuse is configured and the SDK loaded successfully."""
    return _config.enabled and _config.get_client() is not None


# ─── Trace handle ────────────────────────────────────────────────


class _NoOpTrace:
    """A trace that does nothing. Used when Langfuse is disabled."""

    def update(self, **_kwargs: Any) -> None:
        pass

    def end(self) -> None:
        pass

    def span(self, *_args: Any, **_kwargs: Any) -> _NoOpTrace:
        return self

    def __enter__(self) -> _NoOpTrace:
        return self

    def __exit__(self, *_args: Any) -> None:
        pass


class _LangfuseTrace:
    """Wraps a Langfuse trace handle. Forwards updates to the SDK."""

    def __init__(self, trace: Any) -> None:
        self._trace = trace
        self._start = time.monotonic()
        self._spans: list[Any] = []

    def update(self, **kwargs: Any) -> None:
        try:
            # Langfuse v2 SDK: `trace.update(output=..., metadata=...)`
            self._trace.update(**kwargs)
        except Exception as e:
            logger.debug("Langfuse update failed: %s", e)

    def span(self, name: str, **kwargs: Any) -> _LangfuseTrace:
        try:
            span = self._trace.span(name=name, **kwargs)
            self._spans.append(span)
            return _LangfuseTrace(span)
        except Exception as e:
            logger.debug("Langfuse span failed: %s", e)
            return _NoOpTrace()

    def end(self) -> None:
        try:
            self._trace.update(
                latency=(time.monotonic() - self._start),
            )
        except Exception as e:
            logger.debug("Langfuse end failed: %s", e)

    def __enter__(self) -> _LangfuseTrace:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if exc_type is not None:
            self.update(
                status="error",
                error=f"{exc_type.__name__}: {exc_val}",
            )
        self.end()


# ─── Public entry point ──────────────────────────────────────────


@contextmanager
def trace_llm_call(
    name: str,
    *,
    provider: str = "",
    model: str = "",
    session_id: str | None = None,
    user_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    input_data: Any | None = None,
) -> Iterator[Any]:
    """
    Context manager that traces an LLM call.

    Usage:
        with trace_llm_call(name="controller", provider="anthropic") as trace:
            response = await llm.generate_response(...)
            trace.update(output=response)

    Yields a trace handle. If tracing is disabled, the handle is a
    no-op (all methods do nothing).
    """
    client = _config.get_client()
    if client is None:
        # No-op mode. The context manager's __exit__ never runs (we
        # manually call .end() in the finally), so we wrap the yield
        # in try/except/finally to handle exceptions.
        noop = _NoOpTrace()
        try:
            yield noop
        except Exception as exc_val:
            noop.update(status="error", error=f"{type(exc_val).__name__}: {exc_val}")
            raise
        finally:
            noop.end()
        return

    # Real tracing path
    trace_handle: Any = _NoOpTrace()
    exc_info = _capture_exc()
    try:
        # Set up the Langfuse trace. If this fails, fall back to no-op.
        try:
            # Langfuse v2: `langfuse.trace(name=..., session_id=..., ...)`
            lf_trace = client.trace(
                name=name,
                session_id=session_id,
                user_id=user_id,
                metadata={
                    "provider": provider,
                    "model": model,
                    "trace_id": str(uuid.uuid4()),
                    **(metadata or {}),
                },
            )
            if input_data is not None:
                lf_trace.update(input=input_data)
            trace_handle = _LangfuseTrace(lf_trace)
        except Exception as e:
            logger.debug("Langfuse trace setup failed: %s", e)
            trace_handle = _NoOpTrace()
        try:
            yield trace_handle
        except Exception as exc_val:
            exc_info = (type(exc_val), exc_val, exc_val.__traceback__)
            # Mark the trace as errored
            with suppress(Exception):
                trace_handle.update(
                    status="error",
                    error=f"{exc_info[0].__name__}: {exc_info[1]}",
                )
            raise
    finally:
        # Always call .end() to record latency, even on the success path.
        with suppress(Exception):
            trace_handle.end()


def _capture_exc() -> tuple:
    """Return sys.exc_info() at call time, or (None, None, None)."""
    import sys
    return sys.exc_info()


def flush_traces() -> None:
    """Flush pending traces. Call on app shutdown."""
    _config.flush()


__all__ = ["trace_llm_call", "is_tracing_enabled", "flush_traces"]
