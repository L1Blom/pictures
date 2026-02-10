"""Tests that cover pipeline parser branches and the enhance_image convenience
function — gaps not covered by the original test_filters.py.

test_filters.py already covers:
  brightness, contrast, color_temperature, color_channel parse branches,
  FilterPipeline (empty, single, chaining, order, repr),
  basic filter behaviours (brightness, saturation, color_channel).

This file covers:
  unsharp_mask, shadows/highlights, vibrance, clarity, saturation,
  sharpness parser branches,
  parse_from_analysis(),
  enhance_image() convenience function,
  advanced filter behaviours (ColorTemperatureFilter, ShadowsHighlightsFilter,
  VibranceFilter, ClarityFilter).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from picture_analyzer.core.models import AnalysisResult
from picture_analyzer.enhancers.filters.advanced import (
    ClarityFilter,
    ColorTemperatureFilter,
    ShadowsHighlightsFilter,
    VibranceFilter,
)
from picture_analyzer.enhancers.pipeline import (
    RecommendationParser,
    enhance_image,
)

# ── Helpers ──────────────────────────────────────────────────────────


@pytest.fixture
def parser() -> RecommendationParser:
    return RecommendationParser()


@pytest.fixture
def small_image() -> Image.Image:
    return Image.new("RGB", (20, 20), (128, 100, 80))


def _make_jpeg(path: Path) -> Path:
    img = Image.new("RGB", (30, 30), (128, 100, 80))
    img.save(str(path), "JPEG", quality=80)
    return path


# ══════════════════════════════════════════════════════════════════════
# Parser branches (previously untested)
# ══════════════════════════════════════════════════════════════════════


class TestParserUnsharpMask:
    def test_unsharp_mask_basic(self, parser):
        pipeline = parser.parse(
            ["UNSHARP_MASK: radius=2.0, strength=120%, threshold=3"]
        )
        names = [f.name for f in pipeline.filters]
        assert "UnsharpMask" in names

    def test_unsharp_mask_defaults(self, parser):
        pipeline = parser.parse(
            ["UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0"]
        )
        names = [f.name for f in pipeline.filters]
        assert "UnsharpMask" in names

    def test_unsharp_mask_partial_params(self, parser):
        pipeline = parser.parse(["UNSHARP_MASK: radius=1.0"])
        assert len(pipeline) >= 1


class TestParserShadowsHighlights:
    def test_shadows_brighten(self, parser):
        pipeline = parser.parse(["SHADOWS: brighten by 20%"])
        names = [f.name for f in pipeline.filters]
        assert "ShadowsHighlights" in names

    def test_highlights_darken(self, parser):
        pipeline = parser.parse(["HIGHLIGHTS: darken by 15%"])
        names = [f.name for f in pipeline.filters]
        assert "ShadowsHighlights" in names


class TestParserVibrance:
    def test_vibrance_increase(self, parser):
        pipeline = parser.parse(["VIBRANCE: increase by 25%"])
        names = [f.name for f in pipeline.filters]
        assert "Vibrance" in names


class TestParserClarity:
    def test_clarity_boost(self, parser):
        pipeline = parser.parse(["CLARITY: boost by 30%"])
        names = [f.name for f in pipeline.filters]
        assert "Clarity" in names


class TestParserSaturation:
    def test_saturation_increase(self, parser):
        pipeline = parser.parse(["SATURATION: increase by 20%"])
        names = [f.name for f in pipeline.filters]
        assert "Saturation" in names


class TestParserSharpness:
    def test_sharpness_enhance(self, parser):
        pipeline = parser.parse(["SHARPNESS: enhance by 15%"])
        names = [f.name for f in pipeline.filters]
        assert "Sharpness" in names

    def test_sharpen_keyword(self, parser):
        pipeline = parser.parse(["sharpen: boost by 10%"])
        names = [f.name for f in pipeline.filters]
        assert "Sharpness" in names


# ══════════════════════════════════════════════════════════════════════
# parse_from_analysis
# ══════════════════════════════════════════════════════════════════════


class TestParseFromAnalysis:
    def test_from_analysis_result(self, parser):
        analysis = AnalysisResult(
            raw_response={
                "enhancement": {
                    "recommended_enhancements": [
                        "BRIGHTNESS: increase by 10%",
                        "CONTRAST: boost by 15%",
                    ],
                },
            },
        )
        pipeline = parser.parse_from_analysis(analysis)
        assert len(pipeline) >= 2

    def test_from_analysis_with_string_recommendations(self, parser):
        analysis = AnalysisResult(
            raw_response={
                "enhancement": {
                    "recommended_enhancements": (
                        "BRIGHTNESS: increase by 10%\n"
                        "CONTRAST: boost by 15%"
                    ),
                },
            },
        )
        pipeline = parser.parse_from_analysis(analysis)
        assert len(pipeline) >= 2

    def test_from_analysis_empty(self, parser):
        analysis = AnalysisResult()
        pipeline = parser.parse_from_analysis(analysis)
        assert len(pipeline) == 0

    def test_from_analysis_dict_recommendation(self, parser):
        analysis = AnalysisResult(
            raw_response={
                "enhancement": {
                    "recommended_enhancements": {
                        "action": "BRIGHTNESS: increase by 20%"
                    },
                },
            },
        )
        pipeline = parser.parse_from_analysis(analysis)
        assert len(pipeline) >= 1


# ══════════════════════════════════════════════════════════════════════
# enhance_image convenience function
# ══════════════════════════════════════════════════════════════════════


class TestEnhanceImage:
    def test_basic_enhancement(self, tmp_path):
        jpeg = _make_jpeg(tmp_path / "test.jpg")
        out = tmp_path / "out.jpg"
        result = enhance_image(
            str(jpeg),
            ["BRIGHTNESS: increase by 10%"],
            output_path=str(out),
        )
        assert result == str(out)
        assert out.exists()

    def test_no_recommendations(self, tmp_path):
        jpeg = _make_jpeg(tmp_path / "test.jpg")
        result = enhance_image(str(jpeg), [])
        assert result is None

    def test_invalid_path(self, tmp_path):
        result = enhance_image(
            str(tmp_path / "nope.jpg"),
            ["BRIGHTNESS: increase by 10%"],
        )
        assert result is None

    def test_overwrite_source(self, tmp_path):
        jpeg = _make_jpeg(tmp_path / "test.jpg")
        result = enhance_image(str(jpeg), ["CONTRAST: boost by 20%"])
        assert result == str(jpeg)


# ══════════════════════════════════════════════════════════════════════
# Advanced filter behaviours
# ══════════════════════════════════════════════════════════════════════


class TestColorTemperatureFilterBehaviour:
    def test_warm_shift(self, small_image):
        f = ColorTemperatureFilter(kelvin=7000)  # warm
        result = f.apply(small_image)
        px = result.getpixel((10, 10))
        # Warm → red boosted relative to blue
        orig = small_image.getpixel((10, 10))
        assert px[0] >= orig[0]  # red same or increased
        # Blue should be reduced
        assert px[2] <= orig[2]

    def test_cool_shift(self, small_image):
        f = ColorTemperatureFilter(kelvin=3000)  # cool
        result = f.apply(small_image)
        px = result.getpixel((10, 10))
        orig = small_image.getpixel((10, 10))
        assert px[2] >= orig[2]  # blue same or increased

    def test_name(self):
        f = ColorTemperatureFilter(kelvin=5500)
        assert f.name == "ColorTemperature"


class TestShadowsHighlightsFilterBehaviour:
    def test_brighten_shadows(self):
        # Create an image with dark (shadow) pixels
        img = Image.new("RGB", (10, 10), (30, 30, 30))
        f = ShadowsHighlightsFilter(shadow_adjust=50.0, highlight_adjust=0.0)
        result = f.apply(img)
        px = result.getpixel((5, 5))
        # Shadows should be brightened
        assert px[0] > 30

    def test_darken_highlights(self):
        # Create an image with bright (highlight) pixels
        img = Image.new("RGB", (10, 10), (220, 220, 220))
        f = ShadowsHighlightsFilter(shadow_adjust=0.0, highlight_adjust=-30.0)
        result = f.apply(img)
        px = result.getpixel((5, 5))
        assert px[0] < 220

    def test_name(self):
        f = ShadowsHighlightsFilter()
        assert f.name == "ShadowsHighlights"


class TestVibranceFilterBehaviour:
    def test_boost_vibrance(self, small_image):
        f = VibranceFilter(factor=1.5)
        result = f.apply(small_image)
        assert result.mode == "RGB"
        assert result.size == small_image.size

    def test_no_change(self, small_image):
        f = VibranceFilter(factor=1.0)
        result = f.apply(small_image)
        # With factor 1.0, pixels should be (near-)identical
        orig_px = small_image.getpixel((10, 10))
        new_px = result.getpixel((10, 10))
        for o, n in zip(orig_px[:3], new_px[:3]):
            assert abs(o - n) <= 1

    def test_name(self):
        f = VibranceFilter()
        assert f.name == "Vibrance"


class TestClarityFilterBehaviour:
    def test_applies(self, small_image):
        f = ClarityFilter(strength=30.0)
        result = f.apply(small_image)
        assert result.size == small_image.size

    def test_name(self):
        f = ClarityFilter()
        assert f.name == "Clarity"
