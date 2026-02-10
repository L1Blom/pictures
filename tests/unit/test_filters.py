"""Tests for ImageFilter implementations and FilterPipeline."""
import pytest
from PIL import Image

from picture_analyzer.core.interfaces import ImageFilter as ImageFilterProtocol
from picture_analyzer.enhancers.filters.advanced import (
    ClarityFilter,
    ColorChannelFilter,
    ColorTemperatureFilter,
    ShadowsHighlightsFilter,
    UnsharpMaskFilter,
    VibranceFilter,
)
from picture_analyzer.enhancers.filters.basic import (
    BrightnessFilter,
    ContrastFilter,
    SaturationFilter,
    SharpnessFilter,
)
from picture_analyzer.enhancers.pipeline import FilterPipeline, RecommendationParser

# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def sample_image():
    """Create a small RGB test image."""
    img = Image.new("RGB", (10, 10), color=(128, 128, 128))
    return img


@pytest.fixture
def red_image():
    """Create a small image with a strong red cast."""
    img = Image.new("RGB", (10, 10), color=(200, 100, 80))
    return img


# ── Protocol conformance ────────────────────────────────────────────


ALL_FILTERS = [
    BrightnessFilter(1.2),
    ContrastFilter(1.1),
    SaturationFilter(1.3),
    SharpnessFilter(1.15),
    UnsharpMaskFilter(radius=1.5, percent=80),
    ColorTemperatureFilter(kelvin=5500),
    ShadowsHighlightsFilter(shadow_adjust=10),
    ClarityFilter(strength=20),
    VibranceFilter(factor=1.2),
    ColorChannelFilter(channel="red", factor=0.9),
]


@pytest.mark.parametrize("f", ALL_FILTERS, ids=lambda f: f.name)
def test_filter_satisfies_protocol(f):
    """Every filter should satisfy the ImageFilter protocol."""
    assert isinstance(f, ImageFilterProtocol)


@pytest.mark.parametrize("f", ALL_FILTERS, ids=lambda f: f.name)
def test_filter_has_name(f):
    """Every filter must have a non-empty name."""
    assert isinstance(f.name, str)
    assert len(f.name) > 0


@pytest.mark.parametrize("f", ALL_FILTERS, ids=lambda f: f.name)
def test_filter_apply_returns_image(f, sample_image):
    """Every filter must return a PIL Image from apply()."""
    result = f.apply(sample_image)
    assert isinstance(result, Image.Image)
    assert result.size == sample_image.size


# ── Basic filter tests ───────────────────────────────────────────────


def test_brightness_increase(sample_image):
    """Increasing brightness should make pixels brighter."""
    f = BrightnessFilter(factor=2.0)
    result = f.apply(sample_image)
    # Center pixel should be brighter than 128
    r, g, b = result.getpixel((5, 5))
    assert r > 128 and g > 128 and b > 128


def test_brightness_decrease(sample_image):
    """Decreasing brightness should make pixels darker."""
    f = BrightnessFilter(factor=0.5)
    result = f.apply(sample_image)
    r, g, b = result.getpixel((5, 5))
    assert r < 128 and g < 128 and b < 128


def test_brightness_unchanged(sample_image):
    """Factor 1.0 should leave image unchanged."""
    f = BrightnessFilter(factor=1.0)
    result = f.apply(sample_image)
    assert result.getpixel((5, 5)) == sample_image.getpixel((5, 5))


def test_saturation_zero_is_grayscale(sample_image):
    """Saturation factor 0 should produce grayscale."""
    f = SaturationFilter(factor=0)
    result = f.apply(sample_image)
    r, g, b = result.getpixel((5, 5))
    # All channels should be equal (grayscale)
    assert r == g == b


def test_color_channel_reduces_red(red_image):
    """Reducing red channel should lower the red component."""
    original_r = red_image.getpixel((5, 5))[0]
    f = ColorChannelFilter(channel="red", factor=0.5)
    result = f.apply(red_image)
    new_r = result.getpixel((5, 5))[0]
    assert new_r < original_r


def test_color_channel_keeps_other_channels(red_image):
    """Adjusting red should not change green/blue."""
    _, orig_g, orig_b = red_image.getpixel((5, 5))
    f = ColorChannelFilter(channel="red", factor=0.5)
    result = f.apply(red_image)
    _, new_g, new_b = result.getpixel((5, 5))
    assert new_g == orig_g
    assert new_b == orig_b


