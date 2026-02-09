"""Pydantic data models for structured data exchange between components.

These models replace the untyped dicts that were previously passed between
modules.  They provide validation, serialization (to/from JSON), and
IDE support throughout the codebase.

All models are immutable by default (``frozen=True``).  Use ``.model_copy()``
to create modified copies.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────────────


class SlideProfileName(str, Enum):
    """Known slide restoration profile identifiers."""

    FADED = "faded"
    COLOR_CAST = "color_cast"
    RED_CAST = "red_cast"
    YELLOW_CAST = "yellow_cast"
    AGED = "aged"
    WELL_PRESERVED = "well_preserved"
    AUTO = "auto"


class EnhancementAction(str, Enum):
    """Recognized enhancement action keywords from AI responses."""

    BRIGHTNESS = "brightness"
    CONTRAST = "contrast"
    SATURATION = "saturation"
    COLOR_TEMPERATURE = "color_temperature"
    SHARPNESS = "sharpness"
    NOISE_REDUCTION = "noise_reduction"
    RED_CHANNEL = "red_channel"
    BLUE_CHANNEL = "blue_channel"
    GREEN_CHANNEL = "green_channel"
    GREEN_SATURATION = "green_saturation"
    UNSHARP_MASK = "unsharp_mask"
    SHADOWS = "shadows"
    HIGHLIGHTS = "highlights"
    VIBRANCE = "vibrance"
    CLARITY = "clarity"
    YELLOW_CAST_REMOVAL = "yellow_cast_removal"
    NO_ENHANCEMENTS = "no_enhancements"


class ReportFormat(str, Enum):
    MARKDOWN = "markdown"
    HTML = "html"


# ── Location Models ──────────────────────────────────────────────────


class GeoLocation(BaseModel, frozen=True):
    """GPS coordinates with optional accuracy metadata."""

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    display_name: Optional[str] = None

    @property
    def as_tuple(self) -> tuple[float, float]:
        return (self.latitude, self.longitude)


class LocationInfo(BaseModel, frozen=True):
    """Location information extracted from analysis."""

    location_name: str = Field(description="Human-readable location description")
    country: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    coordinates: Optional[GeoLocation] = None
    confidence: int = Field(default=0, ge=0, le=100, description="Confidence in location accuracy")
    source: str = Field(default="ai", description="How location was determined: ai, description, gps")


# ── Enhancement Models ───────────────────────────────────────────────


class Enhancement(BaseModel, frozen=True):
    """A single enhancement recommendation from AI analysis."""

    action: str = Field(description="Enhancement action keyword (e.g., 'brightness', 'contrast')")
    direction: str = Field(default="increase", description="'increase' or 'decrease'")
    amount_percent: Optional[float] = Field(default=None, description="Suggested change in percent")
    value: Optional[float] = Field(default=None, description="Absolute target value (e.g., Kelvin)")
    raw_text: str = Field(default="", description="Original recommendation text from AI")


class ColorBalance(BaseModel, frozen=True):
    """RGB color balance multipliers for slide restoration."""

    red: float = Field(default=1.0, ge=0.0, le=3.0)
    green: float = Field(default=1.0, ge=0.0, le=3.0)
    blue: float = Field(default=1.0, ge=0.0, le=3.0)


class SlideProfile(BaseModel, frozen=True):
    """Slide restoration profile parameters."""

    name: str
    description: str = ""
    saturation: float = Field(default=1.0, ge=0.0, le=3.0)
    contrast: float = Field(default=1.0, ge=0.0, le=3.0)
    brightness: float = Field(default=1.0, ge=0.0, le=3.0)
    sharpness: float = Field(default=1.0, ge=0.0, le=3.0)
    color_balance: ColorBalance = Field(default_factory=ColorBalance)
    denoise: bool = False
    denoise_radius: float = Field(default=0.5, ge=0.0, le=5.0)


class SlideProfileDetection(BaseModel, frozen=True):
    """AI-detected slide profile with confidence score."""

    profile_name: str
    confidence: int = Field(ge=0, le=100)


# ── Era / Time Models ───────────────────────────────────────────────


class EraInfo(BaseModel, frozen=True):
    """Time period information extracted from analysis."""

    estimated_decade: Optional[str] = Field(default=None, description="E.g., '1970s', '1980s'")
    estimated_year: Optional[int] = Field(default=None, ge=1800, le=2100)
    time_of_day: Optional[str] = Field(default=None, description="E.g., 'morning', 'afternoon'")
    season: Optional[str] = Field(default=None, description="E.g., 'summer', 'winter'")
    confidence: int = Field(default=0, ge=0, le=100)


# ── Main Analysis Result ─────────────────────────────────────────────


class AnalysisResult(BaseModel):
    """Complete result of AI image analysis.

    This is the central data model — produced by Analyzers and consumed
    by Enhancers, MetadataWriters, Reporters, etc.
    """

    # Descriptive metadata
    title: str = Field(default="", description="Short descriptive title")
    description: str = Field(default="", description="Detailed description of the image")
    keywords: list[str] = Field(default_factory=list, description="Tags / keywords")

    # People and objects
    people: list[str] = Field(default_factory=list, description="People identified in image")
    objects: list[str] = Field(default_factory=list, description="Notable objects identified")
    people_count: Optional[int] = Field(default=None, ge=0)

    # Location
    location: Optional[LocationInfo] = None

    # Time / era
    era: Optional[EraInfo] = None

    # Scene classification
    scene_type: Optional[str] = None
    mood: Optional[str] = None
    photography_style: Optional[str] = None
    composition_quality: Optional[str] = None
    lighting_quality: Optional[str] = None

    # Enhancement recommendations
    enhancement_recommendations: list[Enhancement] = Field(default_factory=list)

    # Slide profile detection
    slide_profile: Optional[SlideProfileDetection] = None

    # Colors
    dominant_colors: list[str] = Field(default_factory=list)
    color_palette: Optional[str] = None

    # Confidence scores for individual sections
    confidence_scores: dict[str, int] = Field(default_factory=dict)

    # Preserve original AI output for debugging / re-processing
    raw_response: dict[str, Any] = Field(default_factory=dict)

    # Processing metadata
    source_path: Optional[Path] = None
    analyzed_at: Optional[datetime] = None
    analyzer_model: Optional[str] = None
    description_context: Optional[str] = Field(
        default=None,
        description="Contents of description.txt used as context",
    )


# ── Analysis Context ─────────────────────────────────────────────────


class AnalysisContext(BaseModel):
    """Context provided to an Analyzer alongside the image.

    Includes description.txt content, language preference, and any
    configuration that affects how analysis is performed.
    """

    language: str = "en"
    description_text: Optional[str] = Field(
        default=None,
        description="Contents of description.txt from the image directory",
    )
    detect_slide_profiles: bool = True
    recommend_enhancements: bool = True
    detect_location: bool = True
    custom_instructions: Optional[str] = None


# ── Image Data ────────────────────────────────────────────────────────


class ImageData(BaseModel):
    """Wrapper for image file information passed to analyzers."""

    path: Path
    mime_type: str
    base64_data: Optional[str] = Field(default=None, exclude=True, repr=False)
    width: Optional[int] = None
    height: Optional[int] = None


# ── Batch Processing ─────────────────────────────────────────────────


class ProcessingResult(BaseModel):
    """Result of processing a single image (analysis + enhancement + metadata)."""

    source_path: Path
    analysis: Optional[AnalysisResult] = None
    analyzed_path: Optional[Path] = None
    enhanced_path: Optional[Path] = None
    restored_path: Optional[Path] = None
    json_path: Optional[Path] = None
    success: bool = True
    error: Optional[str] = None
    duration_seconds: Optional[float] = None


class BatchResult(BaseModel):
    """Aggregated results from batch processing."""

    results: list[ProcessingResult] = Field(default_factory=list)
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    duration_seconds: Optional[float] = None

    @property
    def failure_rate(self) -> float:
        return self.failed / self.total if self.total > 0 else 0.0
