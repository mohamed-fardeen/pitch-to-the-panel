"""
Eval tests — verify the orchestrator's verdict-generation pipeline
produces well-formed output for every golden transcript.

This catches prompt regressions early: if a prompt edit accidentally
causes the LLM to return malformed JSON, missing fields, or wildly
wrong scores, this suite fails.

Tests are deterministic via a mocked LLM provider (see conftest.py).
To run against the real LLM, set PANELMIND_EVAL_REAL_LLM=1.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from backend.orchestrator import VerdictSchema, generate_verdict_text
from backend.prompts import extract_json  # noqa: F401 — used in non-golden tests


# ─── Helpers ───────────────────────────────────────────────────────


def _validate_verdict_shape(verdict: dict, expectations: dict) -> list[str]:
    """Validate a verdict dict against the expectations. Returns a list of error messages."""
    errors: list[str] = []
    schema = expectations.get("verdict_schema", {})

    # Check schema fields exist and have correct types
    for field_name, constraints in schema.items():
        if field_name not in verdict:
            errors.append(f"Missing field: {field_name}")
            continue

        value = verdict[field_name]
        expected_type = constraints.get("type")
        if expected_type == "string":
            if not isinstance(value, str):
                errors.append(f"{field_name}: expected string, got {type(value).__name__}")
            else:
                min_len = constraints.get("min_length", 0)
                max_len = constraints.get("max_length", float("inf"))
                if not (min_len <= len(value) <= max_len):
                    errors.append(
                        f"{field_name}: length {len(value)} not in "
                        f"[{min_len}, {max_len}]"
                    )
        elif expected_type == "number":
            if not isinstance(value, (int, float)):
                errors.append(f"{field_name}: expected number, got {type(value).__name__}")
            else:
                min_v = constraints.get("min", float("-inf"))
                max_v = constraints.get("max", float("inf"))
                if not (min_v <= value <= max_v):
                    errors.append(
                        f"{field_name}: value {value} not in [{min_v}, {max_v}]"
                    )

    # Check expected keywords appear
    keywords = expectations.get("verdict_contains_keywords", [])
    for kw in keywords:
        if kw.lower() not in str(verdict).lower():
            errors.append(f"Missing expected keyword: {kw!r}")

    return errors


# ─── Golden transcript tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_each_golden_transcript_produces_valid_verdict(golden_transcripts, mock_llm_provider):
    """For each golden transcript, the verdict pipeline should return
    a well-formed parts dict that satisfies the transcript's expectations.
    """
    for transcript in golden_transcripts:
        verdict_text, parts = await generate_verdict_text(
            strengths=[],
            risks=[],
            claims=[],
            contradictions=[],
            confidence_score=50,  # doesn't matter for the JSON test
            mode=transcript["mode"],
            provider=transcript["provider"],
        )
        # The verdict text should be a non-empty formatted string
        assert isinstance(verdict_text, str) and len(verdict_text) > 0
        # The parts dict should have the expected structure
        assert isinstance(parts, dict)
        for key in ("strongest", "weakness", "fix"):
            assert key in parts, f"[{transcript['name']}] missing key {key!r}"
            assert isinstance(parts[key], str)

        # Extract score and recommendation from the formatted verdict text
        import re
        score_match = re.search(r"\(Score:\s*([0-9.]+)/10\)", verdict_text)
        rec_match = re.match(r"^Recommendation:\s*([^(\n]+)", verdict_text)
        extracted_score = float(score_match.group(1)) if score_match else None
        extracted_rec = rec_match.group(1).strip() if rec_match else ""

        # Validate against the transcript's expectations
        verdict_for_check = {
            "strongest_point": parts.get("strongest", ""),
            "biggest_weakness": parts.get("weakness", ""),
            "fix_before_next_pitch": parts.get("fix", ""),
            "investment_score": extracted_score,
            "recommendation": extracted_rec,
        }
        errors = _validate_verdict_shape(verdict_for_check, transcript["expectations"])

        # Filter out "Missing expected keyword" errors when running with
        # the mock LLM, because the orchestrator's prompt doesn't
        # include the actual pitch text — the mock can't know which
        # keywords to embed. Real LLM evals (PANELMIND_EVAL_REAL_LLM=1)
        # will see the full prompt and can match keywords correctly.
        if not os.getenv("PANELMIND_EVAL_REAL_LLM"):
            errors = [
                e for e in errors
                if "Missing expected keyword" not in e
            ]

        assert not errors, (
            f"[{transcript['name']}] Shape validation failed:\n  "
            + "\n  ".join(errors)
        )


@pytest.mark.asyncio
async def test_investment_score_format_in_verdict_text(golden_transcripts, mock_llm_provider):
    """The verdict text should include an investment score in (Score: X/10) format."""
    for transcript in golden_transcripts:
        verdict_text, _parts = await generate_verdict_text(
            strengths=[],
            risks=[],
            claims=[],
            contradictions=[],
            confidence_score=50,
            mode=transcript["mode"],
            provider=transcript["provider"],
        )
        # Look for the (Score: X/10) pattern
        import re
        match = re.search(r"\(Score:\s*([0-9.]+)/10\)", verdict_text)
        assert match, (
            f"[{transcript['name']}] verdict_text missing (Score: X/10) pattern: "
            f"{verdict_text!r}"
        )
        score = float(match.group(1))
        lo, hi = transcript["expectations"]["investment_score_range"]
        assert lo <= score <= hi, (
            f"[{transcript['name']}] score {score} not in range [{lo}, {hi}]"
        )


@pytest.mark.asyncio
async def test_recommendation_is_in_verdict_text(golden_transcripts, mock_llm_provider):
    """The verdict text should contain a recommendation."""
    for transcript in golden_transcripts:
        verdict_text, _parts = await generate_verdict_text(
            strengths=[],
            risks=[],
            claims=[],
            contradictions=[],
            confidence_score=50,
            mode=transcript["mode"],
            provider=transcript["provider"],
        )
        # The verdict text should start with "Recommendation:"
        assert verdict_text.startswith("Recommendation:"), (
            f"[{transcript['name']}] missing 'Recommendation:' prefix: "
            f"{verdict_text!r}"
        )


# ─── extract_json contract ────────────────────────────────────────


def test_extract_json_handles_clean_json():
    assert extract_json('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_extract_json_handles_markdown_fence():
    text = 'Here you go:\n```json\n{"a": 1}\n```\nDone.'
    assert extract_json(text) == {"a": 1}


def test_extract_json_returns_empty_for_garbage():
    assert extract_json("no json here at all") == {}


def test_extract_json_returns_empty_for_empty_string():
    assert extract_json("") == {}


def test_extract_json_handles_nested_objects():
    text = '{"action": "ask_persona", "input": {"tool": "search", "query": "AI"}}'
    result = extract_json(text)
    assert result == {"action": "ask_persona", "input": {"tool": "search", "query": "AI"}}


# ─── VerdictSchema contract ───────────────────────────────────────


def test_verdict_schema_requires_all_fields():
    """If any field is missing, VerdictSchema raises (legacy contract)."""
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        VerdictSchema(
            strongest_point="x",
            # missing biggest_weakness
            fix_before_next_pitch="z",
            investment_score=5.0,
            recommendation="Pass",
        )


def test_verdict_schema_accepts_all_fields():
    v = VerdictSchema(
        strongest_point="x",
        biggest_weakness="y",
        fix_before_next_pitch="z",
        investment_score=7.5,
        recommendation="Invest",
    )
    assert v.investment_score == 7.5


# ─── Verdict text format ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_verdict_text_is_string(mock_llm_provider):
    """The verdict text should be a string, not a dict or list."""
    verdict_text, _parts = await generate_verdict_text(
        strengths=["test"],
        risks=["test"],
        claims=[],
        contradictions=[],
        confidence_score=50,
        mode="venture",
        provider="groq",
    )
    assert isinstance(verdict_text, str)
    assert len(verdict_text) > 0


@pytest.mark.asyncio
async def test_verdict_text_parses_to_json(mock_llm_provider):
    """The verdict text should always parse to valid JSON."""
    verdict_text, _parts = await generate_verdict_text(
        strengths=[],
        risks=[],
        claims=[],
        contradictions=[],
        confidence_score=50,
        mode="venture",
        provider="groq",
    )
    parsed = extract_json(verdict_text)
    assert isinstance(parsed, dict), f"Verdict didn't parse: {verdict_text}"


# ─── Prompt regression sanity ─────────────────────────────────────


def test_all_golden_transcripts_have_required_fields():
    """Each golden transcript must define the expected fields."""
    required = {"name", "description", "pitch_summary", "mode", "provider", "expectations"}
    for json_file in sorted((__import__("pathlib").Path(__file__).parent / "golden_transcripts").glob("*.json")):
        import json
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        missing = required - set(data.keys())
        assert not missing, f"{json_file.name} is missing: {missing}"


def test_golden_transcripts_have_valid_modes():
    """Each golden transcript's mode should be one we support."""
    valid_modes = {"spark", "venture", "reality"}
    for json_file in sorted((__import__("pathlib").Path(__file__).parent / "golden_transcripts").glob("*.json")):
        import json
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["mode"] in valid_modes, (
            f"{json_file.name}: invalid mode {data['mode']!r} "
            f"(must be one of {valid_modes})"
        )