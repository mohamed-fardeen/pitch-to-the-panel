"""
Tests for the multi-language translation endpoint (Tier-1e).

Verifies:
- GET /api/languages returns the supported language list
- POST /api/translate handles each supported language
- English-to-English is a passthrough (no LLM call)
- Unsupported languages return 400
- Empty / missing fields return 422 (Pydantic validation)
- Network/LLM errors fall back to returning the original text
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ─── GET /api/languages ────────────────────────────────────────────


def test_languages_endpoint_returns_supported_list(client):
    r = client.get("/api/languages")
    assert r.status_code == 200
    data = r.json()
    assert "languages" in data
    codes = {lang["code"] for lang in data["languages"]}
    assert "en" in codes
    assert "es" in codes
    assert "hi" in codes
    assert "zh" in codes


def test_languages_endpoint_includes_names(client):
    r = client.get("/api/languages")
    data = r.json()
    en = next(lang for lang in data["languages"] if lang["code"] == "en")
    assert en["name"] == "English"


def test_languages_list_is_sorted(client):
    r = client.get("/api/languages")
    codes = [lang["code"] for lang in r.json()["languages"]]
    assert codes == sorted(codes)


# ─── POST /api/translate ───────────────────────────────────────────


def test_translate_english_to_english_is_passthrough(client):
    """Translating to English returns the input unchanged with no LLM call."""
    pitch = "We are building an AI CRM for dentists."
    with patch("services.llm.llm_provider") as mock_provider:
        # Should not be called for en→en
        r = client.post(
            "/api/translate",
            json={"text": pitch, "target_language": "en"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["translated_text"] == pitch
        assert data["target_language"] == "en"
        assert data["model"] == "passthrough"
        # LLM was not called
        mock_provider.generate_response.assert_not_called()


def test_translate_to_spanish_calls_llm(client):
    """Translating to Spanish hits the LLM provider and returns its result."""
    pitch = "We are building an AI CRM."
    with patch("services.llm.llm_provider") as mock_provider:
        mock_provider.generate_response = AsyncMock(
            return_value="Estamos construyendo un CRM de IA."
        )
        r = client.post(
            "/api/translate",
            json={"text": pitch, "target_language": "es"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["translated_text"] == "Estamos construyendo un CRM de IA."
        assert data["target_language"] == "es"
        assert data["source_language"] == "auto"
        # LLM was called
        mock_provider.generate_response.assert_called_once()
        call_args = mock_provider.generate_response.call_args
        # The user prompt should include the original text and the target language
        assert pitch in call_args.kwargs["user_prompt"]
        assert "Spanish" in call_args.kwargs["user_prompt"]


def test_translate_to_hindi_calls_llm(client):
    with patch("services.llm.llm_provider") as mock_provider:
        mock_provider.generate_response = AsyncMock(
            return_value="हम एक AI CRM बना रहे हैं।"
        )
        r = client.post(
            "/api/translate",
            json={"text": "We are building an AI CRM.", "target_language": "hi"},
        )
        assert r.status_code == 200
        assert "Hindi" in mock_provider.generate_response.call_args.kwargs["user_prompt"]


def test_translate_unsupported_language_returns_400(client):
    r = client.post(
        "/api/translate",
        json={"text": "Hello", "target_language": "klingon"},
    )
    assert r.status_code == 400
    assert "klingon" in r.json()["detail"]


def test_translate_empty_text_returns_422(client):
    r = client.post(
        "/api/translate",
        json={"text": "", "target_language": "es"},
    )
    assert r.status_code == 422  # Pydantic validation


def test_translate_missing_text_returns_422(client):
    r = client.post(
        "/api/translate",
        json={"target_language": "es"},
    )
    assert r.status_code == 422


def test_translate_missing_language_returns_422(client):
    r = client.post(
        "/api/translate",
        json={"text": "Hello"},
    )
    assert r.status_code == 422


def test_translate_too_long_text_returns_422(client):
    r = client.post(
        "/api/translate",
        json={"text": "x" * 10_000, "target_language": "es"},
    )
    assert r.status_code == 422


def test_translate_case_insensitive_language_code(client):
    """Language codes are case-insensitive ('ES' should work the same as 'es')."""
    with patch("services.llm.llm_provider") as mock_provider:
        mock_provider.generate_response = AsyncMock(return_value="Hola")
        r = client.post(
            "/api/translate",
            json={"text": "Hello", "target_language": "ES"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["target_language"] == "es"


def test_translate_falls_back_on_llm_error(client):
    """If the LLM raises, return the original text with model='fallback'."""
    with patch("services.llm.llm_provider") as mock_provider:
        mock_provider.generate_response = AsyncMock(
            side_effect=RuntimeError("LLM down")
        )
        pitch = "We are building an AI CRM."
        r = client.post(
            "/api/translate",
            json={"text": pitch, "target_language": "es"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["translated_text"] == pitch  # original returned
        assert data["model"] == "fallback"
        assert "error" in data


def test_translate_uses_provided_provider(client):
    with patch("services.llm.llm_provider") as mock_provider:
        mock_provider.generate_response = AsyncMock(return_value="Bonjour")
        r = client.post(
            "/api/translate",
            json={
                "text": "Hello",
                "target_language": "fr",
                "provider": "anthropic",
            },
        )
        assert r.status_code == 200
        call_args = mock_provider.generate_response.call_args
        assert call_args.kwargs["provider"] == "anthropic"


def test_translate_preserves_brand_names_and_technical_terms(client):
    """The prompt should instruct the model to preserve brand names + tech terms."""
    with patch("services.llm.llm_provider") as mock_provider:
        mock_provider.generate_response = AsyncMock(return_value="translated")
        client.post(
            "/api/translate",
            json={"text": "Test", "target_language": "de"},
        )
        call_args = mock_provider.generate_response.call_args
        prompt = call_args.kwargs["user_prompt"]
        # The system prompt should mention preserving terms
        system = call_args.kwargs["system_prompt"]
        assert "preserve" in system.lower() or "preserve" in prompt.lower()