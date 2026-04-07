"""Unit tests for the stepped analysis pipeline (Phase 3).

Tests cover:
- AnalysisStep protocol satisfaction
- Each step skips correctly when disabled or context flag is off
- Steps merge partial results via model_copy
- GeocodingStep skips on missing / already-geocoded location
- AnalysisPipeline accumulates results across steps
- build_pipeline returns steps in canonical order
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from picture_analyzer.core.models import (
    AnalysisContext,
    AnalysisResult,
    Enhancement,
    EraInfo,
    GeoLocation,
    ImageData,
    LocationInfo,
    SlideProfileDetection,
)
from picture_analyzer.config.settings import Settings, PipelineConfig, StepConfig
from picture_analyzer.pipeline import AnalysisPipeline, build_pipeline, AnalysisStep
from picture_analyzer.pipeline.steps import (
    MetadataStep,
    LocationStep,
    EnhancementStep,
    SlideProfileStep,
    build_steps,
)
from picture_analyzer.pipeline.geo_step import GeocodingStep


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def image() -> ImageData:
    return ImageData(path=Path("test.jpg"), mime_type="image/jpeg", base64_data="abc123==")


@pytest.fixture
def context() -> AnalysisContext:
    return AnalysisContext(
        language="en",
        detect_location=True,
        recommend_enhancements=True,
        detect_slide_profiles=True,
    )


@pytest.fixture
def empty_result() -> AnalysisResult:
    return AnalysisResult()


@pytest.fixture
def settings_stepped() -> Settings:
    return Settings(
        openai={"api_key": "sk-test"},
        analyzer_provider="openai",
        pipeline={"mode": "stepped"},
    )


def _mock_analyzer_result(**fields) -> AnalysisResult:
    """Build a minimal AnalysisResult with only the given fields set."""
    return AnalysisResult(**fields)


def _step_config() -> dict:
    return {"provider": "openai", "model": "gpt-4o-mini", "max_tokens": 4096, "prompt_template": None}


# ── AnalysisStep Protocol ─────────────────────────────────────────────

class TestAnalysisStepProtocol:
    def test_metadata_step_satisfies_protocol(self):
        step = MetadataStep(config=_step_config())
        assert isinstance(step, AnalysisStep)

    def test_location_step_satisfies_protocol(self):
        step = LocationStep(config=_step_config())
        assert isinstance(step, AnalysisStep)

    def test_enhancement_step_satisfies_protocol(self):
        step = EnhancementStep(config=_step_config())
        assert isinstance(step, AnalysisStep)

    def test_slide_profile_step_satisfies_protocol(self):
        step = SlideProfileStep(config=_step_config())
        assert isinstance(step, AnalysisStep)


# ── MetadataStep ──────────────────────────────────────────────────────

class TestMetadataStep:
    def test_skip_when_disabled(self, image, context, empty_result):
        step = MetadataStep(config=_step_config(), enabled=False)
        result = step.run(image, context, empty_result)
        assert result is empty_result

    def test_merges_fields(self, image, context, empty_result):
        step = MetadataStep(config=_step_config())
        returned = _mock_analyzer_result(
            title="Landscape",
            scene_type="landscape",
            mood="calm",
            keywords=["tree", "sky"],
            people=["woman"],
        )
        with patch.object(step, "_config", _step_config()):
            from picture_analyzer.analyzers.openai import OpenAIAnalyzer
            with patch.object(OpenAIAnalyzer, "analyze_section", return_value=returned):
                result = step.run(image, context, empty_result)
        assert result.title == "Landscape"
        assert result.scene_type == "landscape"
        assert result.mood == "calm"
        assert "tree" in result.keywords


# ── LocationStep ──────────────────────────────────────────────────────

class TestLocationStep:
    def test_skip_when_disabled(self, image, context, empty_result):
        step = LocationStep(config=_step_config(), enabled=False)
        result = step.run(image, context, empty_result)
        assert result is empty_result

    def test_skip_when_context_flag_off(self, image, empty_result):
        ctx = AnalysisContext(detect_location=False)
        step = LocationStep(config=_step_config())
        result = step.run(image, ctx, empty_result)
        assert result is empty_result

    def test_merges_location(self, image, context, empty_result):
        step = LocationStep(config=_step_config())
        loc = LocationInfo(location_name="Amsterdam, Netherlands", country="Netherlands", confidence=85)
        returned = _mock_analyzer_result(location=loc)
        from picture_analyzer.analyzers.openai import OpenAIAnalyzer
        with patch.object(OpenAIAnalyzer, "analyze_section", return_value=returned):
            result = step.run(image, context, empty_result)
        assert result.location is not None
        assert result.location.location_name == "Amsterdam, Netherlands"


# ── EnhancementStep ───────────────────────────────────────────────────

class TestEnhancementStep:
    def test_skip_when_disabled(self, image, context, empty_result):
        step = EnhancementStep(config=_step_config(), enabled=False)
        result = step.run(image, context, empty_result)
        assert result is empty_result

    def test_skip_when_context_flag_off(self, image, empty_result):
        ctx = AnalysisContext(recommend_enhancements=False)
        step = EnhancementStep(config=_step_config())
        result = step.run(image, ctx, empty_result)
        assert result is empty_result

    def test_merges_enhancements(self, image, context, empty_result):
        step = EnhancementStep(config=_step_config())
        enh = Enhancement(action="brightness", raw_text="BRIGHTNESS: increase by 20%")
        returned = _mock_analyzer_result(enhancement_recommendations=[enh])
        from picture_analyzer.analyzers.openai import OpenAIAnalyzer
        with patch.object(OpenAIAnalyzer, "analyze_section", return_value=returned):
            result = step.run(image, context, empty_result)
        assert len(result.enhancement_recommendations) == 1
        assert result.enhancement_recommendations[0].action == "brightness"


# ── SlideProfileStep ──────────────────────────────────────────────────

class TestSlideProfileStep:
    def test_skip_when_disabled(self, image, context, empty_result):
        step = SlideProfileStep(config=_step_config(), enabled=False)
        result = step.run(image, context, empty_result)
        assert result is empty_result

    def test_skip_when_context_flag_off(self, image, empty_result):
        ctx = AnalysisContext(detect_slide_profiles=False)
        step = SlideProfileStep(config=_step_config())
        result = step.run(image, ctx, empty_result)
        assert result is empty_result

    def test_merges_slide_profile(self, image, context, empty_result):
        step = SlideProfileStep(config=_step_config())
        profile = SlideProfileDetection(profile_name="faded", confidence=80)
        returned = _mock_analyzer_result(slide_profile=profile)
        from picture_analyzer.analyzers.openai import OpenAIAnalyzer
        with patch.object(OpenAIAnalyzer, "analyze_section", return_value=returned):
            result = step.run(image, context, empty_result)
        assert result.slide_profile is not None
        assert result.slide_profile.profile_name == "faded"


# ── GeocodingStep ─────────────────────────────────────────────────────

class TestGeocodingStep:
    def test_skip_when_detect_location_false(self, image, settings_stepped, empty_result):
        ctx = AnalysisContext(detect_location=False)
        step = GeocodingStep(settings_stepped)
        result = step.run(image, ctx, empty_result)
        assert result is empty_result

    def test_skip_when_no_location(self, image, context, settings_stepped, empty_result):
        step = GeocodingStep(settings_stepped)
        result = step.run(image, context, empty_result)
        assert result is empty_result

    def test_skip_when_coords_already_present(self, image, context, settings_stepped):
        loc = LocationInfo(
            location_name="Amsterdam",
            confidence=90,
            coordinates=GeoLocation(latitude=52.37, longitude=4.89),
        )
        partial = AnalysisResult(location=loc)
        step = GeocodingStep(settings_stepped)
        result = step.run(image, context, partial)
        assert result is partial

    def test_skip_when_confidence_below_threshold(self, image, context, settings_stepped):
        loc = LocationInfo(location_name="Somewhere", confidence=10)
        partial = AnalysisResult(location=loc)
        step = GeocodingStep(settings_stepped)
        result = step.run(image, context, partial)
        assert result is partial

    def test_resolves_coordinates(self, image, context, settings_stepped):
        loc = LocationInfo(location_name="Amsterdam, Netherlands", confidence=90)
        partial = AnalysisResult(location=loc)
        step = GeocodingStep(settings_stepped)
        coords = GeoLocation(latitude=52.37, longitude=4.89)
        with patch("picture_analyzer.pipeline.geo_step.NominatimGeocoder") as MockGeo:
            MockGeo.return_value.geocode.return_value = coords
            result = step.run(image, context, partial)
        assert result.location is not None
        assert result.location.coordinates == coords

    def test_returns_partial_when_geocoder_returns_none(self, image, context, settings_stepped):
        loc = LocationInfo(location_name="Unknown Place", confidence=90)
        partial = AnalysisResult(location=loc)
        step = GeocodingStep(settings_stepped)
        with patch("picture_analyzer.pipeline.geo_step.NominatimGeocoder") as MockGeo:
            MockGeo.return_value.geocode.return_value = None
            result = step.run(image, context, partial)
        assert result.location.coordinates is None


# ── AnalysisPipeline ──────────────────────────────────────────────────

class TestAnalysisPipeline:
    def test_empty_pipeline_returns_empty_result(self, image, context):
        pipeline = AnalysisPipeline(steps=[])
        result = pipeline.run(image, context)
        assert isinstance(result, AnalysisResult)

    def test_single_step_result_propagated(self, image, context):
        step = MagicMock()
        step.name = "mock"
        step.run.return_value = AnalysisResult(title="Mock Title")
        pipeline = AnalysisPipeline(steps=[step])
        result = pipeline.run(image, context)
        assert result.title == "Mock Title"

    def test_accumulates_across_steps(self, image, context):
        step_a = MagicMock()
        step_a.name = "a"
        step_a.run.side_effect = lambda img, ctx, p: p.model_copy(update={"title": "from_a"})

        step_b = MagicMock()
        step_b.name = "b"
        step_b.run.side_effect = lambda img, ctx, p: p.model_copy(
            update={"scene_type": "from_b", "title": p.title}
        )

        pipeline = AnalysisPipeline(steps=[step_a, step_b])
        result = pipeline.run(image, context)
        assert result.title == "from_a"
        assert result.scene_type == "from_b"

    def test_step_exception_is_skipped(self, image, context):
        bad_step = MagicMock()
        bad_step.name = "bad"
        bad_step.run.side_effect = RuntimeError("boom")
        good_step = MagicMock()
        good_step.name = "good"
        good_step.run.return_value = AnalysisResult(title="good")
        pipeline = AnalysisPipeline(steps=[bad_step, good_step])
        result = pipeline.run(image, context)
        assert result.title == "good"


# ── build_pipeline / build_steps ─────────────────────────────────────

class TestBuildPipeline:
    def test_returns_analysis_pipeline(self, settings_stepped):
        pipeline = build_pipeline(settings_stepped)
        assert isinstance(pipeline, AnalysisPipeline)

    def test_canonical_step_order(self, settings_stepped):
        pipeline = build_pipeline(settings_stepped)
        names = [s.name for s in pipeline._steps]
        assert names == ["metadata", "location", "enhancement", "slide_profiles", "geocoding"]

    def test_disabled_slide_profiles_step(self):
        s = Settings(
            openai={"api_key": "sk-test"},
            analyzer_provider="openai",
            pipeline={"mode": "stepped", "slide_profiles": {"enabled": False}},
        )
        steps = build_steps(s)
        slide_step = next(st for st in steps if st.name == "slide_profiles")
        # Disabled step should pass through unchanged
        result = slide_step.run(
            ImageData(path=Path("x.jpg"), mime_type="image/jpeg", base64_data=""),
            AnalysisContext(),
            AnalysisResult(),
        )
        assert isinstance(result, AnalysisResult)
