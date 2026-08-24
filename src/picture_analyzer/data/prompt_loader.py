"""Prompt template loader for picture_analyzer.

Templates live in ``src/picture_analyzer/data/templates/``:
    metadata.txt        — Sections 1–11 (scene, objects, people, …)  — localized
    location.txt        — Section 12 (geographic reasoning)           — localized
    enhancement.txt     — Sections 13–18 (lighting, color, sharpness) — English only
    slide_profiles.txt  — Section 19 (profile classification)         — English only

Usage::

    loader = PromptLoader()
    # single section
    text = loader.load("metadata", language="Dutch")
    # combined (mirrors the legacy monolithic ANALYSIS_PROMPT)
    full = loader.combined(language="Dutch")
"""
from __future__ import annotations

from pathlib import Path

_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Canonical section order used by combined()
_DEFAULT_SECTIONS = ["metadata", "location", "enhancement", "slide_profiles"]


class PromptLoader:
    """Loads named prompt templates and substitutes placeholder tokens.

    All templates support ``{language}`` substitution.  Templates in
    ``enhancement.txt`` and ``slide_profiles.txt`` intentionally contain no
    ``{language}`` placeholder (they are always delivered in English), but
    passing ``language=`` is still accepted and silently ignored for those.
    """

    def __init__(self, templates_dir: Path | None = None) -> None:
        self._dir = templates_dir or _TEMPLATES_DIR

    # ── Public API ───────────────────────────────────────────────────

    def load(self, name: str, **kwargs: str) -> str:
        """Load a named template and substitute *kwargs*.

        Args:
            name: Template name without extension, e.g. ``"metadata"``.
            **kwargs: Substitution tokens, e.g. ``language="Dutch"``.

        Returns:
            The substituted template text.

        Raises:
            FileNotFoundError: If no ``<name>.txt`` file exists in the
                templates directory.
        """
        path = self._dir / f"{name}.txt"
        if not path.exists():
            raise FileNotFoundError(
                f"Prompt template '{name}' not found at {path}"
            )
        text = path.read_text(encoding="utf-8")
        # Always apply format_map to handle escaped braces {{ }} → { }
        # even if kwargs is empty. This ensures JSON examples are properly
        # unescaped and Python format strings are processed.
        text = _safe_format(text, kwargs)
        return text

    def combined(
        self,
        sections: list[str] | None = None,
        section_overrides: dict[str, str] | None = None,
        **kwargs: str,
    ) -> str:
        """Concatenate multiple section templates into one prompt string.

        This reproduces the legacy monolithic ``ANALYSIS_PROMPT`` when called
        with the default *sections* list.

        Args:
            sections: Section names to include, in order.  Defaults to
                ``["metadata", "location", "enhancement", "slide_profiles"]``.
            section_overrides: Map of section name → suffix.  When a section
                ``"enhancement"`` has override ``"blue"``, the loader looks
                for ``enhancement-blue.txt`` first, falling back to
                ``enhancement.txt`` if the specialised template doesn't exist.
            **kwargs: Substitution tokens passed to each section.

        Returns:
            A single combined prompt string with preamble and footer.
        """
        if sections is None:
            sections = _DEFAULT_SECTIONS
        section_overrides = section_overrides or {}

        # Section name → JSON schema key for the dynamic footer
        _SECTION_KEY_MAP = {
            "metadata": "metadata",
            "location": "location_detection",
            "enhancement": "enhancement",
            "slide_profiles": "slide_profiles",
        }

        parts = [self.load("preamble", **kwargs)]
        for s in sections:
            suffix = section_overrides.get(s)
            if suffix:
                specialised = f"{s}-{suffix}"
                specialised_path = self._dir / f"{specialised}.txt"
                if specialised_path.exists():
                    parts.append(self.load(specialised, **kwargs))
                    continue
            parts.append(self.load(s, **kwargs))

        # Build a focused footer: one schema line per requested section,
        # then the shared structural rules.
        schema_lines = []
        for s in sections:
            footer_section = f"footer_{s}"
            footer_path = self._dir / f"{footer_section}.txt"
            if footer_path.exists():
                schema_lines.append(self.load(footer_section, **kwargs))
        if schema_lines:
            parts.append("".join(schema_lines))

        parts.append(self.load("footer", **kwargs))
        return "\n".join(parts)


# ── helpers ──────────────────────────────────────────────────────────

class _SafeFormatMap(dict):
    """dict subclass that returns the original ``{key}`` for missing keys."""

    def __missing__(self, key: str) -> str:  # type: ignore[override]
        return "{" + key + "}"


def _safe_format(text: str, kwargs: dict) -> str:
    """Like ``str.format_map`` but leaves unknown placeholders intact."""
    return text.format_map(_SafeFormatMap(kwargs))