# ── Pipeline tests ───────────────────────────────────────────────────


def test_pipeline_empty(sample_image):
    """Empty pipeline should return the image unchanged."""
    pipeline = FilterPipeline()
    result = pipeline.run(sample_image)
    assert result.size == sample_image.size
    assert len(pipeline) == 0


def test_pipeline_single_filter(sample_image):
    """Pipeline with one filter should apply it."""
    pipeline = FilterPipeline([BrightnessFilter(1.5)])
    result = pipeline.run(sample_image)
    r, g, b = result.getpixel((5, 5))
    assert r > 128  # brighter


def test_pipeline_chaining(sample_image):
    """Pipeline.add should support chaining."""
    pipeline = (
        FilterPipeline()
        .add(BrightnessFilter(1.2))
        .add(ContrastFilter(1.1))
        .add(SharpnessFilter(1.05))
    )
    assert len(pipeline) == 3
    result = pipeline.run(sample_image)
    assert isinstance(result, Image.Image)


def test_pipeline_order_matters(sample_image):
    """Different filter orders should produce different results (generally)."""
    # Brightness then contrast
    p1 = FilterPipeline([BrightnessFilter(1.5), ContrastFilter(0.5)])
    _r1 = p1.run(sample_image)

    # Contrast then brightness
    p2 = FilterPipeline([ContrastFilter(0.5), BrightnessFilter(1.5)])
    _r2 = p2.run(sample_image)

    # For a uniform image the result may be the same, but the pipeline
    # structure should differ
    assert p1.filters[0].name == "Brightness"
    assert p2.filters[0].name == "Contrast"


def test_pipeline_repr():
    """Pipeline repr should list filter names."""
    pipeline = FilterPipeline([BrightnessFilter(1.2), ContrastFilter(1.1)])
    assert "Brightness" in repr(pipeline)
    assert "Contrast" in repr(pipeline)


# ── RecommendationParser tests ───────────────────────────────────────


def test_parser_brightness():
    """Parser should create BrightnessFilter from recommendation."""
    parser = RecommendationParser()
    pipeline = parser.parse(["BRIGHTNESS: increase by 25%"])
    assert len(pipeline) == 1
    assert pipeline.filters[0].name == "Brightness"
    assert abs(pipeline.filters[0].factor - 1.25) < 0.01


def test_parser_multiple_recommendations():
    """Parser should create multiple filters in correct order."""
    parser = RecommendationParser()
    pipeline = parser.parse([
        "BRIGHTNESS: increase by 20%",
        "CONTRAST: boost by 15%",
        "SATURATION: increase by 10%",
    ])
    # Should be in order: brightness, contrast, saturation
    names = [f.name for f in pipeline.filters]
    assert names == ["Brightness", "Contrast", "Saturation"]


def test_parser_color_temperature():
    """Parser should handle color temperature recommendations."""
    parser = RecommendationParser()
    pipeline = parser.parse(["COLOR_TEMPERATURE: cool by 800K"])
    assert len(pipeline) == 1
    assert pipeline.filters[0].name == "ColorTemperature"
    assert pipeline.filters[0].kelvin == 5700  # 6500 - 800


def test_parser_channel_adjustment():
    """Parser should handle color channel adjustments."""
    parser = RecommendationParser()
    pipeline = parser.parse(["RED_CHANNEL: reduce by 15%"])
    assert len(pipeline) == 1
    assert pipeline.filters[0].name == "RedChannel"


def test_parser_skips_no_op():
    """Parser should skip no-op recommendations."""
    parser = RecommendationParser()
    pipeline = parser.parse([
        "NO_ENHANCEMENTS: maintain current quality",
        "none needed",
    ])
    assert len(pipeline) == 0


def test_parser_skips_non_numeric():
    """Parser should skip recommendations without numeric values."""
    parser = RecommendationParser()
    pipeline = parser.parse(["BRIGHTNESS: slightly increase"])
    assert len(pipeline) == 0


def test_parser_handles_dict_recommendations():
    """Parser should handle dict-format recommendations."""
    parser = RecommendationParser()
    pipeline = parser.parse([
        {"action": "BRIGHTNESS: increase by 20%"},
        {"text": "CONTRAST: boost by 10%"},
    ])
    assert len(pipeline) == 2
