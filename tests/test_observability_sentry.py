"""
Tests for the Sentry integration (backend/observability/sentry.py).
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from backend.observability import sentry as sentry_module
from backend.observability.sentry import (
    capture_exception,
    capture_message,
    is_sentry_enabled,
)


# ─── Disabled state ──────────────────────────────────────────────


def test_is_sentry_enabled_returns_false_when_no_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert is_sentry_enabled() is False


def test_is_sentry_enabled_returns_true_when_dsn_set(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/123")
    assert is_sentry_enabled() is True


def test_capture_exception_noop_when_disabled(monkeypatch):
    """Without SENTRY_DSN, capture_exception should be a no-op."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    # Should not raise
    capture_exception(ValueError("test"))


def test_capture_message_noop_when_disabled(monkeypatch):
    """Without SENTRY_DSN, capture_message should be a no-op."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    capture_message("test message")


# ─── Enabled state (mocked) ───────────────────────────────────────


def test_capture_exception_calls_sentry_sdk(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/123")
    mock_sdk = MagicMock()
    mock_scope = MagicMock()
    mock_sdk.push_scope.return_value.__enter__.return_value = mock_scope

    with patch.dict("sys.modules", {"sentry_sdk": mock_sdk}):
        # We need to patch the import in the sentry module
        with patch.object(sentry_module, "is_sentry_enabled", return_value=True):
            capture_exception(ValueError("boom"), context={"session_id": "s1"})

    # Verify the exception was captured
    mock_sdk.capture_exception.assert_called_once()
    # Verify the context was set
    mock_scope.set_extra.assert_any_call("session_id", "s1")


def test_capture_message_calls_sentry_sdk(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/123")
    mock_sdk = MagicMock()
    mock_scope = MagicMock()
    mock_sdk.push_scope.return_value.__enter__.return_value = mock_scope

    with patch.object(sentry_module, "is_sentry_enabled", return_value=True):
        with patch.dict("sys.modules", {"sentry_sdk": mock_sdk}):
            capture_message("test alert", level="warning", context={"user_id": "u1"})

    mock_sdk.capture_message.assert_called_once()
    call_args = mock_sdk.capture_message.call_args
    assert call_args.args[0] == "test alert"
    assert call_args.kwargs.get("level") == "warning"
    mock_scope.set_extra.assert_any_call("user_id", "u1")


def test_capture_exception_swallows_sdk_errors(monkeypatch):
    """If Sentry SDK raises, capture_exception should not crash the caller."""
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/123")
    mock_sdk = MagicMock()
    mock_sdk.push_scope.side_effect = RuntimeError("Sentry is down")

    with patch.object(sentry_module, "is_sentry_enabled", return_value=True):
        with patch.dict("sys.modules", {"sentry_sdk": mock_sdk}):
            # Should not raise
            capture_exception(ValueError("boom"))


def test_init_sentry_returns_none_when_disabled(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    assert sentry_module.init_sentry() is None


def test_init_sentry_handles_missing_sdk(monkeypatch):
    """If sentry-sdk is not installed, init should return None gracefully."""
    monkeypatch.setenv("SENTRY_DSN", "https://fake@sentry.io/123")

    # Force the sentry_sdk import to fail
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sentry_sdk" or name.startswith("sentry_sdk."):
            raise ImportError("No module named 'sentry_sdk'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        # Should not raise, should return None
        result = sentry_module.init_sentry()
        assert result is None