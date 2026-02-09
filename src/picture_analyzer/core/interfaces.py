"""Protocol definitions (interfaces) for all pluggable components.

These protocols use Python's structural subtyping — any class that implements
the required methods is automatically compatible, no inheritance needed.

Each protocol corresponds to a provider category:
    - Analyzer:       AI image analysis  (OpenAI, Ollama, etc.)
    - Geocoder:       Location → GPS     (Nominatim, Google, etc.)
    - MetadataWriter: Embed metadata     (EXIF, XMP, IPTC, etc.)
    - ImageFilter:    Transform image    (brightness, contrast, etc.)
    - Reporter:       Generate reports   (Markdown, HTML, etc.)

Usage::

    class MyAnalyzer:  # No inheritance needed!
        def analyze(self, image: ImageData, context: AnalysisContext) -> AnalysisResult:
            ...

    # Type checking works:
    analyzer: Analyzer = MyAnalyzer()  # ✓
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from PIL import Image

from .models import (
    AnalysisContext,
    AnalysisResult,
    GeoLocation,
    ImageData,
)


@runtime_checkable
class Analyzer(Protocol):
    """Analyzes an image and returns structured metadata.

    Implementations:
        - OpenAIAnalyzer:  Uses OpenAI Vision API
        - OllamaAnalyzer:  Uses local Ollama models (future)
    """

    def analyze(self, image: ImageData, context: AnalysisContext) -> AnalysisResult:
        """Analyze an image and return structured results.

        Args:
            image: Image data including path and optional base64 encoding.
            context: Analysis context (language, description text, flags).

        Returns:
            Structured analysis result.
        """
        ...


@runtime_checkable
class Geocoder(Protocol):
    """Converts location names to GPS coordinates.

    Implementations:
        - NominatimGeocoder:  Free, uses OpenStreetMap
        - GoogleGeocoder:     Paid, higher accuracy (future)
    """

    def geocode(self, location: str) -> GeoLocation | None:
        """Convert a location string to GPS coordinates.

        Args:
            location: Human-readable location name (e.g., "Oostkapelle, Nederland").

        Returns:
            GeoLocation with lat/lon, or None if not found / too vague.
        """
        ...


@runtime_checkable
class GeocoderWithCache(Geocoder, Protocol):
    """Geocoder that supports cache operations."""

    def clear_cache(self) -> None:
        """Clear the geocoding cache."""
        ...

    def cache_size(self) -> int:
        """Return the number of cached entries."""
        ...


@runtime_checkable
class MetadataWriter(Protocol):
    """Writes metadata to an image file.

    Implementations:
        - ExifWriter:  Writes EXIF tags via piexif
        - XmpWriter:   Writes XMP sidecar data
    """

    def write(self, image_path: Path, analysis: AnalysisResult) -> bool:
        """Embed analysis metadata into an image file.

        Args:
            image_path: Path to the image file to write to.
            analysis: Analysis result containing metadata to embed.

        Returns:
            True if metadata was written successfully.
        """
        ...


@runtime_checkable
class MetadataReader(Protocol):
    """Reads metadata from an image file."""

    def read(self, image_path: Path) -> dict:
        """Read metadata from an image file.

        Args:
            image_path: Path to the image file.

        Returns:
            Dictionary of metadata key-value pairs.
        """
        ...


@runtime_checkable
class ImageFilter(Protocol):
    """Applies a single transformation to an image.

    Filters are composed into a FilterPipeline for sequential application.

    Implementations:
        - BrightnessFilter, ContrastFilter, SaturationFilter
        - ColorTemperatureFilter, UnsharpMaskFilter
        - ShadowsFilter, HighlightsFilter, VibranceFilter, ClarityFilter
    """

    @property
    def name(self) -> str:
        """Human-readable name of this filter (e.g., 'Brightness')."""
        ...

    def apply(self, image: Image.Image) -> Image.Image:
        """Apply this filter to an image.

        Args:
            image: PIL Image to transform.

        Returns:
            Transformed PIL Image (may be the same object or a new one).
        """
        ...


@runtime_checkable
class Reporter(Protocol):
    """Generates reports from analysis results.

    Implementations:
        - MarkdownReporter:  Generates .md reports with optional thumbnails
        - HtmlReporter:      Generates .html gallery pages (future)
    """

    def generate(self, results: list[AnalysisResult], output_path: Path) -> Path:
        """Generate a report from analysis results.

        Args:
            results: List of analysis results to include in report.
            output_path: Directory or file path for the report.

        Returns:
            Path to the generated report file.
        """
        ...


@runtime_checkable
class ProgressCallback(Protocol):
    """Callback for reporting progress during batch operations."""

    def on_start(self, total: int) -> None:
        """Called when batch processing begins."""
        ...

    def on_progress(self, current: int, total: int, message: str = "") -> None:
        """Called after each item is processed."""
        ...

    def on_complete(self, succeeded: int, failed: int) -> None:
        """Called when batch processing is complete."""
        ...

    def on_error(self, item: str, error: str) -> None:
        """Called when processing an item fails."""
        ...
