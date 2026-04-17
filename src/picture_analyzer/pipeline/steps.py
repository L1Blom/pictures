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
        result = self._analyzer.analyze_section(image, context, self._sections)
        return partial.model_copy(
            update={
                "title": result.title or partial.title,
                "description": result.description or partial.description,
                "keywords": result.keywords or partial.keywords,
                "people": result.people or partial.people,
                "people_count": result.people_count or partial.people_count,
                "objects": result.objects or partial.objects,
                "scene_type": result.scene_type or partial.scene_type,
                "mood": result.mood or partial.mood,
                "photography_style": result.photography_style or partial.photography_style,
                "composition_quality": result.composition_quality or partial.composition_quality,
                "era": result.era or partial.era,
                "raw_response": {**partial.raw_response, "metadata": result.raw_response.get("metadata", {})},
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
        return partial.model_copy(
            update={
                "location": result.location or partial.location,
                "raw_response": {**partial.raw_response, "location_detection": result.raw_response.get("location_detection", {})},
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
        result = self._analyzer.analyze_section(image, context, self._sections)
        return partial.model_copy(
            update={
                "enhancement_recommendations": result.enhancement_recommendations or partial.enhancement_recommendations,
                "lighting_quality": result.lighting_quality or partial.lighting_quality,
                "dominant_colors": result.dominant_colors or partial.dominant_colors,
                "raw_response": {**partial.raw_response, "enhancement": result.raw_response.get("enhancement", {})},
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
        return partial.model_copy(
            update={
                "slide_profile": result.slide_profile or partial.slide_profile,
                "raw_response": {**partial.raw_response, "slide_profiles": result.raw_response.get("slide_profiles", [])},
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
        EnhancementStep(
            config=resolve_step_config(pipeline_cfg.enhancement, settings),
            enabled=pipeline_cfg.enhancement.enabled,
        ),
        SlideProfileStep(
            config=resolve_step_config(pipeline_cfg.slide_profiles, settings),
            enabled=pipeline_cfg.slide_profiles.enabled,
        ),
    ]
