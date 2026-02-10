"""Integration tests: enhance → metadata pipeline.

These tests exercise the full path from enhancement recommendations
through the filter pipeline to metadata embedding.  They use real
(tiny) JPEG images but do NOT call the OpenAI API.
"""
from __future__ import annotations

import json
from pathlib import Path

import piexif
from PIL import Image

from picture_analyzer.core.models import AnalysisResult
from picture_analyzer.enhancers.pipeline import (
    RecommendationParser,
    enhance_image,
)
from picture_analyzer.metadata.exif_writer import ExifWriter
from picture_analyzer.metadata.xmp_writer import XmpWriter


class TestEnhanceThenWriteExif:
    """Enhance an image, then embed EXIF metadata."""

    def test_end_to_end(
        self,
        tiny_jpeg: Path,
        sample_analysis: AnalysisResult,
        tmp_path,
    ):
        enhanced = tmp_path / "enhanced.jpg"

        # Step 1: enhance
        recs = [e.raw_text for e in sample_analysis.enhancement_recommendations]
        result = enhance_image(str(tiny_jpeg), recs, output_path=str(enhanced))
        assert result is not None
        assert enhanced.exists()

        # Step 2: write EXIF
        writer = ExifWriter(language="en")
        ok = writer.write(enhanced, sample_analysis)
        assert ok

        # Verify: EXIF description contains scene info
        exif = piexif.load(str(enhanced))
        desc = exif["0th"].get(piexif.ImageIFD.ImageDescription, b"")
        desc_str = desc.decode("utf-8") if isinstance(desc, bytes) else desc
        assert "Nature" in desc_str or "sunset" in desc_str.lower()

        # Verify: GPS tags
        assert piexif.GPSIFD.GPSLatitude in exif["GPS"]

    def test_enhanced_image_is_valid(self, tiny_jpeg, tmp_path):
        out = tmp_path / "out.jpg"
        enhance_image(
            str(tiny_jpeg),
            ["BRIGHTNESS: increase by 5%"],
            output_path=str(out),
        )
        img = Image.open(str(out))
        assert img.mode == "RGB"
        assert img.size == (40, 40)


class TestEnhanceThenWriteXmp:
    """Enhance an image, then embed XMP/UserComment metadata."""

    def test_end_to_end(
        self,
        tiny_jpeg: Path,
        sample_analysis: AnalysisResult,
        tmp_path,
    ):
        enhanced = tmp_path / "enhanced.jpg"

        recs = [e.raw_text for e in sample_analysis.enhancement_recommendations]
        enhance_image(str(tiny_jpeg), recs, output_path=str(enhanced))

        writer = XmpWriter()
        ok = writer.write(enhanced, sample_analysis)
        assert ok

        # UserComment should contain JSON
        exif = piexif.load(str(enhanced))
        raw = exif["Exif"].get(piexif.ExifIFD.UserComment, b"")
        json_str = raw[8:].decode("utf-8") if len(raw) > 8 else ""
        data = json.loads(json_str)
        assert "metadata" in data


class TestSlideRestoreChain:
    """Test slide restore followed by EXIF writing."""

    def test_restore_then_exif(
        self,
        tiny_jpeg: Path,
        sample_analysis: AnalysisResult,
        tmp_path,
    ):
        from picture_analyzer.enhancers.profiles.slide_restorer import SlideRestorer

        restored = tmp_path / "restored.jpg"
        restorer = SlideRestorer()
        result = restorer.auto_restore(
            tiny_jpeg,
            analysis_result=sample_analysis,
            output_path=restored,
        )
        assert result is not None

        writer = ExifWriter(language="en")
        ok = writer.write(Path(result), sample_analysis)
        assert ok


class TestParsePipeline:
    """Test the full RecommendationParser → pipeline → run chain."""

    def test_complex_recommendation_set(self, tiny_jpeg: Path, tmp_path):
        recs = [
            "BRIGHTNESS: increase by 8%",
            "CONTRAST: boost by 12%",
            "SATURATION: increase by 10%",
            "SHARPNESS: enhance by 5%",
            "VIBRANCE: increase by 15%",
            "CLARITY: boost by 20%",
        ]
        parser = RecommendationParser()
        pipeline = parser.parse(recs)
        # Should pick up all 6
        assert len(pipeline) >= 6

        img = Image.open(str(tiny_jpeg))
        result = pipeline.run(img)
        assert result.size == img.size

    def test_mixed_recommendation_types(self):
        parser = RecommendationParser()
        recs = [
            "BRIGHTNESS: increase by 10%",
            {"action": "CONTRAST: boost by 20%"},
            {"text": "SHARPNESS: enhance by 5%"},
        ]
        pipeline = parser.parse(recs)
        assert len(pipeline) >= 3


class TestExifRoundTrip:
    """Write EXIF then read it back."""

    def test_write_read_roundtrip(
        self,
        tiny_jpeg: Path,
        sample_analysis: AnalysisResult,
        tmp_path,
    ):
        out = tmp_path / "roundtrip.jpg"
        writer = ExifWriter(language="en")
        writer.write_from_dict(tiny_jpeg, out, sample_analysis.raw_response)

        data = writer.read(out)
        assert isinstance(data, dict)

    def test_copy_exif_preserves_tags(
        self,
        tiny_jpeg: Path,
        sample_analysis: AnalysisResult,
        tmp_path,
    ):
        src = tmp_path / "src.jpg"
        tgt = tmp_path / "tgt.jpg"
        final = tmp_path / "final.jpg"

        # Create two copies
        Image.open(str(tiny_jpeg)).save(str(src), "JPEG")
        Image.open(str(tiny_jpeg)).save(str(tgt), "JPEG")

        writer = ExifWriter(language="en")
        writer.write_from_dict(tiny_jpeg, src, sample_analysis.raw_response)
        writer.copy_exif(src, tgt, final)

        assert final.exists()
        exif = piexif.load(str(final))
        assert piexif.ImageIFD.ImageDescription in exif["0th"]
