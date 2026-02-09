"""Individual image filter implementations.

Each filter class implements the ``ImageFilter`` protocol:
  - ``name`` property → human-readable identifier
  - ``apply(image) → image`` → transforms a PIL Image

Filters are designed to be composed into a ``FilterPipeline``.
"""
from .basic import (
    BrightnessFilter,
    ContrastFilter,
    SaturationFilter,
    SharpnessFilter,
)
from .advanced import (
    ClarityFilter,
    ColorChannelFilter,
    ColorTemperatureFilter,
    ShadowsHighlightsFilter,
    UnsharpMaskFilter,
    VibranceFilter,
)

__all__ = [
    "BrightnessFilter",
    "ContrastFilter",
    "SaturationFilter",
    "SharpnessFilter",
    "ClarityFilter",
    "ColorChannelFilter",
    "ColorTemperatureFilter",
    "ShadowsHighlightsFilter",
    "UnsharpMaskFilter",
    "VibranceFilter",
]
