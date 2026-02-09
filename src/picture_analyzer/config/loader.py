"""Data loading utilities for externalized YAML / Jinja2 / text files.

This module provides functions to load translations, slide profiles,
report templates, and description templates from the ``data/`` directory
bundled inside the package.  Each loader has a built-in fallback so
that the application never crashes if a file is missing — it simply
uses the hardcoded defaults from ``defaults.py``.

Users can override bundled data by pointing to a custom directory via
``Settings`` (e.g. ``slide_restoration.profiles_dir``).

Typical usage::

    from picture_analyzer.config.loader import (
        load_translations,
        load_slide_profiles,
        load_report_template,
        load_description_template,
    )

    labels = load_translations("nl")       # dict[str, str]
    profiles = load_slide_profiles()        # dict[str, SlideProfile]
    tmpl = load_report_template("report")   # jinja2.Template | None
    desc = load_description_template("nl")  # str
"""
from __future__ import annotations

import importlib.resources
from pathlib import Path
from typing import Any

from ..core.models import ColorBalance, SlideProfile

# ── Package data root ────────────────────────────────────────────────

_DATA_PACKAGE = "picture_analyzer.data"


def _data_dir() -> Path:
    """Return path to the bundled ``data/`` directory.

    Uses ``importlib.resources`` for correct resolution even when the
    package is installed as a wheel / zip.
    """
    try:
        # Python 3.9+
        ref = importlib.resources.files(_DATA_PACKAGE)
        return Path(str(ref))
    except (TypeError, AttributeError):
        # Fallback for older Python
        return Path(__file__).resolve().parent.parent / "data"


# ── Translations ─────────────────────────────────────────────────────

# Module-level cache: lang → dict[str, str]
_translations_cache: dict[str, dict[str, str]] = {}


def load_translations(language: str = "en") -> dict[str, str]:
    """Load translation labels for *language* from YAML.

    Returns English labels as fallback if the requested language file
    does not exist.

    Args:
        language: ISO 639-1 code (``"en"``, ``"nl"``, …).

    Returns:
        Flat ``{key: translated_label}`` mapping.
    """
    if language in _translations_cache:
        return _translations_cache[language]

    data = _load_yaml(f"translations/{language}.yaml")
    if data is None and language != "en":
        data = _load_yaml("translations/en.yaml")
    if data is None:
        # Ultimate fallback — use the hardcoded English dict
        data = _english_fallback()

    _translations_cache[language] = data
    return data


def clear_translation_cache() -> None:
    """Clear the translations cache (useful for testing)."""
    _translations_cache.clear()


def _english_fallback() -> dict[str, str]:
    """Hardcoded English labels — last-resort fallback."""
    return {
        "LOCATION": "LOCATION",
        "SOURCE_DESCRIPTION_HEADER": "SOURCE DESCRIPTION (from description.txt)",
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
    }


# ── Slide Profiles ──────────────────────────────────────────────────

_profiles_cache: dict[str, SlideProfile] | None = None


def load_slide_profiles(
    custom_dir: Path | str | None = None,
) -> dict[str, SlideProfile]:
    """Load all slide restoration profiles.

    Resolution order:
        1. *custom_dir* (if provided and exists)
        2. Bundled ``data/profiles/*.yaml``
        3. ``defaults.DEFAULT_SLIDE_PROFILES`` (hardcoded fallback)

    Args:
        custom_dir: Optional directory containing custom YAML profiles.

    Returns:
        ``{profile_key: SlideProfile}`` mapping.
    """
    global _profiles_cache
    if _profiles_cache is not None and custom_dir is None:
        return _profiles_cache

    profiles: dict[str, SlideProfile] = {}

    # Try custom dir first
    if custom_dir:
        custom_path = Path(custom_dir)
        if custom_path.is_dir():
            profiles = _load_profiles_from_dir(custom_path)

    # Merge with bundled profiles (custom takes precedence)
    if not profiles:
        bundled_dir = _data_dir() / "profiles"
        if bundled_dir.is_dir():
            profiles = _load_profiles_from_dir(bundled_dir)

    # Fallback to hardcoded defaults
    if not profiles:
        profiles = _profiles_from_defaults()

    if custom_dir is None:
        _profiles_cache = profiles

    return profiles


def clear_profile_cache() -> None:
    """Clear the profile cache (useful for testing)."""
    global _profiles_cache
    _profiles_cache = None


