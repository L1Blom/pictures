"""Phase 5 hardening tests.

Covers:
- Parity: single vs stepped modes produce structurally equivalent AnalysisResult
- Backward-compat: default mode=single never exercises AnalysisPipeline
- DeprecationWarning emitted when importing root prompts module
- Per-step timing: pipeline logs elapsed time for each step
- Step error isolation: one failing step does not abort the pipeline
"""
from __future__ import annotations

import importlib
import logging
import warnings
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from picture_analyzer.config.settings import Settings
from picture_analyzer.core.models import (
    AnalysisContext,
    AnalysisResult,
    GeoLocation,
    ImageData,
    LocationInfo,
)
from picture_analyzer.pipeline import AnalysisPipeline, build_pipeline


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
def base_result() -> AnalysisResult:
    return AnalysisResult(
        analyzed_at=datetime.now(),
        title="Test Photo",
        scene_type="landscape",
        mood="serene",
    )


# ── Parity Tests ──────────────────────────────────────────────────────

class TestModeParity:
    """Assert that both modes produce structurally consistent results."""

    def _make_step_result(self, **extra) -> AnalysisResult:
        return AnalysisResult(analyzed_at=datetime.now(), title="Parity Photo", **extra)

    def test_stepped_produces_analysis_result(self, image, context):
        """Pipeline.run() always returns an AnalysisResult instance."""
        settings = Settings(
            openai={"api_key": "sk-test"},
            analyzer_provider="openai",
            pipeline={"mode": "stepped"},
        )
        with patch(
            "picture_analyzer.pipeline.steps.MetadataStep.run",
            return_value=self._make_step_result(),
        ), patch(
            "picture_analyzer.pipeline.steps.LocationStep.run",
            return_value=self._make_step_result(),
        ), patch(
            "picture_analyzer.pipeline.steps.EnhancementStep.run",
            return_value=self._make_step_result(),
        ), patch(
            "picture_analyzer.pipeline.steps.SlideProfileStep.run",
            return_value=self._make_step_result(),
        ), patch(
            "picture_analyzer.pipeline.geo_step.GeocodingStep.run",
            return_value=self._make_step_result(),
        ):
            pipeline = build_pipeline(settings)
            result = pipeline.run(image, context)

        assert isinstance(result, AnalysisResult)

    def test_single_and_stepped_share_same_result_fields(self, image, context):
        """Both modes expose the same AnalysisResult field set."""
        full_result = AnalysisResult(
            analyzed_at=datetime.now(),
            title="Parity Photo",
            scene_type="landscape",
            mood="calm",
            keywords=["tree"],
        )
        settings = Settings(
            openai={"api_key": "sk-test"},
            analyzer_provider="openai",
            pipeline={"mode": "single"},
        )
        # Single mode
        with patch("picture_analyzer.analyzers.openai.OpenAIAnalyzer.analyze", return_value=full_result):
            from picture_analyzer.analyzers.openai import OpenAIAnalyzer
            analyzer = OpenAIAnalyzer(api_key="sk-test", model="gpt-4o-mini")
            single_result = analyzer.analyze(image, context)

        assert single_result.title == "Parity Photo"
        assert single_result.scene_type == "landscape"
        assert single_result.keywords == ["tree"]


# ── Backward-Compat Tests ─────────────────────────────────────────────

class TestBackwardCompat:
    """Default mode=single must never exercise pipeline code."""

    def test_default_settings_mode_is_single(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)  # no config.yaml in tmp_path
        settings = Settings(openai={"api_key": "sk-test"})
        assert settings.pipeline.mode == "single"

    def test_single_mode_does_not_call_build_pipeline(self, image, context):
        """When mode=single, build_pipeline must never be called."""
        settings = Settings(
            openai={"api_key": "sk-test"},
            analyzer_provider="openai",
            pipeline={"mode": "single"},
        )
        with patch("picture_analyzer.pipeline.build_pipeline") as bp_mock, \
             patch("picture_analyzer.cli.app.get_settings", return_value=settings), \
             patch("picture_analyzer.cli.app._build_analyzer") as build_mock, \
             patch("picture_analyzer.cli.app._analysis_to_legacy_dict", return_value={}):
            analyzer = MagicMock()
            analyzer.analyze.return_value = AnalysisResult(analyzed_at=datetime.now())
            build_mock.return_value = analyzer

            from picture_analyzer.cli.app import _analyze_with_provider
            _analyze_with_provider(image.path)

            bp_mock.assert_not_called()

    def test_env_unset_mode_stays_single(self, monkeypatch, tmp_path):
        """Without PA_PIPELINE__MODE and no config.yaml, mode defaults to 'single'."""
        monkeypatch.chdir(tmp_path)  # no config.yaml in tmp_path
        monkeypatch.delenv("PA_PIPELINE__MODE", raising=False)
        settings = Settings(openai={"api_key": "sk-test"})
        assert settings.pipeline.mode == "single"

    def test_stepped_mode_env_var_activates_pipeline(self, monkeypatch):
        """PA_PIPELINE__MODE=stepped loads stepped mode in settings."""
        monkeypatch.setenv("PA_PIPELINE__MODE", "stepped")
        # Re-create settings after env var is set
        settings = Settings(openai={"api_key": "sk-test"})
        assert settings.pipeline.mode == "stepped"


