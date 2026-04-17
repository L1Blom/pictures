"""Ollama Vision analyzer implementation.

Implements the ``Analyzer`` protocol using locally hosted Ollama models
(for example ``llava``) to analyze images and return structured
``AnalysisResult`` instances.
"""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import ollama

from ..config.defaults import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_METADATA_LANGUAGE,
    DEFAULT_OLLAMA_MODEL,
    LANGUAGE_NAMES,
)
from ..core.models import AnalysisContext, AnalysisResult, ImageData
from .openai import OpenAIAnalyzer


class OllamaAnalyzer(OpenAIAnalyzer):
    """Analyzes images using a local Ollama vision model.

    Reuses parsing and model-conversion helpers from ``OpenAIAnalyzer``
    so both providers yield the same internal ``AnalysisResult`` shape.
    """

    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        host: str | None = None,
        timeout: int = 300,
        num_ctx: int | None = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.num_ctx = num_ctx
        self.client = ollama.Client(host=host, timeout=timeout) if host else ollama.Client(timeout=timeout)

    def _encode(self, path: Path) -> str:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _call_api(
        self,
        image: ImageData,
        context: AnalysisContext,
        prompt_override: str | None = None,
    ) -> str:
        from ..data.prompt_loader import PromptLoader

        lang = context.language or DEFAULT_METADATA_LANGUAGE
        lang_name = LANGUAGE_NAMES.get(lang, lang)
        prompt = prompt_override or PromptLoader().combined(language=lang)

        if context.description_text:
            import re as _re_ctx
            # Strip person/activity/notes lines — these cause the model to copy them verbatim
            # into scene_type/activity_action instead of deriving from visual evidence.
            # Covers both English and Dutch field names.
            desc_for_prompt = _re_ctx.sub(
                r"(?im)^(people|personen|notes|opmerkingen|activiteit|activity)\s*:.*\n?",
                "",
                context.description_text,
            ).strip()
            prompt += (
                f"\n\n=== CONTEXT FROM DESCRIPTION.TXT ===\n"
                f"Use this context as follows:\n"
                f"- GROUND TRUTH (use exactly as given, do not override with visual inference):\n"
                f"  Location (city, region, country) and Date.\n"
                f"- VISUAL CONFIRMATION REQUIRED (only use if you can confirm it in the image):\n"
                f"  Activity, Weather, Mood. Describe ONLY what you can SEE in the image for these fields.\n"
                f"  If the image contradicts the description, trust the image.\n"
                f"- PERSONS: describe ONLY people physically visible in the image. If no person is visible, write 'geen personen zichtbaar'. Do NOT infer persons from context text or names.\n"
                f"- SCENE TYPE: determine scene type from visual evidence only. A cage containing animals is NOT a prison. Do not derive scene type from context text.\n"
                f"This text is written in {lang_name} ({lang}):\n"
                f"{desc_for_prompt}\n"
            )

        system_prompt = (
            f"You are an image analysis assistant. "
            f"All user-facing metadata fields (objects, persons, weather, mood, scene type, location setting, "
            f"activity, photography style, composition quality) MUST be written in {lang_name} ({lang}). "
            "Technical enhancement fields (lighting_quality, color_analysis, sharpness_clarity, contrast_level, "
            "composition_issues, recommended_enhancements, overall_priority) MUST remain in English. "
            "Location field values (country, region, city_or_area) should use the local language name as given "
            "in the description context when provided. "
            "ALWAYS write every string value in full. NEVER abbreviate, truncate, or end any value with '...', "
            "'\u2026', or '-'."
        )

        options: dict = {"num_predict": self.max_tokens, "repeat_penalty": 1.3}
        if self.num_ctx is not None:
            options["num_ctx"] = self.num_ctx

        response = self.client.chat(
            model=self.model,
            format="json",  # Force the model to emit valid JSON directly
            options=options,
            keep_alive="2h",  # Keep model loaded; prevents costly reload mid-batch on CPU
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image.base64_data or self._encode(image.path)],
                },
            ],
        )

        # ollama >= 0.4 returns a typed ChatResponse object
        if hasattr(response, "message") and hasattr(response.message, "content"):
            text = response.message.content or ""
        elif isinstance(response, dict):
            msg = response.get("message", {})
            text = msg.get("content", "") if isinstance(msg, dict) else ""
        else:
            text = ""

        # Store token/timing stats for pipeline display
        self._last_call_stats = {
            "prompt_tokens": getattr(response, "prompt_eval_count", None),
            "output_tokens": getattr(response, "eval_count", None),
            "eval_duration_ns": getattr(response, "eval_duration", None),
        }

        import os
        if os.getenv("PA_ANALYZER_DEBUG"):
            import sys
            print("\n[DEBUG] Raw Ollama response:\n" + text + "\n", file=sys.stderr)

        return text

    @staticmethod
    def _enforce_location_from_description(raw_dict: dict, description_text: str) -> dict:
        """Override location fields with ground truth from description.txt.

        If the description has an explicit ``Location:`` line, parse
        city/region/country from it and write them directly into
        ``location_detection``, ignoring whatever the model produced.
        This handles truncation, misspelling, and empty responses alike.
        """
        import re

        # Look for an explicit "Location:" / "Locatie:" line (English and Dutch)
        match = re.search(r"(?im)^(?:location|locatie)\s*:\s*(.+)$", description_text)
        if not match:
            return raw_dict

        raw_location = match.group(1).strip()

        # Slash-separated value means multiple countries at the same level
        # (e.g. "Duitsland / Oostenrijk / Frankrijk").  Store the whole
        # string as the country field and leave region/city empty.
        if "/" in raw_location:
            field_map: dict[str, str] = {
                "country": " / ".join(p.strip() for p in raw_location.split("/") if p.strip()),
                "region": "",
                "city_or_area": "",
            }
            loc = dict(raw_dict.get("location_detection") or {})
            loc.update(field_map)
            loc.setdefault("location_type", "country")
            loc["confidence"] = 100
            loc["reasoning"] = "Explicitly named in the description"
            raw_dict = {**raw_dict, "location_detection": loc}
            return raw_dict

        parts = [p.strip() for p in raw_location.split(",") if p.strip()]
        if not parts:
            return raw_dict

        # Map positional tokens to location fields (city, region, country)
        # Convention: most specific first → city, region, country
        field_map = {}
        if len(parts) >= 1:
            field_map["city_or_area"] = parts[0]
        if len(parts) >= 2:
            field_map["region"] = parts[1]
        if len(parts) >= 3:
            field_map["country"] = parts[2]

        loc = dict(raw_dict.get("location_detection") or {})
        for field, value in field_map.items():
            loc[field] = value

        # Ensure confidence and reasoning reflect ground truth
        loc.setdefault("location_type", "city")
        loc["confidence"] = 100
        loc["reasoning"] = "Explicitly named in the description"

        raw_dict = {**raw_dict, "location_detection": loc}
        return raw_dict

    def analyze_section(
        self,
        image: "ImageData",
        context: "AnalysisContext",
        sections: list[str],
    ) -> "AnalysisResult":
        """Override to apply post-processing normalisations after JSON parse."""
        from ..data.prompt_loader import PromptLoader
        from ..config.defaults import DEFAULT_METADATA_LANGUAGE

        lang = context.language or DEFAULT_METADATA_LANGUAGE
        prompt_override = PromptLoader().combined(sections=sections, language=lang)
        if not image.base64_data:
            image = image.model_copy(update={"base64_data": self._encode(image.path)})
        raw_text = self._call_api(image, context, prompt_override=prompt_override)
        raw_dict = self._parse_json(raw_text)

        if context.description_text and "location" in sections:
            raw_dict = self._enforce_location_from_description(raw_dict, context.description_text)

        return self._to_analysis_result(raw_dict, image, context)