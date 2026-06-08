"""Concrete AnalysisStep implementations for the stepped pipeline.

Each step is responsible for exactly one section of the analysis:

    MetadataStep      — sections 1–11  (scene, objects, people, …)
    LocationStep      — section 12     (geographic reasoning)
    EnhancementStep   — sections 13–18 (lighting, color, sharpness)
    SlideProfileStep  — section 19     (profile classification)

Steps receive the accumulated ``AnalysisResult`` so far and return an
updated copy via ``model_copy(update=...)``.  A step that is disabled or
whose matching ``AnalysisContext`` flag is off returns *partial* unchanged.
"""
from __future__ import annotations

import logging
from typing import Any

from ..analyzers.openai import OpenAIAnalyzer
from ..analyzers.ollama import OllamaAnalyzer
from ..config.settings import Settings, StepConfig, resolve_step_config
from ..core.models import AnalysisContext, AnalysisResult, ImageData

logger = logging.getLogger(__name__)


def _build_analyzer(resolved: dict[str, Any]):
    """Instantiate the right analyzer from a resolved step config dict."""
    provider = resolved["provider"]
    model = resolved["model"]
    max_tokens = resolved["max_tokens"]

    if provider == "openai":
        kwargs: dict[str, Any] = {"model": model}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        return OpenAIAnalyzer(**kwargs)
    else:
        kwargs = {"model": model}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if resolved.get("timeout") is not None:
            kwargs["timeout"] = resolved["timeout"]
        if resolved.get("num_ctx") is not None:
            kwargs["num_ctx"] = resolved["num_ctx"]
        if resolved.get("host") is not None:
            kwargs["host"] = resolved["host"]
        if resolved.get("keep_alive") is not None:
            kwargs["keep_alive"] = resolved["keep_alive"]
        return OllamaAnalyzer(**kwargs)


class MetadataStep:
    """Runs sections 1–11: scene description, objects, people, mood, era, …"""

    name = "metadata"
    _sections = ["metadata"]

    def __init__(self, config: dict[str, Any], enabled: bool = True) -> None:
        self._config = config
        self._enabled = enabled
        self._analyzer = _build_analyzer(config)

    def run(
        self,
        image: ImageData,
        context: AnalysisContext,
        partial: AnalysisResult,
    ) -> AnalysisResult:
        if not self._enabled:
            return partial
        # Two-pass: part1 = fields 1-6 (objects/persons/weather/mood/time/season)
        #           part2 = fields 7-11 (scene_type/location/activity/style/composition)
        # Each pass has fewer fields so the LLM can provide rich detail without truncation.
        r1 = self._analyzer.analyze_section(image, context, ["metadata_part1"])
        r2 = self._analyzer.analyze_section(image, context, ["metadata_part2"])
        raw1 = r1.raw_response if isinstance(r1.raw_response, dict) else {}
        raw2 = r2.raw_response if isinstance(r2.raw_response, dict) else {}
        merged_meta = {**raw1.get("metadata", {}), **raw2.get("metadata", {})}
        merged_raw = {**raw1, **raw2, "metadata": merged_meta}
        return partial.model_copy(
            update={
                "title": r2.title or r1.title or partial.title,
                "description": r2.description or r1.description or partial.description,
                "keywords": r1.keywords or r2.keywords or partial.keywords,
                "people": r1.people or r2.people or partial.people,
                "people_count": r1.people_count or r2.people_count or partial.people_count,
                "objects": r1.objects or r2.objects or partial.objects,
                "scene_type": r2.scene_type or r1.scene_type or partial.scene_type,
                "mood": r1.mood or r2.mood or partial.mood,
                "photography_style": r2.photography_style or r1.photography_style or partial.photography_style,
                "composition_quality": r2.composition_quality or r1.composition_quality or partial.composition_quality,
                "era": r1.era or r2.era or partial.era,
                "raw_response": {**partial.raw_response, **merged_raw},
            }
        )


class LocationStep:
    """Runs section 12: geographic location detection."""

    name = "location"
    _sections = ["location"]

    def __init__(self, config: dict[str, Any], enabled: bool = True) -> None:
        self._config = config
        self._enabled = enabled
        self._analyzer = _build_analyzer(config)

    def run(
        self,
        image: ImageData,
        context: AnalysisContext,
        partial: AnalysisResult,
    ) -> AnalysisResult:
        if not self._enabled or not context.detect_location:
            return partial
        result = self._analyzer.analyze_section(image, context, self._sections)
        # Only merge non-empty sections (avoid overwriting metadata with empty dict)
        # IMPORTANT: Never merge metadata from location step (only metadata step should set it)
        merged = {**partial.raw_response}
        for key, val in result.raw_response.items():
            if key == "metadata":
                # Skip metadata — it comes only from MetadataStep
                continue
            if val or key not in merged:  # Update if non-empty OR if it's a new key
                merged[key] = val
        return partial.model_copy(
            update={
                "location": result.location or partial.location,
                "raw_response": merged,
            }
        )


