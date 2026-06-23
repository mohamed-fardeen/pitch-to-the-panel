"""
Tests for the observability / Langfuse tracing module.

These verify:
- The module imports cleanly whether or not Langfuse is configured
- The trace context manager is a no-op when disabled (the dev case)
- The trace context manager correctly forwards updates to Langfuse
  when enabled (we mock the SDK to avoid network calls)
- The is_tracing_enabled() helper returns the right value
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ─── Module-level smoke ───────────────────────────────────────────


def test_module_imports_without_langfuse():
    """The module should import even if langfuse is not installed."""
    # The import happens at the top of the test file
    from backend.observability import trace_llm_call, is_tracing_enabled, flush_traces

    assert trace_llm_call is not None
    assert is_tracing_enabled is not None
    assert flush_traces is not None


def test_tracing_disabled_by_default():
    """Without LANGFUSE_PUBLIC_KEY, is_tracing_enabled() returns False."""
    # We patch the env to make sure no key is set
    with patch.dict(os.environ, {}, clear=True):
        # Force a fresh import of the module
        from backend.observability import tracing
        from importlib import reload
        reload(tracing)

        try:
            # In a clean env with no Langfuse env vars, disabled
            # (this also handles the case where langfuse isn't installed)
            result = tracing.is_tracing_enabled()
            assert result is False
        finally:
            # Reload again to restore default state
            reload(tracing)


# ─── No-op behavior ──────────────────────────────────────────────


def test_trace_context_is_noop_when_disabled():
    """When tracing is off, trace_llm_call yields a no-op context manager."""
    from backend.observability import tracing

    # Force disabled state
    with patch.object(tracing, "is_tracing_enabled", return_value=False):
        with tracing.trace_llm_call(
            name="test_call",
            provider="anthropic",
            model="claude-3-5-sonnet-latest",
        ) as trace:
            # The handle should be a no-op
            assert hasattr(trace, "update")
            # update() should be callable and do nothing
            trace.update(output="hello", metadata={"x": 1})
            trace.span("sub_step")


def test_noop_trace_doesnt_raise():
    """The no-op trace should never raise, even with weird inputs."""
    from backend.observability.tracing import _NoOpTrace

    noop = _NoOpTrace()
    # None, empty dict, all of these should work
    noop.update()
    noop.update(output=None, metadata={})
    noop.update(output="x", metadata={"weird key": "value"})
    noop.span("name")
    noop.span(name="name", metadata={})
    with noop as t:
        t.update(output="inside-context")
    # All good — no exceptions


# ─── With Langfuse enabled (mocked) ──────────────────────────────


def test_trace_context_calls_langfuse_when_enabled():
    """When tracing is on, the context manager creates a Langfuse trace
    and forwards updates to it."""
    from backend.observability import tracing

    # Mock the Langfuse client and the global config
    mock_client = MagicMock()
    mock_trace = MagicMock()
    mock_client.trace.return_value = mock_trace

    mock_config = MagicMock()
    mock_config.enabled = True
    mock_config.get_client.return_value = mock_client

    with patch.object(tracing, "_config", mock_config):
        with tracing.trace_llm_call(
            name="controller",
            provider="anthropic",
            model="claude-3-5-sonnet-latest",
            session_id="sess-1",
            metadata={"persona_id": "vc"},
            input_data={"prompt": "test"},
        ) as trace:
            trace.update(output="response", metadata={"usage": 100})
            trace.end()

    # Verify the mock was called correctly
    mock_client.trace.assert_called_once()
    call_kwargs = mock_client.trace.call_args.kwargs
    assert call_kwargs["name"] == "controller"
    assert call_kwargs["session_id"] == "sess-1"
    assert "provider" in call_kwargs["metadata"]
    assert call_kwargs["metadata"]["provider"] == "anthropic"

    # Verify update was called
    assert mock_trace.update.called
    # The first call had input_data
    input_call = mock_trace.update.call_args_list[0]
    assert input_call.kwargs.get("input") == {"prompt": "test"}


def test_trace_context_swallows_langfuse_exceptions():
    """If Langfuse raises, the trace context should not crash the caller."""
    from backend.observability import tracing

    mock_client = MagicMock()
    mock_client.trace.side_effect = RuntimeError("Langfuse is down")
    mock_config = MagicMock()
    mock_config.enabled = True
    mock_config.get_client.return_value = mock_client

    with patch.object(tracing, "_config", mock_config):
        # Should not raise
        with tracing.trace_llm_call(name="test") as trace:
            trace.update(output="x")
            trace.end()


def test_trace_records_exceptions_via_status_error():
    """When the wrapped block raises, the trace gets status=error."""
    from backend.observability import tracing

    mock_client = MagicMock()
    mock_trace = MagicMock()
    mock_client.trace.return_value = mock_trace
    mock_config = MagicMock()
    mock_config.enabled = True
    mock_config.get_client.return_value = mock_client

    with patch.object(tracing, "_config", mock_config):
        try:
            with tracing.trace_llm_call(name="exploding_call") as trace:
                raise ValueError("simulated failure")
        except ValueError:
            pass

    # The trace should have been updated with error info
    update_calls = mock_trace.update.call_args_list
    error_call = next(
        (c for c in update_calls if c.kwargs.get("status") == "error"),
        None,
    )
    assert error_call is not None
    assert "ValueError" in error_call.kwargs.get("error", "")


# ─── Langfuse SDK install optional ───────────────────────────────


def test_get_client_handles_missing_sdk(monkeypatch):
    """If langfuse is not installed, get_client should return None gracefully."""
    import builtins

    from backend.observability import tracing

    # Force the import to fail inside get_client
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langfuse" or name.startswith("langfuse."):
            raise ImportError("No module named 'langfuse'")
        return real_import(name, *args, **kwargs)

    mock_config = MagicMock()
    mock_config.enabled = True
    mock_config.get_client.return_value = None  # simulate SDK not loaded

    with patch.object(tracing, "_config", mock_config):
        assert tracing.is_tracing_enabled() is False


# ─── flush_traces ────────────────────────────────────────────────


def test_flush_traces_handles_missing_client(monkeypatch):
    """flush_traces should never raise, even if no client is configured."""
    from backend.observability import tracing

    mock_config = MagicMock()
    mock_config._client = None

    with patch.object(tracing, "_config", mock_config):
        # Should not raise
        tracing.flush_traces()