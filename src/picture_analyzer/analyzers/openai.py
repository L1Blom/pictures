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

        if os.environ.get("PA_ANALYZER_DEBUG"):
            import sys
            print("[DEBUG] Parsed dict keys:", list(raw_dict.keys()), file=sys.stderr)

        return self._to_analysis_result(raw_dict, image, context)

    # ── Internal helpers ─────────────────────────────────────────────

    def _encode(self, path: Path) -> str:
        """Base64-encode an image file."""
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def analyze_section(
        self,
        image: ImageData,
        context: AnalysisContext,
        sections: list[str],
    ) -> AnalysisResult:
        """Analyze an image using only the specified prompt sections.

        Used by pipeline steps so each step sends a focused prompt
        instead of the full monolithic one.

        Args:
            image: Image data (base64 will be encoded if missing).
            context: Analysis context.
            sections: Template section names, e.g. ``["metadata"]``.

        Returns:
            ``AnalysisResult`` populated with fields from those sections.
        """
        from ..data.prompt_loader import PromptLoader

        lang = context.language or DEFAULT_METADATA_LANGUAGE
        prompt_override = PromptLoader().combined(sections=sections, language=lang)
        if not image.base64_data:
            image = image.model_copy(update={"base64_data": self._encode(image.path)})
        raw_text = self._call_api(image, context, prompt_override=prompt_override)
        raw_dict = self._parse_json(raw_text)
        return self._to_analysis_result(raw_dict, image, context)

    def _call_api(
        self,
        image: ImageData,
        context: AnalysisContext,
        prompt_override: Optional[str] = None,
    ) -> str:
        """Call OpenAI Vision API and return the raw text response."""
        from ..data.prompt_loader import PromptLoader

        lang = context.language or DEFAULT_METADATA_LANGUAGE
        lang_name = LANGUAGE_NAMES.get(lang, lang)
        prompt = prompt_override or PromptLoader().combined(language=lang)

        # If description.txt is present, clarify its language for the model
        if context.description_text:
            prompt += (
                f"\n\n=== CONTEXT FROM DESCRIPTION.TXT (location/context hint only) ===\n"
                f"WARNING: This text is a LOCATION and CONTEXT HINT — it is NOT a visual description of the image.\n"
                f"** DO NOT use this text as a substitute for visual analysis. **\n"
                f"** You MUST base your analysis on what you ACTUALLY SEE in the image. **\n"
                f"** Only use this text to improve location detection (country/region/city) and date context. **\n"
                f"The hint is written in {lang_name} ({lang}):\n"
                f"{context.description_text}\n"
            )

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
        text = response.choices[0].message.content
        if os.environ.get("PA_ANALYZER_DEBUG"):
            import sys
            print("\n[DEBUG] Raw OpenAI response:\n", text, "\n", file=sys.stderr)
        return text

    def _parse_json(self, response: str) -> dict[str, Any]:
        """Extract JSON from the AI response text."""
        # Strip DeepSeek-R1 style <think>...</think> reasoning blocks before parsing
        import re as _re
        response = _re.sub(r"<think>.*?</think>", "", response, flags=_re.DOTALL).strip()

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
            # Some models (e.g. llava) escape underscores in JSON keys: \_ → _
            cleaned = json_str.replace("\\_", "_")
            try:
                data = json.loads(cleaned)
                if isinstance(data, dict):
                    return self._normalise_response(data)
            except json.JSONDecodeError:
                pass
            # Try original (unmodified) string as fallback
            try:
                data = json.loads(json_str)
                if isinstance(data, dict):
                    return self._normalise_response(data)
            except json.JSONDecodeError:
                pass

        # If all parsing fails, return a minimal dict with raw text
        return {"raw_response": response}

    @staticmethod
    def _normalise_response(data: dict[str, Any]) -> dict[str, Any]:
        """Normalise provider-specific response quirks into a canonical shape.

        Handles differences across models:
        - llava: ``slide_profiles`` inside ``metadata``; ``objects``/``persons`` as count strings
        - gpt-oss: ``enhancement`` as a list; ``location_detection`` uses ``city`` not
          ``city_or_area``; ``confidence`` as 0-1 float instead of 0-100 int
        """
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            metadata = {}

        # ── Normalise uppercase top-level keys (e.g. SLIDE_PROFILES) ────
        for bad_key in list(data.keys()):
            lower = bad_key.lower()
            if bad_key != lower and lower not in data:
                data = {**{lower if k == bad_key else k: v for k, v in data.items()}}

        # ── Hoist slide_profiles out of metadata (llava) ─────────────
        if "slide_profiles" not in data and "slide_profiles" in metadata:
            data = {**data, "slide_profiles": metadata["slide_profiles"]}
            metadata = {k: v for k, v in metadata.items() if k != "slide_profiles"}
            data["metadata"] = metadata

        # ── objects / persons: pure numeric count strings → [] ────────
        for field in ("objects", "persons"):
            val = metadata.get(field)
            if val is None or isinstance(val, list):
                continue
            if isinstance(val, str) and val.strip().isdigit():
                metadata = {**metadata, field: []}
        data = {**data, "metadata": metadata}

        # ── enhancement: various shapes → canonical dict ─────────────
        enhancement = data.get("enhancement", {})
        if isinstance(enhancement, list):
            # gpt-oss: enhancement is a list of named filter objects
            recs = []
            for item in enhancement:
                if isinstance(item, dict):
                    name = item.get("name", "")
                    desc = item.get("description", "")
                    recs.append(f"{name.upper()}: {desc}" if desc else name.upper())
                elif isinstance(item, str):
                    recs.append(item)
            data = {**data, "enhancement": {"recommended_enhancements": recs}}
        else:
            # Some models return enhancement_recommendations at top level
            top_recs = data.get("enhancement_recommendations")
            if top_recs and isinstance(top_recs, list):
                enh = dict(enhancement) if isinstance(enhancement, dict) else {}
                if not enh.get("recommended_enhancements"):
                    enh["recommended_enhancements"] = top_recs
                data = {**data, "enhancement": enh}
            # Some models use image_analysis instead of enhancement fields
            if isinstance(enhancement, dict) and not enhancement.get("recommended_enhancements"):
                image_analysis = data.get("image_analysis", {})
                if isinstance(image_analysis, dict):
                    merged = {**image_analysis, **enhancement}
                    data = {**data, "enhancement": merged}

        # ── location_detection field name variants ────────────────────
        loc = data.get("location_detection")
        if isinstance(loc, dict):
            # "city" → "city_or_area"
            if "city_or_area" not in loc and "city" in loc:
                loc = {**loc, "city_or_area": loc["city"]}
            loc = {**loc, "confidence": _parse_confidence(loc.get("confidence"))}
            data = {**data, "location_detection": loc}

        # ── slide_profiles: normalise field names and confidence ─────
        # Canonical profile names — map translated/variant names back to these
        _PROFILE_ALIASES: dict[str, str] = {
            # Dutch
            "goed bewaard": "well_preserved",
            "goed_bewaard": "well_preserved",
            "vervaagd": "faded",
            "verouderd": "aged",
            "geel verval": "yellow_cast",
            "geel_verval": "yellow_cast",
            "rood verval": "red_cast",
            "rood_verval": "red_cast",
            "kleurverval": "color_cast",
            "kleur_verval": "color_cast",
            # French
            "bien conservé": "well_preserved",
            "bien_conserve": "well_preserved",
            "vieilli": "aged",
            "décoloré": "faded",
            # German
            "gut erhalten": "well_preserved",
            "gut_erhalten": "well_preserved",
            "verblasst": "faded",
            "gealtert": "aged",
            # Other common variants
            "well preserved": "well_preserved",
            "yellow cast": "yellow_cast",
            "red cast": "red_cast",
            "color cast": "color_cast",
        }
        profiles = data.get("slide_profiles")
        if isinstance(profiles, list):
            normalised = []
            for p in profiles:
                if isinstance(p, dict):
                    # Rename profile_name → profile, confidence_score → confidence
                    if "profile" not in p and "profile_name" in p:
                        p = {**p, "profile": p["profile_name"]}
                    if "confidence" not in p and "confidence_score" in p:
                        p = {**p, "confidence": p["confidence_score"]}
                    # Normalise translated/variant profile names to canonical English
                    raw_profile = str(p.get("profile", "")).strip().lower()
                    canonical = _PROFILE_ALIASES.get(raw_profile)
                    if canonical:
                        p = {**p, "profile": canonical}
                    p = {**p, "confidence": _parse_confidence(p.get("confidence"))}
                normalised.append(p)
            data = {**data, "slide_profiles": normalised}

        return data

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
                confidence=_parse_confidence(location_det.get("confidence")),
                source="ai",
            )

        # ── Enhancement recommendations ──────────────────────────────
        enhancements: list[Enhancement] = []
        recs = enhancement.get("recommended_enhancements", [])
        if isinstance(recs, list):
            for rec in recs:
                if isinstance(rec, str):
                    text = rec
                elif isinstance(rec, dict):
                    # llava returns {"action": "CONTRAST", "value": "Boost by 20%"}
                    action = rec.get("action", "")
                    value = rec.get("value", "")
                    text = f"{action}: {value}" if value else action
                else:
                    text = str(rec)
                enhancements.append(Enhancement(raw_text=text, action=_extract_action(text)))

        # ── Slide profile detection ──────────────────────────────────
        slide_profile: Optional[SlideProfileDetection] = None
        if slide_profiles and isinstance(slide_profiles, list):
            best = slide_profiles[0]
            if isinstance(best, dict):
                slide_profile = SlideProfileDetection(
                    profile_name=best.get("profile", "aged"),
                    confidence=_parse_confidence(best.get("confidence")),
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

_CONFIDENCE_WORDS: dict[str, int] = {
    "very high": 90, "high": 80, "medium high": 70, "medium": 60,
    "moderate": 55, "low medium": 45, "low": 30, "very low": 15,
    "none": 0, "unknown": 0,
}


def _parse_confidence(value: Any) -> int:
    """Convert any confidence representation to a 0-100 int.

    Handles:
    - int / float in 0-1 range  → multiply by 100
    - int / float in 0-100 range → pass through
    - word strings ("high", "medium") → map via lookup table
    - None / unparseable          → 0
    """
    if value is None:
        return 0
    if isinstance(value, (int, float)):
        if value <= 1.0:
            return int(value * 100)
        return int(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in _CONFIDENCE_WORDS:
            return _CONFIDENCE_WORDS[lower]
        try:
            f = float(lower.rstrip("%"))
            return int(f) if f > 1.0 else int(f * 100)
        except ValueError:
            pass
    return 0


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
        if not value:
            return []
        lower = value.lower()
        # Return empty list for "none"-type phrases in any language
        none_phrases = (
            "not detected", "none", "unknown", "geen", "no ", "niet ", "keine",
        )
        if lower in ("not detected", "none", "unknown", "geen") or any(
            lower.startswith(p) for p in ("no ", "niet ", "keine ", "geen ")
        ):
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
