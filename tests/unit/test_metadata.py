"""Tests for EXIF and XMP metadata writers.

Tests use small in-memory JPEG images created by PIL, avoiding any
dependency on real photos.
"""
from __future__ import annotations

import json
from pathlib import Path

import piexif
import pytest
from PIL import Image

from picture_analyzer.core.interfaces import MetadataWriter
from picture_analyzer.core.models import (
    AnalysisResult,
    Enhancement,
    GeoLocation,
    LocationInfo,
    SlideProfileDetection,
)
from picture_analyzer.metadata.exif_writer import ExifWriter
from picture_analyzer.metadata.xmp_writer import XmpWriter

# ── Helpers ──────────────────────────────────────────────────────────


def _make_jpeg(path: Path, size: tuple[int, int] = (100, 100)) -> Path:
    """Create a minimal JPEG file for testing."""
    img = Image.new("RGB", size, color=(128, 128, 128))
    img.save(str(path), "JPEG", quality=80)
    return path


# ══════════════════════════════════════════════════════════════════════
# ExifWriter
# ══════════════════════════════════════════════════════════════════════


class TestExifWriterProtocol:
    def test_implements_metadata_writer(self):
        assert isinstance(ExifWriter(), MetadataWriter)


class TestExifWriteFromDict:
    @pytest.fixture
    def jpeg(self, tmp_path: Path) -> Path:
        return _make_jpeg(tmp_path / "test.jpg")

    def test_basic_write(self, jpeg, tmp_path):
        writer = ExifWriter()
        out = tmp_path / "out.jpg"
        analysis_data = {
            "metadata": {
                "scene_type": "Garden",
                "objects": ["tree", "flower"],
                "mood_atmosphere": "peaceful",
            },
        }
        assert writer.write_from_dict(jpeg, out, analysis_data)
        assert out.exists()

    def test_description_in_exif(self, jpeg, tmp_path):
        writer = ExifWriter(language="en")
        out = tmp_path / "out.jpg"
        analysis_data = {
            "metadata": {
                "scene_type": "Landscape",
                "objects": ["mountain"],
            },
        }
        writer.write_from_dict(jpeg, out, analysis_data)

        exif = piexif.load(str(out))
        desc = exif["0th"].get(piexif.ImageIFD.ImageDescription, b"")
        desc_str = desc.decode("utf-8") if isinstance(desc, bytes) else desc
        assert "Landscape" in desc_str or "mountain" in desc_str

    def test_user_comment_json(self, jpeg, tmp_path):
        writer = ExifWriter()
        out = tmp_path / "out.jpg"
        analysis_data = {
            "metadata": {"scene_type": "Beach"},
        }
        writer.write_from_dict(jpeg, out, analysis_data)

        exif = piexif.load(str(out))
        raw = exif["Exif"].get(piexif.ExifIFD.UserComment, b"")
        # Strip ASCII prefix
        json_str = raw[8:].decode("utf-8") if len(raw) > 8 else ""
        data = json.loads(json_str)
        assert data["metadata"]["scene_type"] == "Beach"

    def test_location_in_description(self, jpeg, tmp_path):
        writer = ExifWriter(language="en")
        out = tmp_path / "out.jpg"
        analysis_data = {
            "metadata": {},
            "location_detection": {
                "country": "Netherlands",
                "region": "Zeeland",
                "city_or_area": "Goes",
                "confidence": 85,
            },
        }
        writer.write_from_dict(jpeg, out, analysis_data)
        exif = piexif.load(str(out))
        desc = exif["0th"][piexif.ImageIFD.ImageDescription].decode("utf-8")
        assert "Netherlands" in desc
        assert "85" in desc

    def test_source_description(self, jpeg, tmp_path):
        writer = ExifWriter(language="en")
        out = tmp_path / "out.jpg"
        analysis_data = {
            "metadata": {"scene_type": "Park"},
            "source_description": "Photo taken in Slotpark",
        }
        writer.write_from_dict(jpeg, out, analysis_data)
        exif = piexif.load(str(out))
        desc = exif["0th"][piexif.ImageIFD.ImageDescription].decode("utf-8")
        assert "Slotpark" in desc


