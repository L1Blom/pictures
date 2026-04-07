"""Tests for PromptLoader."""
from __future__ import annotations

import pytest

from picture_analyzer.data.prompt_loader import PromptLoader


class TestPromptLoaderLoad:
    """Test the load() method in isolation."""

    def test_load_metadata_template(self):
        text = PromptLoader().load("metadata", language="Dutch")
        assert "METADATA SECTION" in text
        assert "Dutch" in text

    def test_load_location_template(self):
        text = PromptLoader().load("location", language="English")
        assert "LOCATION DETECTION" in text
        assert "HIGHEST PRIORITY" in text  # location now uses description as ground truth

    def test_load_enhancement_template(self):
        text = PromptLoader().load("enhancement", language="ignored")
        assert "ENHANCEMENT RECOMMENDATIONS" in text

    def test_load_slide_profiles_template(self):
        text = PromptLoader().load("slide_profiles")
        assert "SLIDE RESTORATION PROFILES" in text

    def test_load_preamble(self):
        text = PromptLoader().load("preamble", language="Dutch")
        assert "You are analyzing an image" in text

    def test_load_footer(self):
        text = PromptLoader().load("footer", language="Dutch")
        assert "JSON" in text

    def test_missing_template_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="nonexistent"):
            PromptLoader().load("nonexistent")

    def test_language_substitution(self):
        text = PromptLoader().load("metadata", language="Spanish")
        assert "Spanish" in text
        assert "{language}" not in text

    def test_unknown_placeholder_left_intact(self):
        # enhancement.txt has no {language} placeholder — should not raise
        text = PromptLoader().load("enhancement", language="Dutch")
        assert "{language}" not in text  # was substituted (no-op) or not present


class TestPromptLoaderCombined:
    """Test the combined() method."""

    def test_combined_contains_all_sections(self):
        text = PromptLoader().combined(language="English")
        assert "METADATA SECTION" in text
        assert "LOCATION DETECTION" in text
        assert "ENHANCEMENT RECOMMENDATIONS" in text
        assert "SLIDE RESTORATION PROFILES" in text

    def test_combined_contains_preamble_and_footer(self):
        text = PromptLoader().combined(language="English")
        assert "You are analyzing an image" in text
        assert "CRITICAL JSON STRUCTURE RULES" in text

    def test_combined_no_unresolved_language_placeholders(self):
        text = PromptLoader().combined(language="Dutch")
        # The only {language} occurrences remaining should be zero
        # (preamble, metadata, location templates substitute it)
        assert text.count("{language}") == 0

    def test_combined_subset_of_sections(self):
        text = PromptLoader().combined(
            sections=["metadata"], language="English"
        )
        assert "METADATA SECTION" in text
        assert "LOCATION DETECTION" not in text
        assert "ENHANCEMENT RECOMMENDATIONS" not in text

    def test_combined_is_string(self):
        result = PromptLoader().combined(language="English")
        assert isinstance(result, str)
        assert len(result) > 100


class TestPromptLoaderShim:
    """Verify the root-level prompts.py shim still exposes ANALYSIS_PROMPT."""

    def test_shim_exports_analysis_prompt(self):
        import importlib, sys
        # Ensure re-import in case already cached
        if "prompts" in sys.modules:
            del sys.modules["prompts"]
        import prompts
        assert hasattr(prompts, "ANALYSIS_PROMPT")
        assert isinstance(prompts.ANALYSIS_PROMPT, str)
        assert "METADATA SECTION" in prompts.ANALYSIS_PROMPT

    def test_shim_prompt_contains_language_placeholder(self):
        import prompts
        # The shim uses language="{language}" so the placeholder stays
        assert "{language}" in prompts.ANALYSIS_PROMPT
