"""Advanced image filters.

These filters implement the ``ImageFilter`` protocol and perform
more complex per-pixel or multi-pass operations.  They are extracted
from the legacy ``enhancement_filters.py`` module.

Where possible, each filter operates on an in-memory PIL ``Image``
rather than file paths (unlike the legacy functions).  This makes
them composable via ``FilterPipeline``.
"""
from __future__ import annotations

import colorsys

from PIL import Image, ImageFilter as PILFilter

from ...config.defaults import (
    DEFAULT_COLOR_TEMP_BASELINE,
    LUMINANCE_BLUE,
    LUMINANCE_GREEN,
    LUMINANCE_RED,
)


class UnsharpMaskFilter:
    """Apply Unsharp Mask for sharpening / local contrast.

    Args:
        radius: Blur radius (1.0–3.0 typical).
        percent: Sharpening strength as percentage (50–150 typical).
        threshold: Edge detection threshold (0–10 typical).
    """

    def __init__(
        self, radius: float = 1.5, percent: int = 80, threshold: int = 0
    ):
        self.radius = radius
        self.percent = percent
        self.threshold = threshold

    @property
    def name(self) -> str:
        return "UnsharpMask"

    def apply(self, image: Image.Image) -> Image.Image:
        return image.filter(
            PILFilter.UnsharpMask(
                radius=self.radius,
                percent=self.percent,
                threshold=self.threshold,
            )
        )

    def __repr__(self) -> str:
        return (
            f"UnsharpMaskFilter(radius={self.radius}, "
            f"percent={self.percent}, threshold={self.threshold})"
        )


class ColorTemperatureFilter:
    """Adjust image color temperature (warm ↔ cool).

    Args:
        kelvin: Target color temperature in Kelvin.
                1500 = warm/candle, 6500 = daylight, 10000 = cool/sky.
    """

    def __init__(self, kelvin: float = DEFAULT_COLOR_TEMP_BASELINE):
        self.kelvin = kelvin

    @property
    def name(self) -> str:
        return "ColorTemperature"

    def apply(self, image: Image.Image) -> Image.Image:
        if image.mode != "RGB":
            image = image.convert("RGB")

        ratio = self.kelvin / DEFAULT_COLOR_TEMP_BASELINE
        pixels = image.load()
        width, height = image.size

        out = Image.new("RGB", image.size)
        out_px = out.load()

        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y][:3]
                r = int(min(255, r * ratio))
                b = int(min(255, b / ratio))
                out_px[x, y] = (r, g, b)

        return out

    def __repr__(self) -> str:
        return f"ColorTemperatureFilter(kelvin={self.kelvin})"


class ShadowsHighlightsFilter:
    """Selectively adjust shadows and highlights.

    Args:
        shadow_adjust: Shadow brightness change (-100 to +100).
        highlight_adjust: Highlight brightness change (-100 to +100).
    """

    def __init__(self, shadow_adjust: float = 0.0, highlight_adjust: float = 0.0):
        self.shadow_adjust = shadow_adjust
        self.highlight_adjust = highlight_adjust

    @property
    def name(self) -> str:
        return "ShadowsHighlights"

    def apply(self, image: Image.Image) -> Image.Image:
        if image.mode != "RGB":
            image = image.convert("RGB")

        pixels = image.load()
        width, height = image.size
        out = Image.new("RGB", image.size)
        out_px = out.load()

        for y in range(height):
            for x in range(width):
                r, g, b = pixels[x, y][:3]
                luminance = (
                    LUMINANCE_RED * r + LUMINANCE_GREEN * g + LUMINANCE_BLUE * b
                ) / 255.0

                if luminance < 0.5:
                    factor = 1.0 + (self.shadow_adjust / 100.0)
                    r = int(min(255, max(0, r * factor)))
                    g = int(min(255, max(0, g * factor)))
                    b = int(min(255, max(0, b * factor)))

                if luminance > 0.5:
                    factor = 1.0 + (self.highlight_adjust / 100.0)
                    r = int(min(255, max(0, r * factor)))
                    g = int(min(255, max(0, g * factor)))
                    b = int(min(255, max(0, b * factor)))

                out_px[x, y] = (r, g, b)

        return out

    def __repr__(self) -> str:
        return (
            f"ShadowsHighlightsFilter("
            f"shadow_adjust={self.shadow_adjust}, "
            f"highlight_adjust={self.highlight_adjust})"
        )


class ClarityFilter:
    """Mid-tone contrast enhancement using unsharp mask.

    Args:
        strength: Clarity strength (0–100, typically 20–40).
    """

    def __init__(self, strength: float = 20.0):
        self.strength = strength

    @property
    def name(self) -> str:
        return "Clarity"

    def apply(self, image: Image.Image) -> Image.Image:
        factor = 1.0 + (self.strength / 100.0)
        return image.filter(
            PILFilter.UnsharpMask(
                radius=2.0, percent=int(factor * 100), threshold=3
            )
        )

    def __repr__(self) -> str:
        return f"ClarityFilter(strength={self.strength})"


class VibranceFilter:
    """Selective saturation boost (less-saturated colors boosted more).

    Args:
        factor: 0.5 = half vibrance, 1.0 = unchanged, 1.5 = 50 % more.
    """

    def __init__(self, factor: float = 1.0):
        self.factor = factor

    @property
    def name(self) -> str:
        return "Vibrance"

    def apply(self, image: Image.Image) -> Image.Image:
        if image.mode != "RGB":
            image = image.convert("RGB")

        pixels = image.load()
        width, height = image.size
        out = Image.new("RGB", image.size)
        out_px = out.load()

        for y in range(height):
            for x in range(width):
                r, g, b = [c / 255.0 for c in pixels[x, y][:3]]
                h, s, v = colorsys.rgb_to_hsv(r, g, b)
                s = min(1.0, s * self.factor)
                r, g, b = colorsys.hsv_to_rgb(h, s, v)
                out_px[x, y] = (int(r * 255), int(g * 255), int(b * 255))

        return out

    def __repr__(self) -> str:
        return f"VibranceFilter(factor={self.factor})"


class ColorChannelFilter:
    """Adjust a single RGB channel.

    Args:
        channel: ``'red'``, ``'green'``, or ``'blue'``.
        factor: Multiplier (>1 = increase, <1 = decrease).
    """

    CHANNEL_INDEX = {"red": 0, "green": 1, "blue": 2}

    def __init__(self, channel: str = "red", factor: float = 1.0):
        self.channel = channel.lower()
        self.factor = factor

    @property
    def name(self) -> str:
        return f"{self.channel.capitalize()}Channel"

    def apply(self, image: Image.Image) -> Image.Image:
        if image.mode != "RGB":
            image = image.convert("RGB")

        idx = self.CHANNEL_INDEX.get(self.channel, 0)
        pixels = image.load()
        width, height = image.size

        # Operate in-place on a copy
        out = image.copy()
        out_px = out.load()

        for y in range(height):
            for x in range(width):
                channels = list(pixels[x, y][:3])
                channels[idx] = int(min(255, channels[idx] * self.factor))
                out_px[x, y] = tuple(channels)

        return out

    def __repr__(self) -> str:
        return f"ColorChannelFilter(channel='{self.channel}', factor={self.factor})"