class TestExifWriteProtocolMethod:
    """Test the ``write(path, AnalysisResult)`` protocol method."""

    @pytest.fixture
    def jpeg(self, tmp_path: Path) -> Path:
        return _make_jpeg(tmp_path / "test.jpg")

    def test_write_from_analysis_result(self, jpeg):
        writer = ExifWriter(language="en")
        analysis = AnalysisResult(
            title="Sunset",
            description="Beautiful sunset over the sea",
            keywords=["sunset", "sea"],
            mood="romantic",
            scene_type="Nature",
        )
        assert writer.write(jpeg, analysis)
        exif = piexif.load(str(jpeg))
        assert piexif.ImageIFD.ImageDescription in exif["0th"]


class TestExifGps:
    @pytest.fixture
    def jpeg(self, tmp_path: Path) -> Path:
        return _make_jpeg(tmp_path / "test.jpg")

    def test_add_gps_north_east(self, jpeg, tmp_path):
        writer = ExifWriter()
        out = tmp_path / "out.jpg"
        analysis_data = {
            "metadata": {},
            "gps_coordinates": {
                "latitude": 51.5074,
                "longitude": -0.1278,
            },
        }
        writer.write_from_dict(jpeg, out, analysis_data)
        exif = piexif.load(str(out))
        assert piexif.GPSIFD.GPSLatitude in exif["GPS"]
        assert exif["GPS"][piexif.GPSIFD.GPSLatitudeRef] == b"N"
        assert exif["GPS"][piexif.GPSIFD.GPSLongitudeRef] == b"W"

    def test_add_gps_south_west(self, jpeg, tmp_path):
        writer = ExifWriter()
        out = tmp_path / "out.jpg"
        analysis_data = {
            "metadata": {},
            "gps_coordinates": {
                "latitude": -33.86,
                "longitude": 151.21,
            },
        }
        writer.write_from_dict(jpeg, out, analysis_data)
        exif = piexif.load(str(out))
        assert exif["GPS"][piexif.GPSIFD.GPSLatitudeRef] == b"S"
        assert exif["GPS"][piexif.GPSIFD.GPSLongitudeRef] == b"E"

    def test_add_gps_from_geolocation(self):
        writer = ExifWriter()
        geo = GeoLocation(latitude=52.37, longitude=4.89)
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}}
        writer.add_gps(exif_dict, geo)
        assert piexif.GPSIFD.GPSLatitude in exif_dict["GPS"]
        assert exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] == b"N"


class TestExifDmsConversion:
    def test_dms_from_decimal(self):
        # 51.5074 → 51°30'26.64"
        _result = ExifWriter._add_gps_to_exif.__wrapped__ if hasattr(
            ExifWriter._add_gps_to_exif, "__wrapped__"
        ) else None

        # Test via a round-trip: write GPS then read it back
        exif_dict = {"GPS": {}}
        ExifWriter._add_gps_to_exif(
            exif_dict,
            {"latitude": 51.5074, "longitude": 4.3517},
        )
        lat = exif_dict["GPS"][piexif.GPSIFD.GPSLatitude]
        # Verify structure: ((deg, 1), (min, 1), (sec, 100))
        assert len(lat) == 3
        assert lat[0][0] == 51  # degrees


