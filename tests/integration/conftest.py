"""Shared integration-test fixtures.

Provides a tiny real JPEG and a representative AnalysisResult.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from picture_analyzer.core.models import (
    AnalysisResult,
    Enhancement,
    GeoLocation,
    LocationInfo,
    SlideProfileDetection,
)


@pytest.fixture
def tiny_jpeg(tmp_path: Path) -> Path:
    """Create a 40×40 JPEG with varied colours for realistic filtering."""
    img = Image.new("RGB", (40, 40))
    px = img.load()
    for y in range(40):
        for x in range(40):
            px[x, y] = (
                min(255, x * 6),
                min(255, y * 6),
                min(255, (x + y) * 3),
            )
    p = tmp_path / "tiny.jpg"
    img.save(str(p), "JPEG", quality=85)
    return p


@pytest.fixture
def sample_analysis() -> AnalysisResult:
    """A representative AnalysisResult for end-to-end tests."""
    return AnalysisResult(
        title="Sunset Over the Sea",
        description="A colourful sunset over a calm sea with fishing boats.",
        keywords=["sunset", "sea", "boats", "sky", "water"],
        people=[],
        mood="peaceful",
        scene_type="Nature",
        location=LocationInfo(
            location_name="Scheveningen Beach",
            country="Netherlands",
            region="South Holland",
            city="Scheveningen",
            confidence=85,
            coordinates=GeoLocation(latitude=52.1, longitude=4.28),
        ),
        enhancement_recommendations=[
            Enhancement(action="brightness", raw_text="BRIGHTNESS: increase by 10%"),
            Enhancement(action="contrast", raw_text="CONTRAST: boost by 15%"),
        ],
        slide_profile=SlideProfileDetection(profile_name="faded", confidence=70),
        raw_response={
            "metadata": {
                "scene_type": "Nature",
                "objects": ["sunset", "sea", "boats"],
                "mood_atmosphere": "peaceful",
            },
            "enhancement": {
                "recommended_enhancements": [
                    "BRIGHTNESS: increase by 10%",
                    "CONTRAST: boost by 15%",
                ],
            },
            "location_detection": {
                "country": "Netherlands",
                "region": "South Holland",
                "city_or_area": "Scheveningen",
                "confidence": 85,
            },
            "gps_coordinates": {
                "latitude": 52.1,
                "longitude": 4.28,
            },
        },
    )


@pytest.fixture
def sample_analysis_json(sample_analysis: AnalysisResult, tmp_path: Path) -> Path:
    """Write sample_analysis to a JSON file and return the path."""
    p = tmp_path / "analysis.json"
    p.write_text(sample_analysis.model_dump_json(indent=2))
    return p