class EnhancementStep:
    """Runs sections 13–18: lighting, color, sharpness, contrast recommendations."""

    name = "enhancement"
    _sections = ["enhancement"]

    def __init__(self, config: dict[str, Any], enabled: bool = True) -> None:
        self._config = config
        self._enabled = enabled
        self._analyzer = _build_analyzer(config)

    def run(
        self,
        image: ImageData,
        context: AnalysisContext,
        partial: AnalysisResult,
    ) -> AnalysisResult:
        if not self._enabled or not context.recommend_enhancements:
            return partial

        # If a slide profile was already detected (SlideProfileStep runs first),
        # inject that knowledge into the context so the enhancement prompt can
        # recommend restoration-oriented adjustments instead of treating the
        # faded/aged scan as a normal photo.
        active_context = context
        if partial.slide_profile and partial.slide_profile.confidence >= 60:
            profile_hint = (
                f"[SLIDE SCAN DETECTED: profile={partial.slide_profile.profile_name}, "
                f"confidence={partial.slide_profile.confidence}%] "
                "This is a scanned photographic slide with aging/fading. "
                "Recommend enhancements appropriate for slide restoration: "
                "contrast recovery, color cast correction, grain/noise reduction, "
                "and sharpness improvements."
            )
            existing = context.description_text or ""
            augmented = f"{profile_hint}\n{existing}".strip()
            active_context = context.model_copy(update={"description_text": augmented})

        result = self._analyzer.analyze_section(image, active_context, self._sections)
        # Only merge non-empty sections (avoid overwriting metadata with empty dict)
        # IMPORTANT: Never merge metadata from enhancement step (only metadata step should set it)
        merged = {**partial.raw_response}
        for key, val in result.raw_response.items():
            if key == "metadata":
                # Skip metadata — it comes only from MetadataStep, not enhancement
                continue
            if val or key not in merged:  # Update if non-empty OR if it's a new key
                merged[key] = val
        return partial.model_copy(
            update={
                "enhancement_recommendations": result.enhancement_recommendations or partial.enhancement_recommendations,
                "lighting_quality": result.lighting_quality or partial.lighting_quality,
                "dominant_colors": result.dominant_colors or partial.dominant_colors,
                "raw_response": merged,
            }
        )


class SlideProfileStep:
    """Runs section 19: slide/dia restoration profile detection."""

    name = "slide_profiles"
    _sections = ["slide_profiles"]

    def __init__(self, config: dict[str, Any], enabled: bool = True) -> None:
        self._config = config
        self._enabled = enabled
        self._analyzer = _build_analyzer(config)

    def run(
        self,
        image: ImageData,
        context: AnalysisContext,
        partial: AnalysisResult,
    ) -> AnalysisResult:
        if not self._enabled or not context.detect_slide_profiles:
            return partial
        result = self._analyzer.analyze_section(image, context, self._sections)
        # Only merge non-empty sections (avoid overwriting metadata with empty dict)
        # IMPORTANT: Never merge metadata from slide_profiles step (only metadata step should set it)
        merged = {**partial.raw_response}
        for key, val in result.raw_response.items():
            if key == "metadata":
                # Skip metadata — it comes only from MetadataStep
                continue
            if val or key not in merged:  # Update if non-empty OR if it's a new key
                merged[key] = val

        # Ensure well_preserved is always present as a baseline option
        profiles = merged.get("slide_profiles", [])
        if isinstance(profiles, list) and profiles:
            if not any(p.get("profile") == "well_preserved" for p in profiles):
                profiles.append({"profile": "well_preserved", "confidence": 20})
                merged["slide_profiles"] = profiles

        return partial.model_copy(
            update={
                "slide_profile": result.slide_profile or partial.slide_profile,
                "raw_response": merged,
            }
        )


def build_steps(settings: Settings) -> list:
    """Build the canonical list of LLM steps from *settings*.

    Returns instances of MetadataStep, LocationStep, EnhancementStep,
    SlideProfileStep — each configured from ``settings.pipeline``.
    """
    pipeline_cfg = settings.pipeline
    return [
        MetadataStep(
            config=resolve_step_config(pipeline_cfg.metadata, settings),
            enabled=pipeline_cfg.metadata.enabled,
        ),
        LocationStep(
            config=resolve_step_config(pipeline_cfg.location, settings),
            enabled=pipeline_cfg.location.enabled,
        ),
        SlideProfileStep(
            config=resolve_step_config(pipeline_cfg.slide_profiles, settings),
            enabled=pipeline_cfg.slide_profiles.enabled,
        ),
        EnhancementStep(
            config=resolve_step_config(pipeline_cfg.enhancement, settings),
            enabled=pipeline_cfg.enhancement.enabled,
        ),
    ]