def _load_profiles_from_dir(directory: Path) -> dict[str, SlideProfile]:
    """Load all ``*.yaml`` profiles from a directory."""
    profiles: dict[str, SlideProfile] = {}
    for yaml_file in sorted(directory.glob("*.yaml")):
        try:
            data = _load_yaml_from_path(yaml_file)
            if data:
                key = yaml_file.stem  # e.g. "faded" from "faded.yaml"
                cb = data.get("color_balance", {})
                profiles[key] = SlideProfile(
                    name=data.get("name", key.replace("_", " ").title()),
                    description=data.get("description", ""),
                    saturation=float(data.get("saturation", 1.0)),
                    contrast=float(data.get("contrast", 1.0)),
                    brightness=float(data.get("brightness", 1.0)),
                    sharpness=float(data.get("sharpness", 1.0)),
                    color_balance=ColorBalance(
                        red=float(cb.get("red", 1.0)),
                        green=float(cb.get("green", 1.0)),
                        blue=float(cb.get("blue", 1.0)),
                    ),
                    denoise=bool(data.get("denoise", False)),
                    denoise_radius=float(data.get("denoise_radius", 0.5)),
                )
        except Exception as e:
            print(f"Warning: Could not load profile {yaml_file}: {e}")
    return profiles


def _profiles_from_defaults() -> dict[str, SlideProfile]:
    """Build profiles from the hardcoded DEFAULT_SLIDE_PROFILES."""
    from .defaults import DEFAULT_SLIDE_PROFILES

    profiles: dict[str, SlideProfile] = {}
    for key, data in DEFAULT_SLIDE_PROFILES.items():
        cb = data.get("color_balance", {})
        profiles[key] = SlideProfile(
            name=data.get("name", key),
            description=data.get("description", ""),
            saturation=data.get("saturation", 1.0),
            contrast=data.get("contrast", 1.0),
            brightness=data.get("brightness", 1.0),
            sharpness=data.get("sharpness", 1.0),
            color_balance=ColorBalance(
                red=cb.get("red", 1.0),
                green=cb.get("green", 1.0),
                blue=cb.get("blue", 1.0),
            ),
            denoise=data.get("denoise", False),
            denoise_radius=data.get("denoise_radius", 0.5),
        )
    return profiles


# ── Report Templates ─────────────────────────────────────────────────


def load_report_template(name: str = "report") -> "Any | None":
    """Load a Jinja2 report template by name.

    Looks for ``data/templates/{name}.md.j2``.

    Args:
        name: Template name without extension (``"report"`` or ``"gallery"``).

    Returns:
        ``jinja2.Template`` instance, or ``None`` if Jinja2 is not installed
        or the template file is missing.
    """
    try:
        import jinja2
    except ImportError:
        return None

    template_path = _data_dir() / "templates" / f"{name}.md.j2"
    if not template_path.exists():
        return None

    try:
        env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(template_path.parent)),
            extensions=["jinja2.ext.loopcontrols"],
            autoescape=False,  # Markdown, not HTML
            keep_trailing_newline=True,
        )
        return env.get_template(template_path.name)
    except Exception as e:
        print(f"Warning: Could not load template {template_path}: {e}")
        return None


# ── Description Templates ────────────────────────────────────────────


def load_description_template(language: str = "nl") -> str:
    """Load the description.txt template for the given language.

    Falls back to the Dutch template (the original hardcoded default).

    Args:
        language: ISO 639-1 code.

    Returns:
        Template string.
    """
    # Try language-specific file
    template_path = _data_dir() / "templates" / f"description_{language}.txt"
    if template_path.exists():
        try:
            return template_path.read_text(encoding="utf-8")
        except Exception:
            pass

    # Fallback to Dutch
    if language != "nl":
        nl_path = _data_dir() / "templates" / "description_nl.txt"
        if nl_path.exists():
            try:
                return nl_path.read_text(encoding="utf-8")
            except Exception:
                pass

    # Ultimate fallback — hardcoded from defaults.py
    from .defaults import DEFAULT_DESCRIPTION_TEMPLATE

    return DEFAULT_DESCRIPTION_TEMPLATE


# ── YAML helpers ─────────────────────────────────────────────────────


def _load_yaml(relative_path: str) -> dict[str, Any] | None:
    """Load a YAML file relative to the data directory.

    Returns None if the file doesn't exist or can't be parsed.
    """
    path = _data_dir() / relative_path
    return _load_yaml_from_path(path)


def _load_yaml_from_path(path: Path) -> dict[str, Any] | None:
    """Load a YAML file from an absolute path.

    Returns None if the file doesn't exist or can't be parsed.
    """
    if not path.exists():
        return None
    try:
        import yaml

        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except ImportError:
        # PyYAML not installed — try to read as simple key: value pairs
        return _parse_simple_yaml(path)
    except Exception as e:
        print(f"Warning: Could not parse YAML file {path}: {e}")
        return None


def _parse_simple_yaml(path: Path) -> dict[str, str] | None:
    """Fallback parser for simple ``key: value`` YAML files.

    Only works for flat files (no nesting).  Used when PyYAML is not
    installed.
    """
    try:
        result: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key:
                    result[key] = value
        return result if result else None
    except Exception:
        return None
