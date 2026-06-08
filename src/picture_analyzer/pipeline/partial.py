"""Utilities for loading an existing analysis JSON as a pipeline partial result.

This allows re-running only specific pipeline steps while preserving all
other data already present in the JSON.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core.models import AnalysisResult, LocationInfo, SlideProfileDetection

logger = logging.getLogger(__name__)


def load_partial_from_json(json_path: Path) -> AnalysisResult:
    """Deserialise an existing ``*_analyzed.json`` into an :class:`AnalysisResult`.

    The returned result has ``raw_response`` fully populated from the JSON so
    that individual pipeline steps can merge their output into it without
    overwriting already-computed sections.

    Args:
        json_path: Path to an existing ``*_analyzed.json`` file.

    Returns:
        An :class:`AnalysisResult` populated from the JSON.

    Raises:
        FileNotFoundError: If *json_path* does not exist.
        ValueError: If the file is not valid JSON.
    """
    if not json_path.exists():
        raise FileNotFoundError(f"Analysis JSON not found: {json_path}")

    try:
        data: dict = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {json_path}: {exc}") from exc

    # Reconstruct lightweight typed fields from the JSON where possible,
    # so that pipeline steps that read from partial.<field> still work.

    # Location
    location: Optional[LocationInfo] = None
    loc_data = data.get("location_detection") or data.get("location")
    if isinstance(loc_data, dict) and loc_data.get("city_or_area"):
        location = LocationInfo(
            location_name=loc_data.get("city_or_area") or loc_data.get("location_name") or "",
            country=loc_data.get("country"),
            region=loc_data.get("region"),
            city=loc_data.get("city_or_area") or loc_data.get("city"),
            confidence=loc_data.get("confidence", 0),
        )

    # Slide profile (best/first)
    slide_profile: Optional[SlideProfileDetection] = None
    profiles = data.get("slide_profiles")
    if isinstance(profiles, list) and profiles:
        best = max(profiles, key=lambda p: p.get("confidence", 0))
        slide_profile = SlideProfileDetection(
            profile_name=best.get("profile", "well_preserved"),
            confidence=best.get("confidence", 0),
        )

    return AnalysisResult(
        raw_response=data,
        location=location,
        slide_profile=slide_profile,
        analyzed_at=datetime.now(),
    )
