"""Tests for the slide restoration module.

Uses small PIL test images and typed SlideProfile models.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from picture_analyzer.core.models import (
    AnalysisResult,
    ColorBalance,
    SlideProfile,
    SlideProfileDetection,
)
from picture_analyzer.enhancers.profiles.slide_restorer import SlideRestorer

# ── Helpers ──────────────────────────────────────────────────────────


def _make_jpeg(path: Path, size: tuple[int, int] = (60, 60)) -> Path:
    img = Image.new("RGB", size, color=(180, 120, 90))
    img.save(str(path), "JPEG", quality=75)
    return path


def _make_profile(**overrides) -> SlideProfile:
    defaults = dict(
        name="test",
        description="Test profile",
        brightness=1.0,
        contrast=1.0,
        saturation=1.0,
        sharpness=1.0,
        denoise=False,
        denoise_radius=0.5,
        color_balance=ColorBalance(red=1.0, green=1.0, blue=1.0),
    )
    defaults.update(overrides)
    return SlideProfile(**defaults)


# ══════════════════════════════════════════════════════════════════════
# Constructor
# ══════════════════════════════════════════════════════════════════════


class TestSlideRestorerInit:
    def test_default_profiles_loaded(self):
        sr = SlideRestorer()
        assert len(sr.available_profiles) > 0
        assert "aged" in sr.available_profiles

    def test_custom_profiles(self):
        custom = {"my_profile": _make_profile(description="Custom")}
        sr = SlideRestorer(profiles=custom)
        assert sr.available_profiles == ["my_profile"]

    def test_available_profiles_sorted(self):
        profiles = {
            "z_profile": _make_profile(),
            "a_profile": _make_profile(),
            "m_profile": _make_profile(),
        }
        sr = SlideRestorer(profiles=profiles)
        assert sr.available_profiles == ["a_profile", "m_profile", "z_profile"]


# ══════════════════════════════════════════════════════════════════════
# Profile access
# ══════════════════════════════════════════════════════════════════════


class TestProfileAccess:
    def test_get_profile_existing(self):
        sr = SlideRestorer(profiles={"test": _make_profile()})
        p = sr.get_profile("test")
        assert p is not None
        assert p.description == "Test profile"

    def test_get_profile_missing(self):
        sr = SlideRestorer(profiles={"test": _make_profile()})
        assert sr.get_profile("nonexistent") is None

    def test_add_profile(self):
        sr = SlideRestorer(profiles={})
        sr.add_profile("new", _make_profile(description="New one"))
        p = sr.get_profile("new")
        assert p is not None
        assert p.description == "New one"


# ══════════════════════════════════════════════════════════════════════
# Restore
# ══════════════════════════════════════════════════════════════════════


class TestRestore:
    @pytest.fixture
    def jpeg(self, tmp_path: Path) -> Path:
        return _make_jpeg(tmp_path / "slide.jpg")

    def test_basic_restore(self, jpeg, tmp_path):
        profile = _make_profile(brightness=1.1, contrast=1.2, saturation=1.1)
        sr = SlideRestorer(profiles={"test": profile, "aged": profile})
        out = tmp_path / "restored.jpg"
        result = sr.restore(jpeg, "test", out)
        assert result == str(out)
        assert out.exists()
        # Verify output is a valid JPEG
        img = Image.open(str(out))
        assert img.mode == "RGB"

    def test_restore_inplace(self, jpeg):
        profile = _make_profile()
        sr = SlideRestorer(profiles={"test": profile, "aged": profile})
        result = sr.restore(jpeg, "test")
        assert result == str(jpeg)

    def test_restore_unknown_profile_falls_back_to_aged(self, jpeg, tmp_path):
        aged = _make_profile(description="Aged fallback")
        sr = SlideRestorer(profiles={"aged": aged})
        out = tmp_path / "out.jpg"
        result = sr.restore(jpeg, "nonexistent", out)
        assert result == str(out)

    def test_restore_with_color_balance(self, jpeg, tmp_path):
        cb = ColorBalance(red=0.9, green=1.0, blue=1.1)
        profile = _make_profile(color_balance=cb)
        sr = SlideRestorer(profiles={"color": profile, "aged": profile})
        out = tmp_path / "out.jpg"
        result = sr.restore(jpeg, "color", out)
        assert result is not None

    def test_restore_with_denoise(self, jpeg, tmp_path):
        profile = _make_profile(denoise=True, denoise_radius=1.0)
        sr = SlideRestorer(profiles={"dn": profile, "aged": profile})
        out = tmp_path / "out.jpg"
        result = sr.restore(jpeg, "dn", out)
        assert result is not None

    def test_restore_no_despeckle(self, jpeg, tmp_path):
        profile = _make_profile()
        sr = SlideRestorer(profiles={"test": profile, "aged": profile})
        out = tmp_path / "out.jpg"
        result = sr.restore(jpeg, "test", out, despeckle=False)
        assert result is not None

    def test_restore_invalid_path_returns_none(self, tmp_path):
        sr = SlideRestorer(profiles={"aged": _make_profile()})
        result = sr.restore(tmp_path / "no_such_file.jpg", "aged")
        assert result is None


# ══════════════════════════════════════════════════════════════════════
# Auto-restore
# ══════════════════════════════════════════════════════════════════════


class TestAutoRestore:
    @pytest.fixture
    def jpeg(self, tmp_path: Path) -> Path:
        return _make_jpeg(tmp_path / "slide.jpg")

    @pytest.fixture
    def restorer(self) -> SlideRestorer:
        profiles = {
            "aged": _make_profile(description="aged"),
            "faded": _make_profile(description="faded"),
            "red_cast": _make_profile(description="red_cast"),
        }
        return SlideRestorer(profiles=profiles)

    def test_from_analysis_result(self, jpeg, tmp_path, restorer):
        analysis = AnalysisResult(
            slide_profile=SlideProfileDetection(
                profile_name="faded", confidence=90,
            ),
        )
        out = tmp_path / "out.jpg"
        result = restorer.auto_restore(
            jpeg, analysis_result=analysis, output_path=out,
        )
        assert result == str(out)

    def test_from_legacy_dict(self, jpeg, tmp_path, restorer):
        data = {
            "slide_profiles": [
                {"profile": "red_cast", "confidence": 80},
            ],
        }
        out = tmp_path / "out.jpg"
        result = restorer.auto_restore(jpeg, analysis_data=data, output_path=out)
        assert result == str(out)

    def test_heuristic_fallback(self, jpeg, tmp_path, restorer):
        data = {
            "enhancement": {
                "color_analysis": {
                    "color_temperature": "warm",
                    "detected_color_casts": "yellowish tone",
                    "saturation_level": "normal",
                },
            },
        }
        out = tmp_path / "out.jpg"
        result = restorer.auto_restore(jpeg, analysis_data=data, output_path=out)
        assert result is not None

    def test_no_data_defaults_to_aged(self, jpeg, tmp_path, restorer):
        out = tmp_path / "out.jpg"
        result = restorer.auto_restore(jpeg, output_path=out)
        assert result == str(out)


# ══════════════════════════════════════════════════════════════════════
# Heuristic assessment
# ══════════════════════════════════════════════════════════════════════


class TestHeuristicAssess:
    @pytest.fixture
    def restorer(self) -> SlideRestorer:
        return SlideRestorer(profiles={
            "aged": _make_profile(),
            "red_cast": _make_profile(),
            "yellow_cast": _make_profile(),
            "color_cast": _make_profile(),
            "faded": _make_profile(),
            "well_preserved": _make_profile(),
        })

    def test_detects_red_cast(self, restorer):
        data = {
            "enhancement": {
                "color_analysis": {
                    "detected_color_casts": "magenta / reddish tint",
                    "color_temperature": "warm",
                },
            },
        }
        result = restorer._heuristic_assess(data)
        assert result["recommended_profile"] == "red_cast"
        assert "red_cast" in result["characteristics"]

    def test_detects_yellow_cast(self, restorer):
        data = {
            "enhancement": {
                "color_analysis": {
                    "detected_color_casts": "slight yellow",
                    "color_temperature": "warm sepia tones",
                },
            },
        }
        result = restorer._heuristic_assess(data)
        assert result["recommended_profile"] == "yellow_cast"

    def test_detects_cool_cast(self, restorer):
        data = {
            "enhancement": {
                "color_analysis": {
                    "detected_color_casts": "cyan shift",
                    "color_temperature": "cool",
                },
            },
        }
        result = restorer._heuristic_assess(data)
        assert result["recommended_profile"] == "color_cast"

    def test_well_preserved(self, restorer):
        data = {
            "enhancement": {
                "color_analysis": {
                    "detected_color_casts": "none",
                    "color_temperature": "neutral",
                    "saturation_level": "vibrant",
                },
            },
        }
        result = restorer._heuristic_assess(data)
        assert result["recommended_profile"] == "well_preserved"
        assert result["condition"] == "well_preserved"

    def test_empty_enhancement(self, restorer):
        result = restorer._heuristic_assess({})
        # No enhancement data → defaults to aged initial, but no characteristics
        # means the code path sets "well_preserved"
        assert result["recommended_profile"] in ("aged", "well_preserved")

    def test_non_dict_enhancement(self, restorer):
        result = restorer._heuristic_assess({"enhancement": "string"})
        assert result["recommended_profile"] == "aged"