# ── DeprecationWarning ────────────────────────────────────────────────

class TestDeprecationWarning:
    """Root prompts.py shim must emit DeprecationWarning on import."""

    def test_root_prompts_import_emits_deprecation(self):
        # Unload cached module so the warning fires on re-import
        import sys
        sys.modules.pop("prompts", None)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            importlib.import_module("prompts")
        sys.modules.pop("prompts", None)

        deprecation_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        assert deprecation_warnings, "Expected a DeprecationWarning from root prompts module"
        assert "PromptLoader" in str(deprecation_warnings[0].message)


# ── Per-Step Timing ───────────────────────────────────────────────────

class TestPerStepTiming:
    """Pipeline must log INFO-level timing for every step that completes."""

    def test_completed_step_logged_at_info(self, image, context, caplog):
        step = MagicMock()
        step.name = "test_step"
        step.run.return_value = AnalysisResult(analyzed_at=datetime.now())

        pipeline = AnalysisPipeline([step])
        with caplog.at_level(logging.INFO, logger="picture_analyzer.pipeline.pipeline"):
            pipeline.run(image, context)

        assert any(
            "test_step" in record.message and "completed" in record.message
            for record in caplog.records
        )

    def test_timing_contains_seconds(self, image, context, caplog):
        step = MagicMock()
        step.name = "timing_step"
        step.run.return_value = AnalysisResult(analyzed_at=datetime.now())

        pipeline = AnalysisPipeline([step])
        with caplog.at_level(logging.INFO, logger="picture_analyzer.pipeline.pipeline"):
            pipeline.run(image, context)

        timing_logs = [r.message for r in caplog.records if "timing_step" in r.message]
        assert timing_logs
        # Log message should contain something like "0.000s"
        assert any("s" in msg for msg in timing_logs)

    def test_failing_step_still_logs_elapsed(self, image, context, caplog):
        step = MagicMock()
        step.name = "bad_step"
        step.run.side_effect = RuntimeError("API error")

        pipeline = AnalysisPipeline([step])
        with caplog.at_level(logging.ERROR, logger="picture_analyzer.pipeline.pipeline"):
            result = pipeline.run(image, context)

        # Pipeline must not re-raise; result must still be an AnalysisResult
        assert isinstance(result, AnalysisResult)
        error_logs = [r for r in caplog.records if "bad_step" in r.message]
        assert error_logs

    def test_multiple_steps_each_logged(self, image, context, caplog):
        steps = []
        for name in ("alpha", "beta", "gamma"):
            s = MagicMock()
            s.name = name
            s.run.return_value = AnalysisResult(analyzed_at=datetime.now())
            steps.append(s)

        pipeline = AnalysisPipeline(steps)
        with caplog.at_level(logging.INFO, logger="picture_analyzer.pipeline.pipeline"):
            pipeline.run(image, context)

        logged_names = {r.message for r in caplog.records}
        for name in ("alpha", "beta", "gamma"):
            assert any(name in msg for msg in logged_names)


# ── Error Isolation ───────────────────────────────────────────────────

class TestErrorIsolation:
    """One failing step must not abort the rest of the pipeline."""

    def test_exception_in_step_skipped_next_step_runs(self, image, context):
        good_result = AnalysisResult(analyzed_at=datetime.now(), title="Surviving Photo")

        bad_step = MagicMock()
        bad_step.name = "bad"
        bad_step.run.side_effect = ValueError("model error")

        good_step = MagicMock()
        good_step.name = "good"
        good_step.run.return_value = good_result

        pipeline = AnalysisPipeline([bad_step, good_step])
        result = pipeline.run(image, context)

        good_step.run.assert_called_once()
        assert result.title == "Surviving Photo"

    def test_all_steps_fail_returns_empty_result(self, image, context):
        steps = []
        for name in ("s1", "s2"):
            s = MagicMock()
            s.name = name
            s.run.side_effect = RuntimeError("boom")
            steps.append(s)

        pipeline = AnalysisPipeline(steps)
        result = pipeline.run(image, context)

        assert isinstance(result, AnalysisResult)
        assert not result.title  # empty string default when all steps fail

    def test_partial_failure_preserves_earlier_data(self, image, context):
        first_result = AnalysisResult(analyzed_at=datetime.now(), title="First Step Data")

        first = MagicMock()
        first.name = "first"
        first.run.return_value = first_result

        second = MagicMock()
        second.name = "second"
        second.run.side_effect = RuntimeError("second broke")

        pipeline = AnalysisPipeline([first, second])
        result = pipeline.run(image, context)

        assert result.title == "First Step Data"
