"""OpenAI Vision API analyzer implementation.

Implements the ``Analyzer`` protocol using OpenAI's Vision models
(gpt-4o-mini, gpt-4o, etc.) to analyze images and return structured
``AnalysisResult`` instances.
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI

from ..config.defaults import (
    DEFAULT_METADATA_LANGUAGE,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_MAX_TOKENS,
    LANGUAGE_NAMES,
    MIME_TYPE_MAP,
)
from ..core.models import (
    AnalysisContext,
    AnalysisResult,
    Enhancement,
    EraInfo,
    GeoLocation,
    ImageData,
    LocationInfo,
    SlideProfileDetection,
)


class OpenAIAnalyzer:
    """Analyzes images using OpenAI Vision API.

    Satisfies the ``Analyzer`` protocol::

        analyzer: Analyzer = OpenAIAnalyzer(api_key="sk-...")
        result = analyzer.analyze(image, context)

    Args:
        api_key: OpenAI API key.  Falls back to ``OPENAI_APIKEY`` env var.
        model: Model name (default ``gpt-4o-mini``).
        max_tokens: Maximum response tokens.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_OPENAI_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        resolved_key = api_key or os.getenv("OPENAI_APIKEY", "")
        self.client = OpenAI(api_key=resolved_key)
        self.model = model
        self.max_tokens = max_tokens

    # ── Analyzer Protocol ────────────────────────────────────────────

    def analyze(self, image: ImageData, context: AnalysisContext) -> AnalysisResult:
        """Analyze an image and return a structured ``AnalysisResult``."""
        # Ensure we have base64 data
        if not image.base64_data:
            image = image.model_copy(update={"base64_data": self._encode(image.path)})

        raw_text = self._call_api(image, context)
        raw_dict = self._parse_json(raw_text)
        return self._to_analysis_result(raw_dict, image, context)

    # ── Internal helpers ─────────────────────────────────────────────

    def _encode(self, path: Path) -> str:
        """Base64-encode an image file."""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _call_api(self, image: ImageData, context: AnalysisContext) -> str:
        """Call OpenAI Vision API and return the raw text response."""
        # Import the analysis prompt from the legacy module (root-level prompts.py)
        import importlib
        import sys

        # Try new location first, fall back to legacy
        try:
            from picture_analyzer.prompts import ANALYSIS_PROMPT  # future location
        except ImportError:
            # Legacy: root-level prompts.py
            _root = str(Path(__file__).resolve().parents[3])
            if _root not in sys.path:
                sys.path.insert(0, _root)
            from prompts import ANALYSIS_PROMPT  # type: ignore[import]

        lang = context.language or DEFAULT_METADATA_LANGUAGE
        prompt = ANALYSIS_PROMPT.format(language=lang)

        # If description.txt is present, clarify its language for the model
        if context.description_text:
            prompt += (
                f"\n\n=== CONTEXT FROM DESCRIPTION.TXT (in {lang_name}) ===\n"
                f"The following description is written in {lang_name} ({lang}):\n"
                f"{context.description_text}\n\n"
                "Please consider this context (in {lang_name}) only for the METADATA section."
            )

        lang_name = LANGUAGE_NAMES.get(lang, lang)

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"You are an image analysis assistant. IMPORTANT: Only the METADATA section and the description context (if present) are in {lang_name} ({lang}). "
                        f"All instructions, technical fields, and ENHANCEMENT RECOMMENDATIONS must remain in English. "
                        f"Every metadata description must be in {lang_name}, while all technical enhancement parameters and instructions must stay in English."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{image.mime_type};base64,{image.base64_data}",
                            },
                        },
                    ],
                },
            ],
        )
        return response.choices[0].message.content

    def _parse_json(self, response: str) -> dict[str, Any]:
        """Extract JSON from the AI response text."""
        json_str = None

        # Try ```json code fence first
        if "```json" in response:
            start = response.find("```json") + 7
            end = response.find("```", start)
            if end > start:
                json_str = response[start:end].strip()
        elif "```" in response:
            start = response.find("```") + 3
            end = response.find("```", start)
            if end > start:
                json_str = response[start:end].strip()

        # Fallback: raw JSON braces
        if not json_str:
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start != -1 and json_end > json_start:
                json_str = response[json_start:json_end]

        if json_str:
            try:
                data = json.loads(json_str)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass

        # If all parsing fails, return a minimal dict with raw text
        return {"raw_response": response}

    def _to_analysis_result(
        self,
        raw: dict[str, Any],
        image: ImageData,
        context: AnalysisContext,
    ) -> AnalysisResult:
        """Convert a raw AI response dict into a typed ``AnalysisResult``.

        This bridges the legacy JSON structure (metadata / enhancement /
        location_detection / slide_profiles) into the Phase 1 Pydantic model.
        """
        metadata = raw.get("metadata", {})
        enhancement = raw.get("enhancement", {})
        location_det = raw.get("location_detection", {})
        slide_profiles = raw.get("slide_profiles", [])

        # ── Location ─────────────────────────────────────────────────
        location: Optional[LocationInfo] = None
        if location_det and isinstance(location_det, dict):
            location = LocationInfo(
                location_name=_join_parts(
                    location_det.get("city_or_area", ""),
                    location_det.get("region", ""),
                    location_det.get("country", ""),
                ),
                country=location_det.get("country"),
                region=location_det.get("region"),
                city=location_det.get("city_or_area"),
                confidence=int(location_det.get("confidence", 0)),
                source="ai",
            )

        # ── Enhancement recommendations ──────────────────────────────
        enhancements: list[Enhancement] = []
        recs = enhancement.get("recommended_enhancements", [])
        if isinstance(recs, list):
            for rec in recs:
                text = rec if isinstance(rec, str) else str(rec)
                enhancements.append(Enhancement(raw_text=text, action=_extract_action(text)))

        # ── Slide profile detection ──────────────────────────────────
        slide_profile: Optional[SlideProfileDetection] = None
        if slide_profiles and isinstance(slide_profiles, list):
            best = slide_profiles[0]
            if isinstance(best, dict):
                slide_profile = SlideProfileDetection(
                    profile_name=best.get("profile", "aged"),
                    confidence=int(best.get("confidence", 0)),
                )

        # ── Era ──────────────────────────────────────────────────────
        era: Optional[EraInfo] = None
        season_date = _str(metadata.get("season_date"))
        time_of_day = _str(metadata.get("time_of_day"))
        if season_date or time_of_day:
            era = EraInfo(
                time_of_day=time_of_day or None,
                season=season_date or None,
            )

        return AnalysisResult(
            # Descriptive
            title=_str(metadata.get("scene_type", "")),
            description=_str(metadata.get("location_setting", "")),
            keywords=_to_list(metadata.get("objects", [])),
            # People
            people=_to_list(metadata.get("persons", [])),
            people_count=None,
            # Location
            location=location,
            # Time
            era=era,
            # Scene
            scene_type=_str(metadata.get("scene_type")),
            mood=_str(metadata.get("mood_atmosphere") or metadata.get("mood")),
            photography_style=_str(metadata.get("photography_style")),
            composition_quality=_str(metadata.get("composition_quality")),
            # Enhancement
            enhancement_recommendations=enhancements,
            slide_profile=slide_profile,
            # Colours
            dominant_colors=_to_list(
                (enhancement.get("color_analysis", {}) or {}).get("dominant_colors", [])
                if isinstance(enhancement.get("color_analysis"), dict)
                else []
            ),
            # Confidence
            confidence_scores={},
            # Raw
            raw_response=raw,
            # Processing metadata
            source_path=image.path,
            analyzed_at=datetime.now(),
            analyzer_model=self.model,
            description_context=context.description_text,
        )


# ── Module-level helpers ─────────────────────────────────────────────


def _str(value: Any) -> str:
    """Safely convert any value to string."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


def _to_list(value: Any) -> list[str]:
    """Normalize value to a list of strings."""
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        if not value or value.lower() in ("not detected", "none", "unknown"):
            return []
        return [s.strip() for s in value.split(",") if s.strip()]
    return []


def _join_parts(*parts: str) -> str:
    """Join non-empty location parts."""
    return ", ".join(p for p in parts if p and p.strip())


def _extract_action(text: str) -> str:
    """Extract the action keyword from a recommendation string."""
    text_lower = text.lower().strip()
    # Check for "ACTION: ..." format
    if ":" in text_lower:
        action = text_lower.split(":")[0].strip()
        # Clean up common prefixes
        for prefix in ("- ", "* ", "• "):
            action = action.removeprefix(prefix)
        return action
    return "unknown"
