"""
Tests for the existing `extract_json` function and `VerdictSchema`.

These cover the LLM-output-parsing logic that the verdict-generation code
relies on. They're known to be fragile — that's exactly why they're
important to test.
"""

from __future__ import annotations

import pytest

from backend.orchestrator import VerdictSchema
from backend.prompts import extract_json


class TestExtractJson:
    """Tests for the JSON extractor used by the controller and verdict nodes."""

    def test_extracts_clean_json(self):
        text = '{"action": "ask_persona", "target": "vc"}'
        assert extract_json(text) == {"action": "ask_persona", "target": "vc"}

    def test_extracts_from_markdown_fence(self):
        text = '```json\n{"action": "ask_pitcher"}\n```'
        assert extract_json(text) == {"action": "ask_pitcher"}

    def test_extracts_from_prose_with_preamble(self):
        text = 'Here is my decision: {"action": "reflect", "reason": "low confidence"}'
        assert extract_json(text) == {"action": "reflect", "reason": "low confidence"}

    def test_extracts_first_of_multiple_objects(self):
        # We want the first valid JSON, not the last
        text = '{"action": "ask_persona"} some text {"action": "ask_pitcher"}'
        assert extract_json(text) == {"action": "ask_persona"}

    def test_handles_nested_objects(self):
        text = '{"action": "ask_persona", "input": {"tool": "search", "query": "AI"}}'
        result = extract_json(text)
        assert result == {"action": "ask_persona", "input": {"tool": "search", "query": "AI"}}

    def test_returns_empty_dict_on_garbage(self):
        assert extract_json("no json here at all") == {}

    def test_returns_empty_dict_on_empty(self):
        assert extract_json("") == {}

    def test_returns_empty_dict_on_partial_json(self):
        assert extract_json('{"action": "ask_p') == {}

    def test_returns_dict_not_list(self):
        # If the LLM returns a top-level array, we should not mistake it for a dict
        result = extract_json('["a", "b"]')
        assert result == {}


class TestVerdictSchema:
    """Tests for the structured verdict output.

    NOTE: The legacy `VerdictSchema` (backend/orchestrator.py:73) requires ALL
    fields. There are no defaults. This is a known design choice — the schema
    is only ever populated from a fully-formed LLM output. Tests reflect this.
    """

    def test_valid_verdict_parses(self):
        raw = {
            "strongest_point": "Strong team",
            "biggest_weakness": "No moat",
            "fix_before_next_pitch": "Build network effects",
            "investment_score": 7.5,
            "recommendation": "Conditional",
        }
        verdict = VerdictSchema(**raw)
        assert verdict.investment_score == 7.5
        assert verdict.recommendation == "Conditional"

    def test_all_fields_required(self):
        # Missing any single field raises ValidationError
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            VerdictSchema(
                # missing strongest_point
                biggest_weakness="No moat",
                fix_before_next_pitch="Build network effects",
                investment_score=7.5,
                recommendation="Conditional",
            )

    def test_recommendation_is_free_text(self):
        # The schema doesn't restrict recommendation to specific values — it's
        # free text. Verify we don't accidentally constrain it.
        verdict = VerdictSchema(
            strongest_point="x",
            biggest_weakness="y",
            fix_before_next_pitch="z",
            investment_score=5.0,
            recommendation="I'll get back to you in 6 weeks",
        )
        assert "6 weeks" in verdict.recommendation