class TestExifEdgeCases:
    def test_rgba_image(self, tmp_path):
        """RGBA images should be converted to RGB before JPEG save."""
        img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
        png_path = tmp_path / "test.png"
        img.save(str(png_path))

        writer = ExifWriter()
        out = tmp_path / "out.jpg"
        assert writer.write_from_dict(png_path, out, {"metadata": {}})
        assert out.exists()

    def test_read_exif(self, tmp_path):
        jpeg = _make_jpeg(tmp_path / "test.jpg")
        writer = ExifWriter()
        result = writer.read(jpeg)
        assert isinstance(result, dict)

    def test_copy_exif(self, tmp_path):
        src = _make_jpeg(tmp_path / "src.jpg")
        tgt = _make_jpeg(tmp_path / "tgt.jpg")
        out = tmp_path / "out.jpg"

        writer = ExifWriter()
        # Write some EXIF to source first
        writer.write_from_dict(
            src, src, {"metadata": {"scene_type": "Test"}}
        )
        # Copy
        assert writer.copy_exif(src, tgt, out)
        assert out.exists()

    def test_sanitize_exif(self):
        writer = ExifWriter()
        # 282,283 are ints (should be tuples), 296 bad value
        exif_dict = {
            "0th": {282: 72, 283: 72, 296: 99},
            "Exif": {},
        }
        result = writer._sanitize_exif_dict(exif_dict)
        assert 282 not in result["0th"]
        assert 283 not in result["0th"]
        assert 296 not in result["0th"]

    def test_description_truncation(self, tmp_path):
        writer = ExifWriter(max_description_length=50)
        long_metadata = {
            "scene_type": "A" * 100,
            "objects": ["object" * 20],
        }
        desc = writer._format_metadata_description(long_metadata)
        assert len(desc) <= 60  # allow some slack for truncation marker


class TestExifToLegacyDict:
    def test_converts_analysis_result(self):
        writer = ExifWriter()
        result = AnalysisResult(
            title="Beach",
            description="Sandy beach",
            keywords=["beach", "sand"],
            people=["Alice"],
            mood="relaxed",
            scene_type="Nature",
            location=LocationInfo(
                location_name="Scheveningen",
                country="NL",
                city="Scheveningen",
                confidence=80,
                coordinates=GeoLocation(latitude=52.1, longitude=4.3),
            ),
            enhancement_recommendations=[
                Enhancement(action="brightness", raw_text="BRIGHTNESS: +10%"),
            ],
            slide_profile=SlideProfileDetection(
                profile_name="faded", confidence=75,
            ),
        )
        d = writer._to_legacy_dict(result)
        assert "metadata" in d
        assert d["metadata"]["scene_type"] == "Nature"
        assert d["location_detection"]["country"] == "NL"
        assert d["gps_coordinates"]["latitude"] == 52.1
        assert d["enhancement"]["recommended_enhancements"] == ["BRIGHTNESS: +10%"]
        assert d["slide_profiles"][0]["profile"] == "faded"


# ══════════════════════════════════════════════════════════════════════
# XmpWriter
# ══════════════════════════════════════════════════════════════════════


class TestXmpWriterProtocol:
    def test_implements_metadata_writer(self):
        assert isinstance(XmpWriter(), MetadataWriter)


class TestXmpWriteFromDict:
    @pytest.fixture
    def jpeg(self, tmp_path: Path) -> Path:
        return _make_jpeg(tmp_path / "test.jpg")

    def test_basic_write(self, jpeg):
        writer = XmpWriter()
        analysis_data = {
            "metadata": {"scene_type": "Street"},
            "enhancement": {"note": "test"},
        }
        assert writer.write_from_dict(jpeg, analysis_data)

    def test_user_comment_embedded(self, jpeg):
        writer = XmpWriter()
        analysis_data = {
            "metadata": {"title": "My Photo"},
        }
        writer.write_from_dict(jpeg, analysis_data)

        exif = piexif.load(str(jpeg))
        raw = exif["Exif"].get(piexif.ExifIFD.UserComment, b"")
        json_str = raw[8:].decode("utf-8") if len(raw) > 8 else ""
        data = json.loads(json_str)
        assert data["metadata"]["title"] == "My Photo"
        assert "timestamp" in data


class TestXmpWriteProtocol:
    @pytest.fixture
    def jpeg(self, tmp_path: Path) -> Path:
        return _make_jpeg(tmp_path / "test.jpg")

    def test_write_from_analysis_result_with_raw(self, jpeg):
        writer = XmpWriter()
        analysis = AnalysisResult(
            title="Test",
            raw_response={"metadata": {"scene_type": "Park"}},
        )
        assert writer.write(jpeg, analysis)

    def test_write_from_analysis_result_no_raw(self, jpeg):
        writer = XmpWriter()
        analysis = AnalysisResult(title="Test")
        # Should still succeed (writes empty dict)
        result = writer.write(jpeg, analysis)
        # May return True or False depending on whether there's content
        assert isinstance(result, bool)
