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

    def test_analyze_single(self, runner, fake_image, mock_legacy):
        result = runner.invoke(cli, ["analyze", str(fake_image)])
        assert result.exit_code == 0
        assert "Analyzing:" in result.output
        mock_legacy["PictureAnalyzer"].return_value.analyze_and_save.assert_called_once()

    def test_analyze_with_output(self, runner, fake_image, mock_legacy, tmp_path):
        out = tmp_path / "results"
        out.mkdir()
        result = runner.invoke(cli, ["analyze", str(fake_image), "-o", str(out)])
        assert result.exit_code == 0

    def test_analyze_no_json(self, runner, fake_image, mock_legacy):
        result = runner.invoke(cli, ["analyze", str(fake_image), "--no-json"])
        assert result.exit_code == 0
        call_kwargs = (
            mock_legacy["PictureAnalyzer"]
            .return_value.analyze_and_save.call_args
        )
        assert (
            call_kwargs[1].get("save_json") is False
            or call_kwargs[0][2] is False
        )

    def test_analyze_with_enhance(self, runner, fake_image, mock_legacy):
        result = runner.invoke(cli, ["analyze", str(fake_image), "--enhance"])
        assert result.exit_code == 0
        assert "Enhanced" in result.output

    def test_analyze_with_restore(self, runner, fake_image, mock_legacy, tmp_path):
        result = runner.invoke(cli, [
            "analyze", str(fake_image), "--restore-slide", "auto",
        ])
        assert result.exit_code == 0

    def test_analyze_batch(self, runner, fake_dir, mock_legacy):
        result = runner.invoke(cli, ["analyze", str(fake_dir), "--batch"])
        assert result.exit_code == 0
        assert "Found" in result.output
        assert "Batch complete" in result.output

    def test_analyze_dir_implies_batch(self, runner, fake_dir, mock_legacy):
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


# ── Process command ──────────────────────────────────────────────────


class TestProcess:

    def test_process_basic(self, runner, fake_image, mock_legacy):
        result = runner.invoke(cli, ["process", str(fake_image)])
        assert result.exit_code == 0
        assert "Analyzing:" in result.output
        assert "Enhancing" in result.output

    def test_process_with_restore(self, runner, fake_image, mock_legacy):
        result = runner.invoke(cli, [
            "process", str(fake_image), "--restore-slide", "faded",
        ])
        assert result.exit_code == 0
        assert "Restoring slide" in result.output

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

    def test_batch_delegates(self, runner, fake_dir, mock_legacy):
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
                {"profile": "aged", "confidence": 30},  # below threshold
            ]
        }
        result = _resolve_profiles("auto", analysis)
        assert result == ["faded", "red_cast"]

    def test_auto_no_profiles(self):
        assert _resolve_profiles("auto", {}) == ["auto"]

    def test_auto_all_low_confidence(self):
        analysis = {
            "slide_profiles": [
                {"profile": "faded", "confidence": 10},
            ]
        }
        assert _resolve_profiles("auto", analysis) == ["auto"]
