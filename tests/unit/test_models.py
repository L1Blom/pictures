"""Tests for core data models (Pydantic).

Validates field constraints, frozen immutability, computed properties,
enum membership, and serialization round-trips.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from picture_analyzer.core.models import (
    AnalysisContext,
    AnalysisResult,
    ColorBalance,
    Enhancement,
    EnhancementAction,
    EraInfo,
    GeoLocation,
    ImageData,
    LocationInfo,
    ProcessingResult,
    ReportFormat,
    SlideProfile,
    SlideProfileDetection,
    SlideProfileName,
)

# ── Enums ────────────────────────────────────────────────────────────


class TestEnums:
    def test_slide_profile_name_values(self):
        assert SlideProfileName.FADED == "faded"
        assert SlideProfileName.AUTO == "auto"
        assert len(SlideProfileName) == 7

    def test_enhancement_action_values(self):
        assert EnhancementAction.BRIGHTNESS == "brightness"
        assert EnhancementAction.NO_ENHANCEMENTS == "no_enhancements"
        assert len(EnhancementAction) >= 17

    def test_report_format_values(self):
        assert ReportFormat.MARKDOWN == "markdown"
        assert ReportFormat.HTML == "html"

    def test_enum_is_str_subclass(self):
        """Enum values are plain strings via .value."""
        assert SlideProfileName.FADED.value == "faded"
        assert EnhancementAction.BRIGHTNESS.value == "brightness"
        assert isinstance(SlideProfileName.FADED, str)
        assert isinstance(EnhancementAction.BRIGHTNESS, str)


# ── GeoLocation ──────────────────────────────────────────────────────


class TestGeoLocation:
    def test_valid(self):
        g = GeoLocation(latitude=51.5, longitude=-3.2)
        assert g.latitude == 51.5
        assert g.longitude == -3.2

    def test_as_tuple(self):
        g = GeoLocation(latitude=52.0, longitude=4.5)
        assert g.as_tuple == (52.0, 4.5)

    def test_display_name(self):
        g = GeoLocation(latitude=0, longitude=0, display_name="Null Island")
        assert g.display_name == "Null Island"

    def test_frozen(self):
        g = GeoLocation(latitude=1, longitude=2)
        with pytest.raises(ValidationError):
            g.latitude = 99  # type: ignore[misc]

    def test_latitude_range(self):
        with pytest.raises(ValidationError):
            GeoLocation(latitude=91, longitude=0)
        with pytest.raises(ValidationError):
            GeoLocation(latitude=-91, longitude=0)

    def test_longitude_range(self):
        with pytest.raises(ValidationError):
            GeoLocation(longitude=181, latitude=0)
        with pytest.raises(ValidationError):
            GeoLocation(longitude=-181, latitude=0)

    def test_edge_coordinates(self):
        g1 = GeoLocation(latitude=-90, longitude=-180)
        g2 = GeoLocation(latitude=90, longitude=180)
        assert g1.as_tuple == (-90, -180)
        assert g2.as_tuple == (90, 180)

    def test_json_roundtrip(self):
        g = GeoLocation(latitude=51.5, longitude=3.4, display_name="NL")
        data = json.loads(g.model_dump_json())
        g2 = GeoLocation(**data)
        assert g == g2


# ── LocationInfo ─────────────────────────────────────────────────────


class TestLocationInfo:
    def test_basic(self):
        loc = LocationInfo(location_name="Amsterdam, Netherlands", country="NL")
        assert loc.location_name == "Amsterdam, Netherlands"
        assert loc.confidence == 0  # default
        assert loc.source == "ai"  # default

    def test_confidence_range(self):
        LocationInfo(location_name="x", confidence=0)
        LocationInfo(location_name="x", confidence=100)
        with pytest.raises(ValidationError):
            LocationInfo(location_name="x", confidence=-1)
        with pytest.raises(ValidationError):
            LocationInfo(location_name="x", confidence=101)

    def test_with_coordinates(self):
        loc = LocationInfo(
            location_name="Amsterdam",
            coordinates=GeoLocation(latitude=52.37, longitude=4.89),
        )
        assert loc.coordinates.latitude == pytest.approx(52.37)

    def test_frozen(self):
        loc = LocationInfo(location_name="x")
        with pytest.raises(ValidationError):
            loc.location_name = "y"  # type: ignore[misc]


# ── Enhancement ──────────────────────────────────────────────────────


class TestEnhancement:
    def test_defaults(self):
        e = Enhancement(action="brightness")
        assert e.direction == "increase"
        assert e.amount_percent is None
        assert e.raw_text == ""

    def test_full(self):
        e = Enhancement(
            action="contrast",
            direction="decrease",
            amount_percent=15.0,
            raw_text="CONTRAST: decrease by 15%",
        )
        assert e.direction == "decrease"
        assert e.amount_percent == 15.0


# ── ColorBalance ─────────────────────────────────────────────────────


class TestColorBalance:
    def test_defaults(self):
        cb = ColorBalance()
        assert cb.red == 1.0
        assert cb.green == 1.0
        assert cb.blue == 1.0

    def test_validation(self):
        with pytest.raises(ValidationError):
            ColorBalance(red=-0.1)
        with pytest.raises(ValidationError):
            ColorBalance(blue=3.1)

    def test_frozen(self):
        cb = ColorBalance(red=1.2)
        with pytest.raises(ValidationError):
            cb.red = 1.5  # type: ignore[misc]


# ── SlideProfile ─────────────────────────────────────────────────────


class TestSlideProfile:
    def test_basic(self):
        sp = SlideProfile(name="test")
        assert sp.name == "test"
        assert sp.saturation == 1.0  # default
        assert sp.color_balance.red == 1.0

    def test_full(self):
        sp = SlideProfile(
            name="custom",
            saturation=1.5,
            contrast=1.3,
            brightness=1.1,
            sharpness=1.2,
            color_balance=ColorBalance(red=1.1, green=0.9, blue=0.85),
            denoise=True,
            denoise_radius=1.0,
        )
        assert sp.contrast == 1.3
        assert sp.color_balance.blue == 0.85

    def test_field_ranges(self):
        with pytest.raises(ValidationError):
            SlideProfile(name="x", saturation=-0.1)
        with pytest.raises(ValidationError):
            SlideProfile(name="x", contrast=3.1)
        with pytest.raises(ValidationError):
            SlideProfile(name="x", denoise_radius=5.1)


# ── SlideProfileDetection ───────────────────────────────────────────


class TestSlideProfileDetection:
    def test_basic(self):
        d = SlideProfileDetection(profile_name="faded", confidence=85)
        assert d.confidence == 85

    def test_confidence_range(self):
        with pytest.raises(ValidationError):
            SlideProfileDetection(profile_name="x", confidence=-1)
        with pytest.raises(ValidationError):
            SlideProfileDetection(profile_name="x", confidence=101)


# ── EraInfo ──────────────────────────────────────────────────────────


class TestEraInfo:
    def test_defaults(self):
        e = EraInfo()
        assert e.estimated_decade is None
        assert e.confidence == 0

    def test_year_range(self):
        EraInfo(estimated_year=1800)
        EraInfo(estimated_year=2100)
        with pytest.raises(ValidationError):
            EraInfo(estimated_year=1799)
        with pytest.raises(ValidationError):
            EraInfo(estimated_year=2101)


# ── AnalysisResult ───────────────────────────────────────────────────


class TestAnalysisResult:
    def test_defaults(self):
        r = AnalysisResult()
        assert r.title == ""
        assert r.keywords == []
        assert r.people == []
        assert r.location is None
        assert r.enhancement_recommendations == []

    def test_full_construction(self):
        r = AnalysisResult(
            title="Beach Photo",
            description="Family at the beach",
            keywords=["beach", "family", "summer"],
            people=["John", "Jane"],
            people_count=2,
            location=LocationInfo(
                location_name="Scheveningen",
                country="Netherlands",
            ),
            era=EraInfo(estimated_decade="1980s", season="summer"),
            enhancement_recommendations=[
                Enhancement(action="brightness", amount_percent=10),
            ],
            slide_profile=SlideProfileDetection(
                profile_name="faded", confidence=80,
            ),
        )
        assert len(r.keywords) == 3
        assert r.people_count == 2
        assert r.location.country == "Netherlands"
        assert r.era.estimated_decade == "1980s"
        assert r.slide_profile.confidence == 80

    def test_json_roundtrip(self):
        r = AnalysisResult(
            title="Test",
            keywords=["a", "b"],
            location=LocationInfo(
                location_name="Here",
                coordinates=GeoLocation(latitude=1.0, longitude=2.0),
            ),
        )
        data = json.loads(r.model_dump_json())
        r2 = AnalysisResult(**data)
        assert r.title == r2.title
        assert r.keywords == r2.keywords

    def test_is_not_frozen(self):
        """AnalysisResult is mutable (no frozen=True) — verify this."""
        r = AnalysisResult()
        r.title = "Updated"
        assert r.title == "Updated"


# ── AnalysisContext ──────────────────────────────────────────────────


class TestAnalysisContext:
    def test_defaults(self):
        ctx = AnalysisContext()
        assert ctx.language == "en"
        assert ctx.detect_slide_profiles is True

    def test_override(self):
        ctx = AnalysisContext(language="nl", detect_location=False)
        assert ctx.language == "nl"
        assert ctx.detect_location is False


# ── ImageData ────────────────────────────────────────────────────────


class TestImageData:
    def test_basic(self, tmp_path):
        p = tmp_path / "img.jpg"
        p.touch()
        img = ImageData(path=p, mime_type="image/jpeg")
        assert img.mime_type == "image/jpeg"
        assert img.base64_data is None

    def test_base64_excluded_from_repr(self, tmp_path):
        p = tmp_path / "img.jpg"
        p.touch()
        img = ImageData(path=p, mime_type="image/jpeg", base64_data="abc123")
        assert "abc123" not in repr(img)


# ── ProcessingResult ─────────────────────────────────────────────────


class TestProcessingResult:
    def test_success(self, tmp_path):
        r = ProcessingResult(source_path=tmp_path / "photo.jpg")
        assert r.success is True
        assert r.error is None

    def test_failure(self, tmp_path):
        r = ProcessingResult(
            source_path=tmp_path / "photo.jpg",
            success=False,
            error="Timeout",
        )
        assert r.success is False
        assert r.error == "Timeout"
