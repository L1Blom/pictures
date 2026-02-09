"""XMP metadata writer implementation.

Implements the ``MetadataWriter`` protocol using piexif's UserComment
as a lightweight XMP fallback (the full xmp_toolkit is rarely available).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import piexif
from PIL import Image

from ..config.defaults import DEFAULT_JPEG_QUALITY, XMP_NAMESPACE
from ..core.models import AnalysisResult


class XmpWriter:
    """Writes analysis metadata into XMP / UserComment.

    Satisfies the ``MetadataWriter`` protocol::

        writer: MetadataWriter = XmpWriter()
        writer.write(Path("photo.jpg"), analysis)

    When the full ``xmp_toolkit`` package is not available (common),
    this falls back to embedding minified JSON in the EXIF UserComment
    field — the same approach used by the legacy ``XMPHandler``.
    """

    def __init__(self, jpeg_quality: int = DEFAULT_JPEG_QUALITY):
        self.jpeg_quality = jpeg_quality
        self._has_xmp_toolkit = False
        try:
            from xmp_toolkit import XMPMeta  # type: ignore[import]
            self._has_xmp_toolkit = True
        except ImportError:
            pass

    # ── MetadataWriter Protocol ──────────────────────────────────────

    def write(self, image_path: Path, analysis: AnalysisResult) -> bool:
        """Embed analysis metadata into an image's XMP / UserComment."""
        legacy_dict = self._to_legacy_dict(analysis)
        return self.write_from_dict(image_path, legacy_dict)

    # ── Legacy-compatible methods ────────────────────────────────────

    def write_from_dict(
        self, image_path: Path | str, analysis_data: dict[str, Any]
    ) -> bool:
        """Write XMP from a legacy analysis dict (simple UserComment method)."""
        try:
            metadata = analysis_data.get("metadata", {})
            enhancement = analysis_data.get("enhancement", {})
            location_detection = analysis_data.get("location_detection", {})

            comment_data: dict[str, Any] = {
                "metadata": metadata,
                "enhancement": {
                    k: v for k, v in enhancement.items() if k != "raw_response"
                },
                "timestamp": datetime.now().isoformat(),
            }
            if location_detection:
                comment_data["location_detection"] = location_detection

            # Read existing EXIF
            try:
                exif_dict = piexif.load(str(image_path))
            except Exception:
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}}

            if "Exif" not in exif_dict:
                exif_dict["Exif"] = {}

            comment_json = json.dumps(comment_data, separators=(",", ":"))
            char_code_prefix = b"ASCII\x00\x00\x00"
            exif_dict["Exif"][piexif.ExifIFD.UserComment] = (
                char_code_prefix + comment_json.encode("utf-8")
            )

            exif_bytes = piexif.dump(exif_dict)

            image = Image.open(str(image_path))
            if image.format and image.format.upper() in ("JPEG", "JPG"):
                image.save(
                    str(image_path), "jpeg", exif=exif_bytes, quality=self.jpeg_quality
                )

            return True
        except Exception as e:
            print(
                f"Warning: Could not embed metadata in {image_path} (simple method): {e}"
            )
            return False

    # ── Internal ─────────────────────────────────────────────────────

    def _to_legacy_dict(self, analysis: AnalysisResult) -> dict[str, Any]:
        """Convert AnalysisResult to legacy dict for XMP embedding."""
        return analysis.raw_response if analysis.raw_response else {}
