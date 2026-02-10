"""Tests for OpenAI analyzer helpers (pure functions).

The ``OpenAIAnalyzer`` class itself requires an API key, but its
helper methods (``_parse_json``, ``_to_analysis_result``) and the
module-level helpers (``_str``, ``_to_list``, ``_join_parts``,
``_extract_action``) are all pure functions that can be tested directly.
"""
from __future__ import annotations

import base64
from unittest.mock import patch

import pytest

from picture_analyzer.analyzers.openai import (
    OpenAIAnalyzer,
    _extract_action,
    _join_parts,
    _str,
    _to_list,
)
from picture_analyzer.core.models import AnalysisContext, ImageData

# ── Module-level helpers ─────────────────────────────────────────────


class TestStr:
    def test_none(self):
        assert _str(None) == ""

    def test_string(self):
        assert _str("hello") == "hello"

    def test_list(self):
        assert _str(["a", "b", "c"]) == "a, b, c"

    def test_number(self):
        assert _str(42) == "42"


class TestToList:
    def test_list_input(self):
        assert _to_list(["a", "b"]) == ["a", "b"]

    def test_string_csv(self):
        assert _to_list("apple, banana, cherry") == ["apple", "banana", "cherry"]

    def test_string_empty(self):
        assert _to_list("") == []

    def test_string_not_detected(self):
        assert _to_list("not detected") == []
        assert _to_list("None") == []
        assert _to_list("unknown") == []

    def test_none(self):
        assert _to_list(None) == []

    def test_int(self):
        assert _to_list(42) == []


class TestJoinParts:
    def test_all_filled(self):
        assert _join_parts("Amsterdam", "Noord-Holland", "Netherlands") == \
               "Amsterdam, Noord-Holland, Netherlands"

    def test_some_empty(self):
        assert _join_parts("", "Noord-Holland", "Netherlands") == \
               "Noord-Holland, Netherlands"

    def test_all_empty(self):
        assert _join_parts("", "", "") == ""

    def test_whitespace_only(self):
        assert _join_parts("  ", "", "NL") == "NL"


class TestExtractAction:
    def test_colon_format(self):
        assert _extract_action("BRIGHTNESS: increase by 10%") == "brightness"
        assert _extract_action("contrast: boost by 15%") == "contrast"

    def test_with_bullet(self):
        assert _extract_action("- brightness: increase by 10%") == "brightness"
        assert _extract_action("* contrast: boost") == "contrast"

    def test_no_colon(self):
        assert _extract_action("no enhancements needed") == "unknown"


# ── OpenAIAnalyzer._parse_json ───────────────────────────────────────


class TestParseJson:
    @pytest.fixture
    def analyzer(self):
        with patch("picture_analyzer.analyzers.openai.OpenAI"):
            return OpenAIAnalyzer(api_key="sk-test")

    def test_json_code_fence(self, analyzer):
        response = '```json\n{"metadata": {"title": "Test"}}\n```'
        result = analyzer._parse_json(response)
        assert result["metadata"]["title"] == "Test"

    def test_plain_code_fence(self, analyzer):
        response = '```\n{"key": "value"}\n```'
        result = analyzer._parse_json(response)
        assert result["key"] == "value"

    def test_raw_json(self, analyzer):
        response = 'Here is the analysis:\n{"metadata": {"scene_type": "landscape"}}'
        result = analyzer._parse_json(response)
        assert result["metadata"]["scene_type"] == "landscape"

    def test_invalid_json(self, analyzer):
        response = "This is not JSON at all"
        result = analyzer._parse_json(response)
        assert "raw_response" in result

    def test_nested_json(self, analyzer):
        response = (
            '```json\n'
            '{"metadata": {"objects": ["tree", "sky"]},'
            ' "enhancement": {}}\n```'
        )
        result = analyzer._parse_json(response)
        assert result["metadata"]["objects"] == ["tree", "sky"]

    def test_malformed_json_fallback(self, analyzer):
        response = '{"key": missing_quotes}'
        result = analyzer._parse_json(response)
        assert "raw_response" in result


# ── OpenAIAnalyzer._to_analysis_result ──────────────────────────────


class TestToAnalysisResult:
    @pytest.fixture
    def analyzer(self):
        with patch("picture_analyzer.analyzers.openai.OpenAI"):
            return OpenAIAnalyzer(api_key="sk-test")

    @pytest.fixture
    def image_data(self, tmp_path):
        img = tmp_path / "test.jpg"
        img.write_bytes(b"\xff\xd8" + b"\x00" * 20)
        return ImageData(path=img, mime_type="image/jpeg")

    @pytest.fixture
    def context(self):
        return AnalysisContext(language="en")

    def test_full_response(self, analyzer, image_data, context):
        raw = {
            "metadata": {
                "scene_type": "Family gathering",
                "location_setting": "A sunny garden",
                "objects": ["table", "chairs"],
                "persons": ["John", "Jane"],
                "mood_atmosphere": "happy",
                "photography_style": "casual",
            },
            "enhancement": {
                "recommended_enhancements": [
                    "BRIGHTNESS: increase by 10%",
                    "CONTRAST: boost by 5%",
                ],
            },
            "location_detection": {
                "country": "Netherlands",
                "region": "Zeeland",
                "city_or_area": "Goes",
                "confidence": 75,
            },
            "slide_profiles": [
                {"profile": "faded", "confidence": 80},
            ],
        }
        result = analyzer._to_analysis_result(raw, image_data, context)
        assert result.title == "Family gathering"
        assert "table" in result.keywords
        assert "John" in result.people
        assert result.location is not None
        assert result.location.country == "Netherlands"
        assert result.location.confidence == 75
        assert result.slide_profile.profile_name == "faded"
        assert len(result.enhancement_recommendations) == 2

    def test_minimal_response(self, analyzer, image_data, context):
        raw = {"metadata": {}}
        result = analyzer._to_analysis_result(raw, image_data, context)
        assert result.title == ""
        assert result.location is None
        assert result.slide_profile is None
        assert result.enhancement_recommendations == []

    def test_empty_response(self, analyzer, image_data, context):
        raw = {}
        result = analyzer._to_analysis_result(raw, image_data, context)
        assert isinstance(result, type(result))  # didn't crash

    def test_era_extraction(self, analyzer, image_data, context):
        raw = {
            "metadata": {
                "time_of_day": "afternoon",
                "season_date": "summer",
            }
        }
        result = analyzer._to_analysis_result(raw, image_data, context)
        assert result.era is not None
        assert result.era.time_of_day == "afternoon"
        assert result.era.season == "summer"

    def test_source_path_set(self, analyzer, image_data, context):
        raw = {"metadata": {}}
        result = analyzer._to_analysis_result(raw, image_data, context)
        assert result.source_path == image_data.path
        assert result.analyzer_model == analyzer.model


# ── OpenAIAnalyzer._encode ──────────────────────────────────────────


class TestEncode:
    def test_encode_file(self, tmp_path):
        with patch("picture_analyzer.analyzers.openai.OpenAI"):
            analyzer = OpenAIAnalyzer(api_key="sk-test")

        content = b"fake image data"
        img = tmp_path / "test.jpg"
        img.write_bytes(content)

        encoded = analyzer._encode(img)
        assert base64.b64decode(encoded) == content
