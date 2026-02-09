"""Basic PIL-based image filters.

These filters wrap PIL's ``ImageEnhance`` classes and implement the
``ImageFilter`` protocol.  They are fast and suitable for all images.
"""
from __future__ import annotations

from PIL import Image, ImageEnhance


class BrightnessFilter:
    """Adjust image brightness.

    Args:
        factor: 1.0 = unchanged, <1 = darker, >1 = brighter.
    """

    def __init__(self, factor: float = 1.0):
        self.factor = factor

    @property
    def name(self) -> str:
        return "Brightness"

    def apply(self, image: Image.Image) -> Image.Image:
        return ImageEnhance.Brightness(image).enhance(self.factor)

    def __repr__(self) -> str:
        return f"BrightnessFilter(factor={self.factor})"


class ContrastFilter:
    """Adjust image contrast.

    Args:
        factor: 1.0 = unchanged, <1 = less contrast, >1 = more contrast.
    """

    def __init__(self, factor: float = 1.0):
        self.factor = factor

    @property
    def name(self) -> str:
        return "Contrast"

    def apply(self, image: Image.Image) -> Image.Image:
        return ImageEnhance.Contrast(image).enhance(self.factor)

    def __repr__(self) -> str:
        return f"ContrastFilter(factor={self.factor})"


class SaturationFilter:
    """Adjust color saturation.

    Args:
        factor: 0 = grayscale, 1.0 = unchanged, >1 = more vibrant.
    """

    def __init__(self, factor: float = 1.0):
        self.factor = factor

    @property
    def name(self) -> str:
        return "Saturation"

    def apply(self, image: Image.Image) -> Image.Image:
        return ImageEnhance.Color(image).enhance(self.factor)

    def __repr__(self) -> str:
        return f"SaturationFilter(factor={self.factor})"


class SharpnessFilter:
    """Adjust image sharpness.

    Args:
        factor: 0 = blur, 1.0 = unchanged, >1 = sharper.
    """

    def __init__(self, factor: float = 1.0):
        self.factor = factor

    @property
    def name(self) -> str:
        return "Sharpness"

    def apply(self, image: Image.Image) -> Image.Image:
        return ImageEnhance.Sharpness(image).enhance(self.factor)

    def __repr__(self) -> str:
        return f"SharpnessFilter(factor={self.factor})"
