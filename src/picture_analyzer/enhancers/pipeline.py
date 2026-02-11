"""Filter pipeline compositor and recommendation parser.

Provides:
  - ``FilterPipeline``: composes multiple ``ImageFilter`` instances
  - ``RecommendationParser``: converts AI text recommendations to filters
  - ``enhance_from_analysis``: top-level convenience function
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

from PIL import Image

from ..config.defaults import (
    DEFAULT_CHANNEL_FACTOR_RANGE,
    DEFAULT_COLOR_TEMP_BASELINE,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_KELVIN_RANGE,
)
from ..core.models import AnalysisResult, Enhancement
from .filters.basic import (
    BrightnessFilter,
    ContrastFilter,
    SaturationFilter,
    SharpnessFilter,
)
from .filters.advanced import (
    ClarityFilter,
    ColorChannelFilter,
    ColorTemperatureFilter,
    ShadowsHighlightsFilter,
    UnsharpMaskFilter,
    VibranceFilter,
)


class FilterPipeline:
    """Composes a sequence of ``ImageFilter`` instances.

    Filters are applied in the order they are added::

        pipeline = FilterPipeline()
        pipeline.add(BrightnessFilter(1.2))
        pipeline.add(ContrastFilter(1.15))
        result = pipeline.run(Image.open("photo.jpg"))
        result.save("enhanced.jpg")
    """

    def __init__(self, filters: Sequence | None = None):
        self._filters: list = list(filters or [])

    def add(self, f: Any) -> "FilterPipeline":
        """Add a filter to the end of the pipeline. Returns self for chaining."""
        self._filters.append(f)
        return self

    def run(self, image: Image.Image) -> Image.Image:
        """Apply all filters in order and return the final image."""
        result = image
        if result.mode not in ("RGB", "RGBA"):
            result = result.convert("RGB")

        for f in self._filters:
            factor_info = f""
            if hasattr(f, 'factor'):
                factor_info = f" ({f.factor:.2f}x)"
            print(f"    → Adjusting {f.name.lower()}{factor_info}...")
            result = f.apply(result)

        return result

    @property
    def filters(self) -> list:
        """List of filters in the pipeline."""
        return list(self._filters)

    def __len__(self) -> int:
        return len(self._filters)

    def __repr__(self) -> str:
        names = [f.name for f in self._filters]
        return f"FilterPipeline([{', '.join(names)}])"


class RecommendationParser:
    """Parses AI enhancement recommendation strings into filter instances.

    The parser understands the format produced by the analysis prompt:
      - ``"BRIGHTNESS: increase by 25%"``
      - ``"COLOR_TEMPERATURE: cool by 800K"``
      - ``"UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0"``
    """

    def parse(self, recommendations: list[str | dict]) -> FilterPipeline:
        """Convert a list of AI recommendations into a ``FilterPipeline``.

        Args:
            recommendations: List of recommendation strings or dicts.

        Returns:
            FilterPipeline ready to apply to an image.
        """
        basic_filters: dict[str, Any] = {}  # ordered by apply priority
        advanced_filters: list = []

        for rec in recommendations:
            text = self._to_text(rec)
            if not text:
                continue

            text_lower = text.lower().strip()

            # Skip no-op recommendations
            if text_lower in (
                "no enhancements needed",
                "no_enhancements: maintain current quality",
                "none needed",
                "maintain",
                "normalize",
            ):
                continue

            # Must have a numeric value
            if not re.search(r"\d+", text):
                continue

            self._parse_one(text, text_lower, basic_filters, advanced_filters)

        # Build pipeline in optimal order
        pipeline = FilterPipeline()

        # Basic adjustments: brightness → contrast → saturation → sharpness
        order = ["brightness", "contrast", "saturation", "sharpness"]
        for key in order:
            if key in basic_filters:
                pipeline.add(basic_filters[key])

        # Advanced operations
        for f in advanced_filters:
            pipeline.add(f)

        return pipeline

    def parse_from_analysis(self, analysis: AnalysisResult) -> FilterPipeline:
        """Build a ``FilterPipeline`` from an ``AnalysisResult``."""
        raw = analysis.raw_response or {}
        enhancement = raw.get("enhancement", {})
        recs = enhancement.get("recommended_enhancements", [])

        if isinstance(recs, str):
            recs = [r.strip() for r in recs.split("\n") if r.strip()]
        elif isinstance(recs, dict):
            recs = [recs]

        return self.parse(recs or [])

    # ── Internal ─────────────────────────────────────────────────────

    def _to_text(self, rec: str | dict) -> str:
        """Normalize a recommendation to a string."""
        if isinstance(rec, dict):
            for key in ("action", "text", "description", "recommendation"):
                if key in rec and isinstance(rec[key], str):
                    return rec[key]
            # Fallback: first string value
            for val in rec.values():
                if isinstance(val, str):
                    return val
            return str(rec)
        if isinstance(rec, str):
            return rec
        return ""

    def _parse_one(
        self,
        text: str,
        text_lower: str,
        basic: dict[str, Any],
        advanced: list,
    ) -> None:
        """Parse a single recommendation into filter(s)."""
        # ── BRIGHTNESS ─────────────────────────────────────────────
        if "brightness" in text_lower:
            match = re.search(r"(?:increase|decrease|by).*?([+-]?\d+)\s*%", text_lower)
            if match:
                pct = int(match.group(1))
                basic["brightness"] = BrightnessFilter(factor=1.0 + pct / 100.0)
                print(f"  → Brightness: {pct:+d}%")

        # ── CONTRAST ───────────────────────────────────────────────
        elif "contrast" in text_lower:
            match = re.search(r"(?:increase|boost|by).*?([+-]?\d+)\s*%", text_lower)
            if match:
                pct = int(match.group(1))
                basic["contrast"] = ContrastFilter(factor=1.0 + pct / 100.0)
                print(f"  → Contrast: {pct:+d}%")

        # ── COLOR TEMPERATURE ──────────────────────────────────────
        elif "color_temperature" in text_lower or "temperature" in text_lower:
            match = re.search(r"([+-]?\d+)\s*k(?:elvin)?", text_lower)
            if match:
                kelvin_shift = int(match.group(1))
                if "cool" in text_lower:
                    kelvin_shift = -abs(kelvin_shift)
                elif "warm" in text_lower:
                    kelvin_shift = abs(kelvin_shift)
                target = max(
                    DEFAULT_KELVIN_RANGE[0],
                    min(DEFAULT_KELVIN_RANGE[1], DEFAULT_COLOR_TEMP_BASELINE + kelvin_shift),
                )
                advanced.append(ColorTemperatureFilter(kelvin=target))
                print(f"  → Color Temperature: {target}K ({kelvin_shift:+d}K)")

        # ── COLOR CHANNELS ─────────────────────────────────────────
        elif any(ch in text_lower for ch in ("red_channel", "blue_channel", "green_channel")):
            channel = None
            if "red" in text_lower:
                channel = "red"
            elif "blue" in text_lower:
                channel = "blue"
            elif "green" in text_lower:
                channel = "green"

            match = re.search(r"([+-]?\d+)\s*%", text_lower)
            if match and channel:
                pct = int(match.group(1))
                if "reduce" in text_lower or "decrease" in text_lower:
                    pct = -pct
                factor = max(
                    DEFAULT_CHANNEL_FACTOR_RANGE[0],
                    min(DEFAULT_CHANNEL_FACTOR_RANGE[1], 1.0 + pct / 100.0),
                )
                advanced.append(ColorChannelFilter(channel=channel, factor=factor))
                print(f"  → {channel.capitalize()} Channel: {pct:+d}%")

        # ── UNSHARP MASK ───────────────────────────────────────────
        elif "unsharp_mask" in text_lower or "unsharp mask" in text_lower:
            radius, percent, threshold = 1.5, 80, 0
            m = re.search(r"radius\s*=\s*([\d.]+)", text_lower)
            if m:
                radius = float(m.group(1))
            m = re.search(r"strength\s*=\s*([\d.]+)", text_lower)
            if m:
                percent = int(float(m.group(1)))
            elif re.search(r"(\d+)\s*%", text_lower):
                m = re.search(r"(\d+)\s*%", text_lower)
                percent = int(m.group(1))
            m = re.search(r"threshold\s*=\s*(\d+)", text_lower)
            if m:
                threshold = int(m.group(1))
            advanced.append(UnsharpMaskFilter(radius=radius, percent=percent, threshold=threshold))
            print(f"  → Unsharp Mask: radius={radius}, strength={percent}%")

        # ── SHADOWS / HIGHLIGHTS ───────────────────────────────────
        elif "shadow" in text_lower or "highlight" in text_lower:
            shadow, highlight = 0.0, 0.0
            if "shadow" in text_lower:
                m = re.search(r"(?:brighten|darken).*?([+-]?\d+)\s*%", text_lower)
                if m:
                    shadow = float(m.group(1))
            if "highlight" in text_lower:
                m = re.search(r"(?:brighten|darken).*?([+-]?\d+)\s*%", text_lower)
                if m:
                    highlight = float(m.group(1))
            if shadow or highlight:
                advanced.append(
                    ShadowsHighlightsFilter(shadow_adjust=shadow, highlight_adjust=highlight)
                )
                print(f"  → Shadows: {shadow:+.0f}%, Highlights: {highlight:+.0f}%")

        # ── VIBRANCE ───────────────────────────────────────────────
        elif "vibrance" in text_lower:
            m = re.search(r"(?:increase|boost|by).*?([+-]?\d+)\s*%", text_lower)
            if m:
                pct = int(m.group(1))
                advanced.append(VibranceFilter(factor=1.0 + pct / 100.0))
                print(f"  → Vibrance: {pct:+d}%")

        # ── CLARITY ────────────────────────────────────────────────
        elif "clarity" in text_lower:
            m = re.search(r"(?:boost|increase|by).*?([+-]?\d+)\s*%", text_lower)
            if m:
                pct = int(m.group(1))
                advanced.append(ClarityFilter(strength=float(pct)))
                print(f"  → Clarity: {pct:+d}%")

        # ── SATURATION ─────────────────────────────────────────────
        elif "saturation" in text_lower or "saturate" in text_lower:
            m = re.search(r"(?:increase|boost|by).*?([+-]?\d+)\s*%", text_lower)
            if m:
                pct = int(m.group(1))
                basic["saturation"] = SaturationFilter(factor=1.0 + pct / 100.0)
                print(f"  → Saturation: {pct:+d}%")

        # ── SHARPNESS ──────────────────────────────────────────────
        elif "sharpness" in text_lower or "sharpen" in text_lower:
            m = re.search(r"(?:increase|boost|enhance|by).*?([+-]?\d+)\s*%", text_lower)
            if m:
                pct = int(m.group(1))
                basic["sharpness"] = SharpnessFilter(factor=1.0 + pct / 100.0)
                print(f"  → Sharpness: {pct:+d}%")


def enhance_image(
    image_path: str,
    recommendations: list[str | dict],
    output_path: str | None = None,
    jpeg_quality: int = DEFAULT_JPEG_QUALITY,
) -> str | None:
    """Convenience function: parse recommendations and enhance an image.

    Args:
        image_path: Source image path.
        recommendations: AI recommendation strings.
        output_path: Where to save the result (defaults to overwrite source).
        jpeg_quality: JPEG save quality.

    Returns:
        Path to the saved image, or None on failure.
    """
    try:
        parser = RecommendationParser()
        pipeline = parser.parse(recommendations)

        if len(pipeline) == 0:
            print("No enhancement recommendations found")
            return None

        image = Image.open(image_path)
        result = pipeline.run(image)
        out = output_path or image_path
        result.save(out, quality=jpeg_quality)
        return out
    except Exception as e:
        print(f"Error during enhancement: {e}")
        return None
