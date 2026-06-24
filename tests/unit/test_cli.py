"""Tests for the Click-based CLI.

Uses Click's ``CliRunner`` to test the CLI without actually invoking
the legacy modules (they require an OpenAI key).  All legacy imports
are mocked.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from picture_analyzer.cli.app import _resolve_profiles, cli

# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_image(tmp_path: Path) -> Path:
    """Create a tiny JPEG-like file for path-existence checks."""
    img = tmp_path / "photo.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # JFIF header stub
    return img


@pytest.fixture
def fake_dir(tmp_path: Path) -> Path:
    """Create a directory with a few fake images."""
    d = tmp_path / "photos"
    d.mkdir()
    for name in ["img1.jpg", "img2.jpg", "img3.png"]:
        (d / name).write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
    return d


@pytest.fixture
def fake_analysis() -> dict:
    return {
        "metadata": {"title": "Test Photo"},
        "enhancement": {"brightness": 10},
        "slide_profiles": [{"profile": "faded", "confidence": 80}],
    }


@pytest.fixture
def mock_legacy(fake_analysis):
    """Patch ``_get_legacy_modules`` to return mocks."""
    analyzer = MagicMock()
    analyzer.return_value.analyze_and_save.return_value = fake_analysis

    enhancer = MagicMock()
    enhancer.return_value.enhance_from_analysis.return_value = "/out/photo_enhanced.jpg"
    enhancer.return_value.enhance_from_json.return_value = "/out/photo_enhanced.jpg"

    slide = MagicMock()
    slide.restore_slide.return_value = "/out/photo_restored.jpg"
    slide.auto_restore_slide.return_value = "/out/photo_restored.jpg"

    meta = MagicMock()
    meta.return_value.copy_exif.return_value = True

    report = MagicMock()

    modules = (analyzer, enhancer, slide, meta, report)
    with patch("picture_analyzer.cli.app._get_legacy_modules", return_value=modules):
        yield {
            "PictureAnalyzer": analyzer,
            "SmartEnhancer": enhancer,
            "SlideRestoration": slide,
            "MetadataManager": meta,
            "ReportGenerator": report,
        }


@pytest.fixture
def mock_provider_analysis(fake_analysis):
    with patch("picture_analyzer.cli.app._analyze_with_provider") as analyze_mock, \
         patch("picture_analyzer.cli.app._analysis_to_legacy_dict") as to_legacy_mock:
        analyze_mock.return_value = object()
        to_legacy_mock.return_value = fake_analysis
        yield {
            "analyze": analyze_mock,
            "to_legacy": to_legacy_mock,
        }


# ── Root group tests ─────────────────────────────────────────────────


class TestCLIRoot:

    def test_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "AI-powered photo analysis" in result.output

    def test_help_short(self, runner: CliRunner):
        result = runner.invoke(cli, ["-h"])
        assert result.exit_code == 0

    def test_version(self, runner: CliRunner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "picture-analyzer" in result.output

    def test_no_command_shows_help(self, runner: CliRunner):
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "Usage:" in result.output


# ── Analyze command ──────────────────────────────────────────────────


class TestAnalyze:

    def test_analyze_single(self, runner, fake_image, mock_legacy, mock_provider_analysis):
        result = runner.invoke(cli, ["analyze", str(fake_image)])
        assert result.exit_code == 0
        assert "Analyzing:" in result.output
        mock_provider_analysis["analyze"].assert_called_once()

    def test_analyze_with_output(self, runner, fake_image, mock_legacy, mock_provider_analysis, tmp_path):
        out = tmp_path / "results"
        out.mkdir()
        result = runner.invoke(cli, ["analyze", str(fake_image), "-o", str(out)])
        assert result.exit_code == 0

    def test_analyze_no_json(self, runner, fake_image, mock_legacy, mock_provider_analysis):
        result = runner.invoke(cli, ["analyze", str(fake_image), "--no-json"])
        assert result.exit_code == 0
        assert result.exit_code == 0

    def test_analyze_with_provider_override(self, runner, fake_image, mock_legacy, mock_provider_analysis):
        result = runner.invoke(cli, ["analyze", str(fake_image), "--provider", "ollama"])
        assert result.exit_code == 0
        assert "Using analyzer provider: ollama" in result.output

    def test_analyze_with_enhance(self, runner, fake_image, mock_legacy, mock_provider_analysis):
        result = runner.invoke(cli, ["analyze", str(fake_image), "--enhance"])
        assert result.exit_code == 0
        assert "Enhanced" in result.output

    def test_analyze_with_restore(self, runner, fake_image, mock_legacy, mock_provider_analysis, tmp_path):
        result = runner.invoke(cli, [
            "analyze", str(fake_image), "--restore-slide", "auto",
        ])
        assert result.exit_code == 0

    def test_analyze_batch(self, runner, fake_dir, mock_legacy, mock_provider_analysis):
        result = runner.invoke(cli, ["analyze", str(fake_dir), "--batch"])
        assert result.exit_code == 0
        assert "Found" in result.output
        assert "Batch complete" in result.output

    def test_analyze_dir_implies_batch(self, runner, fake_dir, mock_legacy, mock_provider_analysis):
        """Passing a directory without --batch should still work."""
        result = runner.invoke(cli, ["analyze", str(fake_dir)])
        assert result.exit_code == 0
        assert "Batch complete" in result.output

    def test_analyze_nonexistent(self, runner):
        result = runner.invoke(cli, ["analyze", "/no/such/file.jpg"])
        assert result.exit_code != 0

    def test_analyze_help(self, runner):
        result = runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "Analyze a single image" in result.output

    def test_analyze_help_shows_pipeline_mode(self, runner):
        result = runner.invoke(cli, ["analyze", "--help"])
        assert result.exit_code == 0
        assert "pipeline-mode" in result.output


class TestAnalyzePipelineMode:
    """Tests for --pipeline-mode flag and stepped/single branching."""

    def _make_analysis_result(self):
        from picture_analyzer.core.models import AnalysisResult
        from datetime import datetime
        return AnalysisResult(analyzed_at=datetime.now())

    def test_single_mode_uses_legacy_path(self, runner, fake_image, mock_legacy):
        """--pipeline-mode single must call _build_analyzer path, not pipeline."""
        with patch("picture_analyzer.cli.app._build_analyzer") as build_mock, \
             patch("picture_analyzer.cli.app._analysis_to_legacy_dict") as to_legacy_mock:
            analyzer = MagicMock()
            analyzer.analyze.return_value = self._make_analysis_result()
            build_mock.return_value = analyzer
            to_legacy_mock.return_value = {"metadata": {}, "enhancement": {}}

            result = runner.invoke(cli, ["analyze", str(fake_image), "--pipeline-mode", "single"])
            assert result.exit_code == 0
            build_mock.assert_called_once()
            analyzer.analyze.assert_called_once()

    def test_stepped_mode_uses_pipeline(self, runner, fake_image, mock_legacy):
        """--pipeline-mode stepped must use AnalysisPipeline, not _build_analyzer."""
        analysis_result = self._make_analysis_result()
        with patch("picture_analyzer.pipeline.build_pipeline") as bp_mock, \
             patch("picture_analyzer.cli.app._analysis_to_legacy_dict") as to_legacy_mock:
            pipeline = MagicMock()
            pipeline.run.return_value = analysis_result
            bp_mock.return_value = pipeline
            to_legacy_mock.return_value = {"metadata": {}, "enhancement": {}}

            result = runner.invoke(cli, ["analyze", str(fake_image), "--pipeline-mode", "stepped"])
            assert result.exit_code == 0
            bp_mock.assert_called_once()
            pipeline.run.assert_called_once()

    def test_stepped_mode_via_env(self, runner, fake_image, mock_legacy):
        """PA_PIPELINE__MODE=stepped env var activates stepped pipeline."""
        analysis_result = self._make_analysis_result()
        with patch("picture_analyzer.pipeline.build_pipeline") as bp_mock, \
             patch("picture_analyzer.cli.app._analysis_to_legacy_dict") as to_legacy_mock, \
             patch("picture_analyzer.cli.app.get_settings") as gs_mock:
            settings = MagicMock()
            settings.pipeline.mode = "stepped"
            settings.geo.provider = "none"
            settings.metadata.language = "en"
            settings.prompt.detect_slide_profiles = True
            settings.prompt.recommend_enhancements = True
            settings.prompt.detect_location = True
            settings.prompt.custom_instructions = None
            gs_mock.return_value = settings

            pipeline = MagicMock()
            pipeline.run.return_value = analysis_result
            bp_mock.return_value = pipeline
            to_legacy_mock.return_value = {"metadata": {}, "enhancement": {}}

            result = runner.invoke(cli, ["analyze", str(fake_image)])
            assert result.exit_code == 0
            bp_mock.assert_called_once()

    def test_default_mode_is_single(self, runner, fake_image, mock_legacy):
        """Without --pipeline-mode, single mode is used by default."""
        with patch("picture_analyzer.cli.app._build_analyzer") as build_mock, \
             patch("picture_analyzer.cli.app._analysis_to_legacy_dict") as to_legacy_mock, \
             patch("picture_analyzer.cli.app.get_settings") as gs_mock:
            settings = MagicMock()
            settings.pipeline.mode = "single"
            settings.geo.provider = "none"
            settings.metadata.language = "en"
            settings.prompt.detect_slide_profiles = True
            settings.prompt.recommend_enhancements = True
            settings.prompt.detect_location = True
            settings.prompt.custom_instructions = None
            gs_mock.return_value = settings

            analyzer = MagicMock()
            analyzer.analyze.return_value = self._make_analysis_result()
            build_mock.return_value = analyzer
            to_legacy_mock.return_value = {"metadata": {}, "enhancement": {}}

            result = runner.invoke(cli, ["analyze", str(fake_image)])
            assert result.exit_code == 0
            build_mock.assert_called_once()

    def test_pipeline_mode_override_beats_config(self, runner, fake_image, mock_legacy):
        """CLI --pipeline-mode=single overrides config mode=stepped."""
        with patch("picture_analyzer.cli.app._build_analyzer") as build_mock, \
             patch("picture_analyzer.cli.app._analysis_to_legacy_dict") as to_legacy_mock, \
             patch("picture_analyzer.cli.app.get_settings") as gs_mock:
            settings = MagicMock()
            settings.pipeline.mode = "stepped"  # config says stepped
            settings.geo.provider = "none"
            settings.metadata.language = "en"
            settings.prompt.detect_slide_profiles = True
            settings.prompt.recommend_enhancements = True
            settings.prompt.detect_location = True
            settings.prompt.custom_instructions = None
            gs_mock.return_value = settings

            analyzer = MagicMock()
            analyzer.analyze.return_value = self._make_analysis_result()
            build_mock.return_value = analyzer
            to_legacy_mock.return_value = {"metadata": {}, "enhancement": {}}

            # CLI flag --pipeline-mode single should win
            result = runner.invoke(
                cli, ["analyze", str(fake_image), "--pipeline-mode", "single"]
            )
            assert result.exit_code == 0
            build_mock.assert_called_once()

    def test_stepped_batch_uses_pipeline(self, runner, fake_dir, mock_legacy):
        """Batch mode with --pipeline-mode stepped calls pipeline for each image."""
        analysis_result = self._make_analysis_result()
        with patch("picture_analyzer.pipeline.build_pipeline") as bp_mock, \
             patch("picture_analyzer.cli.app._analysis_to_legacy_dict") as to_legacy_mock:
            pipeline = MagicMock()
            pipeline.run.return_value = analysis_result
            bp_mock.return_value = pipeline
            to_legacy_mock.return_value = {"metadata": {}, "enhancement": {}}

            result = runner.invoke(
                cli, ["analyze", str(fake_dir), "--batch", "--pipeline-mode", "stepped"]
            )
            assert result.exit_code == 0
            assert pipeline.run.call_count >= 1


# ── Process command ──────────────────────────────────────────────────


class TestProcess:

    def test_process_basic(self, runner, fake_image, mock_legacy, mock_provider_analysis):
        result = runner.invoke(cli, ["process", str(fake_image)])
        assert result.exit_code == 0
        assert "Analyzing:" in result.output
        assert "Enhancing" in result.output

    def test_process_with_restore(self, runner, fake_image, mock_legacy, mock_provider_analysis):
        result = runner.invoke(cli, [
            "process", str(fake_image), "--restore-slide", "faded",
        ])
        assert result.exit_code == 0
        assert "Restoring slide" in result.output

    def test_process_with_provider_override(self, runner, fake_image, mock_legacy, mock_provider_analysis):
        result = runner.invoke(cli, ["process", str(fake_image), "--provider", "ollama"])
        assert result.exit_code == 0
        assert "Using analyzer provider: ollama" in result.output

    def test_process_help(self, runner):
        result = runner.invoke(cli, ["process", "--help"])
        assert result.exit_code == 0


# ── Report / Gallery commands ────────────────────────────────────────


class TestReportGallery:

    def test_report(self, runner, fake_dir, mock_legacy):
        result = runner.invoke(cli, ["report", str(fake_dir)])
        assert result.exit_code == 0
        assert "Report saved" in result.output

    def test_gallery(self, runner, fake_dir, mock_legacy):
        result = runner.invoke(cli, ["gallery", str(fake_dir)])
        assert result.exit_code == 0
        assert "Gallery saved" in result.output

    def test_report_custom_output(self, runner, fake_dir, mock_legacy, tmp_path):
        out = tmp_path / "my_report.md"
        result = runner.invoke(cli, ["report", str(fake_dir), "-o", str(out)])
        assert result.exit_code == 0


# ── Legacy commands ──────────────────────────────────────────────────


class TestLegacyCommands:

    def test_batch_delegates(self, runner, fake_dir, mock_legacy, mock_provider_analysis):
        result = runner.invoke(cli, ["batch", str(fake_dir)])
        assert result.exit_code == 0
        assert "analyze DIR --batch" in result.output  # tip message

    def test_enhance_with_analysis(self, runner, fake_image, mock_legacy, tmp_path):
        json_path = tmp_path / f"{fake_image.stem}_analyzed.json"
        json_path.write_text(json.dumps({"enhancement": {}}))
        result = runner.invoke(cli, [
            "enhance", str(fake_image), "-a", str(json_path),
        ])
        assert result.exit_code == 0
        assert "Enhanced" in result.output

    def test_enhance_no_analysis_fails(self, runner, fake_image, mock_legacy):
        result = runner.invoke(cli, ["enhance", str(fake_image)])
        assert result.exit_code != 0
        assert "Analysis file not found" in result.output

    def test_restore_slide_explicit_profile(self, runner, fake_image, mock_legacy):
        result = runner.invoke(cli, [
            "restore-slide", str(fake_image), "-p", "faded",
        ])
        assert result.exit_code == 0


# ── Config command ───────────────────────────────────────────────────


class TestConfig:

    def test_config_shows_json(self, runner, monkeypatch):
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
        monkeypatch.delenv("METADATA_LANGUAGE", raising=False)
        monkeypatch.delenv("GPS_CONFIDENCE_THRESHOLD", raising=False)
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        monkeypatch.delenv("OPENAI_APIKEY", raising=False)
        result = runner.invoke(cli, ["config"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "openai" in data
        assert "metadata" in data


# ── Helpers ──────────────────────────────────────────────────────────


class TestResolveProfiles:

    def test_explicit_profile(self):
        assert _resolve_profiles("faded", {}) == ["faded"]

    def test_auto_with_suggestions(self):
        analysis = {
            "slide_profiles": [
                {"profile": "faded", "confidence": 80},
                {"profile": "red_cast", "confidence": 60},
                {"profile": "aged", "confidence": 30},  # all applied regardless of confidence
            ]
        }
        result = _resolve_profiles("auto", analysis)
        assert result == ["faded", "red_cast", "aged"]

    def test_auto_no_profiles(self):
        assert _resolve_profiles("auto", {}) == ["auto"]

    def test_auto_all_low_confidence(self):
        analysis = {
            "slide_profiles": [
                {"profile": "faded", "confidence": 10},
            ]
        }
        assert _resolve_profiles("auto", analysis) == ["faded"]


# ── description.txt ground-truth gate (batch mode) ────────────────────


class TestAnalyzeDescriptionGate:
    """Folder-level description.txt location/date gate in batch mode.

    When a folder has a description.txt, location/date are read with the same
    methods as update_location.py and used as ground truth (overriding the
    LLM). Folders whose description.txt lacks a parseable location/date are
    skipped.
    """

    @staticmethod
    def _make_album(tmp_path: Path, desc_text: str, n_images: int = 2) -> Path:
        d = tmp_path / "album"
        d.mkdir()
        (d / "description.txt").write_text(desc_text, encoding="utf-8")
        for i in range(n_images):
            (d / f"img{i + 1}.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
        return d

    def test_skips_folder_when_location_missing(
        self, runner, tmp_path, mock_legacy, mock_provider_analysis
    ):
        d = self._make_album(tmp_path, "Albumnaam: 1984-06 Test\nDatum: Juni 1984\n")
        out = tmp_path / "out"
        out.mkdir()
        result = runner.invoke(cli, ["analyze", str(d), "--batch", "-o", str(out)])
        assert result.exit_code == 0
        assert "Skipping folder" in result.output
        assert "description.txt location/date incomplete" in result.output
        assert list(out.glob("*_analyzed.json")) == []

    def test_skips_folder_when_date_unparseable(
        self, runner, tmp_path, mock_legacy, mock_provider_analysis
    ):
        d = self._make_album(tmp_path, "Locatie: Wien, Austria\nDatum: zomer 1984\n")
        out = tmp_path / "out"
        out.mkdir()
        result = runner.invoke(cli, ["analyze", str(d), "--batch", "-o", str(out)])
        assert result.exit_code == 0
        assert "Skipping folder" in result.output
        assert "could not parse date" in result.output
        assert list(out.glob("*_analyzed.json")) == []

    def test_override_location_and_date_without_gps(
        self, runner, tmp_path, mock_legacy, mock_provider_analysis
    ):
        d = self._make_album(
            tmp_path,
            "Albumnaam: 1984-06 Test\nLocatie: Pruggern, Steiermark, Austria\nDatum: Juni 1984\n",
        )
        out = tmp_path / "out"
        out.mkdir()
        with patch("picture_analyzer.cli.app._geocode_location_str", return_value=None):
            result = runner.invoke(cli, ["analyze", str(d), "--batch", "-o", str(out)])
        assert result.exit_code == 0
        assert "Batch complete" in result.output

        jsons = sorted(out.glob("*_analyzed.json"))
        assert len(jsons) == 2

        first = json.loads(jsons[0].read_text())
        assert first["location_detection"] == {
            "country": "Austria",
            "region": "Steiermark",
            "city_or_area": "Pruggern",
            "confidence": 100,
            "reasoning": "Set from description.txt",
        }
        assert first["date_taken"] == "1984-06-01 00:00:00"
        assert "gps_coordinates" not in first

        second = json.loads(jsons[1].read_text())
        # date_taken increments by 1 second per image (same as update_location.py)
        assert second["date_taken"] == "1984-06-01 00:00:01"

    def test_override_includes_gps_when_geocoded(
        self, runner, tmp_path, mock_legacy, mock_provider_analysis
    ):
        d = self._make_album(
            tmp_path, "Locatie: Wien, Austria\nDatum: 13 mei 1991\n", n_images=1
        )
        out = tmp_path / "out"
        out.mkdir()
        coords = {
            "latitude": 48.2082,
            "longitude": 16.3738,
            "display_name": "Wien, Austria",
        }
        with patch("picture_analyzer.cli.app._geocode_location_str", return_value=coords):
            result = runner.invoke(cli, ["analyze", str(d), "--batch", "-o", str(out)])
        assert result.exit_code == 0
        jsons = list(out.glob("*_analyzed.json"))
        assert len(jsons) == 1
        data = json.loads(jsons[0].read_text())
        assert data["gps_coordinates"]["latitude"] == 48.2082
        assert data["gps_coordinates"]["longitude"] == 16.3738
        assert data["date_taken"] == "1991-05-13 00:00:00"
        assert data["location_detection"]["city_or_area"] == "Wien"

    def test_no_description_txt_proceeds_normally(
        self, runner, tmp_path, mock_legacy, mock_provider_analysis
    ):
        """A folder without description.txt is not gated (normal LLM flow)."""
        d = tmp_path / "plain"
        d.mkdir()
        (d / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
        out = tmp_path / "out"
        out.mkdir()
        result = runner.invoke(cli, ["analyze", str(d), "--batch", "-o", str(out)])
        assert result.exit_code == 0
        assert "Batch complete" in result.output
        assert list(out.glob("*_analyzed.json"))

    def test_disables_llm_location_when_ground_truth_ok(
        self, runner, tmp_path, mock_legacy, mock_provider_analysis
    ):
        """When description.txt provides location/date, the LLM location step is skipped."""
        d = self._make_album(
            tmp_path, "Locatie: Wien, Austria\nDatum: Juni 1984\n", n_images=1
        )
        out = tmp_path / "out"
        out.mkdir()
        with patch("picture_analyzer.cli.app._geocode_location_str", return_value=None):
            result = runner.invoke(cli, ["analyze", str(d), "--batch", "-o", str(out)])
        assert result.exit_code == 0
        analyze_mock = mock_provider_analysis["analyze"]
        assert analyze_mock.call_args.kwargs.get("detect_location") is False

    def test_keeps_llm_location_when_no_description_txt(
        self, runner, tmp_path, mock_legacy, mock_provider_analysis
    ):
        """Without description.txt the LLM location step is not disabled."""
        d = tmp_path / "plain"
        d.mkdir()
        (d / "photo.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 50)
        out = tmp_path / "out"
        out.mkdir()
        result = runner.invoke(cli, ["analyze", str(d), "--batch", "-o", str(out)])
        assert result.exit_code == 0
        analyze_mock = mock_provider_analysis["analyze"]
        # detect_location left at None → settings default applies (LLM location runs)
        assert analyze_mock.call_args.kwargs.get("detect_location") is None

    def test_skip_existing_resumes_date_taken_sequence(
        self, runner, tmp_path, mock_legacy, mock_provider_analysis
    ):
        """--skip-existing continues date_taken after the last stored timestamp."""
        d = self._make_album(
            tmp_path, "Locatie: Wien, Austria\nDatum: Juni 1984\n", n_images=2
        )
        out = tmp_path / "out"
        out.mkdir()
        # Pretend img1 was already processed with date_taken 00:00:05 (must be a
        # "complete" analysis: >=200 bytes with non-empty metadata)
        existing = {
            "metadata": {
                "scene_type": "already processed",
                "objects": ["tree", "building", "person"],
                "persons": "Not detected",
                "weather": "sunny",
                "mood_atmosphere": "calm",
            },
            "enhancement": {"recommended_enhancements": []},
            "location_detection": {"city_or_area": "Wien", "country": "Austria"},
            "date_taken": "1984-06-01 00:00:05",
        }
        (out / "img1_analyzed.json").write_text(json.dumps(existing), encoding="utf-8")
        with patch("picture_analyzer.cli.app._geocode_location_str", return_value=None):
            result = runner.invoke(
                cli, ["analyze", str(d), "--batch", "--skip-existing", "-o", str(out)]
            )
        assert result.exit_code == 0
        assert "Resuming" in result.output
        # img1 skipped; img2 continues from 00:00:06 (not 00:00:00)
        img2 = json.loads((out / "img2_analyzed.json").read_text())
        assert img2["date_taken"] == "1984-06-01 00:00:06"
