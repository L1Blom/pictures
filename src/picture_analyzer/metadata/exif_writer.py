"""EXIF metadata writer implementation.

Implements the ``MetadataWriter`` protocol using piexif to embed
analysis results into JPEG image EXIF data.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import piexif
from PIL import Image

from ..config.defaults import (
    DEFAULT_DESCRIPTION_MAX_LENGTH,
    DEFAULT_DESCRIPTION_TRUNCATE_AT,
    DEFAULT_GPS_DATUM,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_METADATA_LANGUAGE,
    LANGUAGE_NAMES,
    LUMINANCE_BLUE,
    LUMINANCE_GREEN,
    LUMINANCE_RED,
    PROBLEMATIC_EXIF_TAGS,
)
from ..core.models import AnalysisResult, GeoLocation


class ExifWriter:
    """Writes analysis metadata into JPEG EXIF tags.

    Satisfies the ``MetadataWriter`` protocol::

        writer: MetadataWriter = ExifWriter()
        writer.write(Path("photo.jpg"), analysis)

    The writer embeds:
      - ``ImageDescription``: human-readable formatted metadata
      - ``UserComment``: minified JSON backup of all metadata
      - ``GPS IFD``: latitude/longitude from geocoding
    """

    def __init__(
        self,
        language: str = DEFAULT_METADATA_LANGUAGE,
        jpeg_quality: int = DEFAULT_JPEG_QUALITY,
        max_description_length: int = DEFAULT_DESCRIPTION_MAX_LENGTH,
    ):
        self.language = language
        self.jpeg_quality = jpeg_quality
        self.max_description_length = max_description_length

    # ── MetadataWriter Protocol ──────────────────────────────────────

    def write(self, image_path: Path, analysis: AnalysisResult) -> bool:
        """Embed analysis metadata into an image's EXIF data.

        For backward compatibility, this also accepts a legacy dict
        via ``write_from_dict``.
        """
        # Convert AnalysisResult back to legacy dict for EXIF embedding
        # (The EXIF structure expects the old metadata/enhancement/location format)
        legacy_dict = self._to_legacy_dict(analysis)
        return self.write_from_dict(image_path, image_path, legacy_dict)

    # ── Legacy-compatible methods ────────────────────────────────────

    def write_from_dict(
        self,
        source_path: Path | str,
        output_path: Path | str,
        analysis_data: dict[str, Any],
    ) -> bool:
        """Write EXIF from a legacy analysis dict.

        This preserves full backward compatibility with the existing
        ``EXIFHandler.write_exif()`` interface.
        """
        try:
            image = Image.open(str(source_path))
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}}

            # Prepare EXIF with analysis data
            exif_dict = self._prepare_exif_dict(exif_dict, analysis_data)

            # Sanitize to avoid piexif dump errors
            exif_dict = self._sanitize_exif_dict(exif_dict)
            exif_bytes = piexif.dump(exif_dict)

            # Save as JPEG
            self._save_jpeg(image, str(output_path), exif_bytes)
            return True

        except Exception as e:
            print(f"Warning: Could not write EXIF data: {e}")
            try:
                image.save(str(output_path))
                return True
            except Exception:
                return False

    def read(self, image_path: Path | str) -> dict[str, Any]:
        """Read EXIF data from an image."""
        try:
            exif_dict = piexif.load(str(image_path))
            return self._parse_exif_dict(exif_dict)
        except Exception as e:
            print(f"Warning: Could not read EXIF data: {e}")
            return {}

    def copy_exif(
        self,
        source_path: str | Path,
        target_path: str | Path,
        output_path: str | Path,
    ) -> bool:
        """Copy EXIF from source image to target image."""
        try:
            exif_dict = piexif.load(str(source_path))
            exif_dict = self._sanitize_exif_dict(exif_dict)
            exif_bytes = piexif.dump(exif_dict)

            image = Image.open(str(target_path))
            self._save_jpeg(image, str(output_path), exif_bytes)
            return True
        except Exception as e:
            print(f"Warning: Could not copy EXIF data: {e}")
            return False

    # ── GPS helpers ──────────────────────────────────────────────────

    def add_gps(self, exif_dict: dict, geo: GeoLocation) -> None:
        """Add GPS coordinates to an EXIF dict from a GeoLocation model."""
        self._add_gps_to_exif(
            exif_dict,
            {"latitude": geo.latitude, "longitude": geo.longitude},
        )

    # ── Internal helpers ─────────────────────────────────────────────

    def _to_legacy_dict(self, analysis: AnalysisResult) -> dict[str, Any]:
        """Convert an AnalysisResult to the legacy dict format."""
        result: dict[str, Any] = {}

        # Metadata section
        metadata: dict[str, Any] = {}
        if analysis.keywords:
            metadata["objects"] = analysis.keywords
        if analysis.people:
            metadata["persons"] = analysis.people
        if analysis.mood:
            metadata["mood_atmosphere"] = analysis.mood
        if analysis.scene_type:
            metadata["scene_type"] = analysis.scene_type
        if analysis.description:
            metadata["location_setting"] = analysis.description
        if analysis.photography_style:
            metadata["photography_style"] = analysis.photography_style
        if analysis.composition_quality:
            metadata["composition_quality"] = analysis.composition_quality
        if analysis.era:
            if analysis.era.time_of_day:
                metadata["time_of_day"] = analysis.era.time_of_day
            if analysis.era.season:
                metadata["season_date"] = analysis.era.season

        result["metadata"] = metadata

        # Location detection
        if analysis.location:
            result["location_detection"] = {
                "country": analysis.location.country or "",
                "region": analysis.location.region or "",
                "city_or_area": analysis.location.city or "",
                "confidence": analysis.location.confidence,
            }
            if analysis.location.coordinates:
                result["gps_coordinates"] = {
                    "latitude": analysis.location.coordinates.latitude,
                    "longitude": analysis.location.coordinates.longitude,
                    "display_name": analysis.location.coordinates.display_name,
                }

        # Enhancement
        if analysis.enhancement_recommendations:
            result["enhancement"] = {
                "recommended_enhancements": [
                    e.raw_text for e in analysis.enhancement_recommendations
                ],
            }

        # Source description
        if analysis.description_context:
            result["source_description"] = analysis.description_context

        # Slide profiles
        if analysis.slide_profile:
            result["slide_profiles"] = [
                {
                    "profile": analysis.slide_profile.profile_name,
                    "confidence": analysis.slide_profile.confidence,
                }
            ]

        # Raw response for backup
        if analysis.raw_response:
            # Merge raw response into result (metadata/enhancement may already be there)
            for key in ("metadata", "enhancement", "location_detection"):
                if key in analysis.raw_response and key not in result:
                    result[key] = analysis.raw_response[key]

        return result

    def _save_jpeg(self, image: Image.Image, output_path: str, exif_bytes: bytes) -> None:
        """Save an image as JPEG with EXIF data."""
        if image.mode in ("RGBA", "LA", "P"):
            rgb = Image.new("RGB", image.size, (255, 255, 255))
            mask = image.split()[-1] if image.mode in ("RGBA", "LA") else None
            rgb.paste(image, mask=mask)
            rgb.save(output_path, "jpeg", exif=exif_bytes, quality=self.jpeg_quality)
        elif image.mode != "RGB":
            image.convert("RGB").save(
                output_path, "jpeg", exif=exif_bytes, quality=self.jpeg_quality
            )
        else:
            image.save(output_path, "jpeg", exif=exif_bytes, quality=self.jpeg_quality)

    def _format_metadata_description(
        self,
        metadata: dict[str, Any],
        location_detection: dict[str, Any] | None = None,
        source_description: str | None = None,
    ) -> str:
        """Format metadata into a readable description for ImageDescription."""
        lines: list[str] = []

        # Language-specific labels
        translations = {
            "nl": {
                "LOCATION": "LOCATIE",
                "Confidence": "Betrouwbaarheid",
                "Location uncertain": "Locatie onzeker",
                "Objects": "Objecten",
                "Persons": "Personen",
                "Weather": "Weer",
                "Mood/Atmosphere": "Sfeer/Atmosfeer",
                "Time of Day": "Tijd van de dag",
                "Season/Date": "Seizoen/Datum",
                "Scene Type": "Type scène",
                "Setting": "Omgeving",
                "Activity": "Activiteit",
                "Photography Style": "Fotografische stijl",
                "Composition Quality": "Samenstelling kwaliteit",
            },
            "en": {
                "LOCATION": "LOCATION",
                "Confidence": "Confidence",
                "Location uncertain": "Location uncertain",
                "Objects": "Objects",
                "Persons": "Persons",
                "Weather": "Weather",
                "Mood/Atmosphere": "Mood/Atmosphere",
                "Time of Day": "Time of Day",
                "Season/Date": "Season/Date",
                "Scene Type": "Scene Type",
                "Setting": "Setting",
                "Activity": "Activity",
                "Photography Style": "Photography Style",
                "Composition Quality": "Composition Quality",
            },
        }

        lang_trans = translations.get(self.language, translations["en"])

        # Location section
        if location_detection:
            country = location_detection.get("country", "")
            city = location_detection.get("city_or_area", "")
            region = location_detection.get("region", "")
            confidence = location_detection.get("confidence", "")

            parts = [
                p
                for p in [country, region, city]
                if p and p.lower() not in ("uncertain", "unknown")
            ]
            if parts:
                conf_str = (
                    f" ({lang_trans['Confidence']}: {confidence}%)" if confidence else ""
                )
                lines.append(f"{lang_trans['LOCATION']}: {', '.join(parts)}{conf_str}")
            elif confidence:
                lines.append(
                    f"{lang_trans['Location uncertain']} "
                    f"({lang_trans['Confidence']}: {confidence}%)"
                )
            if lines:
                lines.append("")

        # Field labels
        field_labels = {
            "objects": lang_trans.get("Objects", "Objects"),
            "persons": lang_trans.get("Persons", "Persons"),
            "weather": lang_trans.get("Weather", "Weather"),
            "mood_atmosphere": lang_trans.get("Mood/Atmosphere", "Mood/Atmosphere"),
            "mood": lang_trans.get("Mood/Atmosphere", "Mood/Atmosphere"),
            "time_of_day": lang_trans.get("Time of Day", "Time of Day"),
            "season_date": lang_trans.get("Season/Date", "Season/Date"),
            "scene_type": lang_trans.get("Scene Type", "Scene Type"),
            "location_setting": lang_trans.get("Setting", "Setting"),
            "activity_action": lang_trans.get("Activity", "Activity"),
            "activity": lang_trans.get("Activity", "Activity"),
            "photography_style": lang_trans.get("Photography Style", "Photography Style"),
            "composition_quality": lang_trans.get("Composition Quality", "Composition Quality"),
        }

        for key, label in field_labels.items():
            if key in metadata:
                value = metadata[key]
                if isinstance(value, list):
                    value_str = ", ".join(str(v) for v in value)
                else:
                    value_str = str(value)
                lines.append(f"{label}: {value_str}")

        # Extra fields
        for key, value in metadata.items():
            if key not in field_labels:
                label = key.replace("_", " ").title()
                if isinstance(value, list):
                    value_str = ", ".join(str(v) for v in value[:5])
                    if len(value) > 5:
                        value_str += f", ... (+{len(value) - 5} more)"
                elif isinstance(value, dict):
                    value_str = str(value)
                else:
                    value_str = str(value)
                lines.append(f"{label}: {value_str}")

        # Source description
        if source_description:
            lines.append("")
            lines.append("SOURCE DESCRIPTION (from description.txt):")
            lines.append(source_description)

        description = "\n".join(lines)
        if len(description) > self.max_description_length:
            description = description[: self.max_description_length]
            last_nl = description.rfind("\n")
            if last_nl > DEFAULT_DESCRIPTION_TRUNCATE_AT:
                description = description[:last_nl] + "\n[... truncated]"
        return description

    def _prepare_exif_dict(
        self, exif_dict: dict, analysis_data: dict[str, Any]
    ) -> dict:
        """Prepare EXIF dictionary from analysis data."""
        if "0th" not in exif_dict:
            exif_dict["0th"] = {}
        if "Exif" not in exif_dict:
            exif_dict["Exif"] = {}

        metadata = analysis_data.get("metadata", analysis_data)
        location_detection = analysis_data.get("location_detection", {})
        source_description = analysis_data.get("source_description")

        # ImageDescription — human-readable
        if isinstance(metadata, dict):
            description = self._format_metadata_description(
                metadata, location_detection, source_description
            )
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = description.encode("utf-8")

        # UserComment — JSON backup
        backup_data: dict[str, Any] = {"metadata": metadata}
        if location_detection:
            backup_data["location_detection"] = location_detection
        if source_description:
            backup_data["source_description"] = source_description
        if isinstance(metadata, dict):
            backup_data["metadata"] = {
                k: v for k, v in metadata.items() if k != "raw_response"
            }

        backup_json = json.dumps(backup_data, separators=(",", ":"))
        char_code_prefix = b"ASCII\x00\x00\x00"
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = (
            char_code_prefix + backup_json.encode("utf-8")
        )

        # GPS
        coordinates = analysis_data.get("gps_coordinates")
        if coordinates:
            self._add_gps_to_exif(exif_dict, coordinates)

        return exif_dict

    @staticmethod
    def _add_gps_to_exif(exif_dict: dict, coordinates: dict[str, float]) -> None:
        """Add GPS coordinates to EXIF dict."""
        if not coordinates or "latitude" not in coordinates or "longitude" not in coordinates:
            return

        try:
            lat = coordinates["latitude"]
            lon = coordinates["longitude"]

            if "GPS" not in exif_dict:
                exif_dict["GPS"] = {}

            def dms_from_decimal(decimal: float) -> tuple:
                abs_val = abs(decimal)
                degrees = int(abs_val)
                minutes_dec = (abs_val - degrees) * 60
                minutes = int(minutes_dec)
                seconds = int((minutes_dec - minutes) * 60 * 100)
                return ((degrees, 1), (minutes, 1), (seconds, 100))

            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = dms_from_decimal(lat)
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"N" if lat >= 0 else b"S"
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = dms_from_decimal(lon)
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon >= 0 else b"W"
            exif_dict["GPS"][piexif.GPSIFD.GPSVersionID] = b"\x02\x02\x00\x00"
            exif_dict["GPS"][piexif.GPSIFD.GPSMapDatum] = DEFAULT_GPS_DATUM.encode()
        except Exception as e:
            print(f"Warning: Could not add GPS data to EXIF: {e}")

    @staticmethod
    def _sanitize_exif_dict(exif_dict: dict) -> dict:
        """Remove/fix malformed EXIF values that piexif cannot dump."""
        for ifd_name in ("0th", "1st", "Exif", "GPS", "Interop"):
            if ifd_name not in exif_dict:
                continue
            to_remove = []
            for tag_id, value in exif_dict[ifd_name].items():
                if isinstance(value, int) and tag_id in (282, 283):
                    to_remove.append(tag_id)
                elif isinstance(value, int) and tag_id == 296 and value not in (1, 2, 3):
                    to_remove.append(tag_id)
            for tid in to_remove:
                del exif_dict[ifd_name][tid]
        return exif_dict

    @staticmethod
    def _parse_exif_dict(exif_dict: dict) -> dict[str, Any]:
        """Parse EXIF dictionary into readable format."""
        result = {}
        try:
            for ifd_name, tag_group in (("0th", "0th"), ("Exif", "Exif")):
                if ifd_name in exif_dict:
                    for tag, value in exif_dict[ifd_name].items():
                        tag_name = piexif.TAGS[tag_group][tag]["name"]
                        if isinstance(value, bytes):
                            try:
                                result[tag_name] = value.decode("utf-8")
                            except UnicodeDecodeError:
                                result[tag_name] = str(value)
                        else:
                            result[tag_name] = value
        except Exception as e:
            print(f"Warning: Error parsing EXIF: {e}")
        return result
