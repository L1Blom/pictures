"""Tests for config/loader.py — YAML, Jinja2, and text file loaders."""
from __future__ import annotations

import pytest
from pathlib import Path

from picture_analyzer.config.loader import (
    load_translations,
    load_slide_profiles,
    load_report_template,
    load_description_template,
    clear_translation_cache,
    clear_profile_cache,
    _english_fallback,
    _data_dir,
    _parse_simple_yaml,
)
from picture_analyzer.core.models import SlideProfile, ColorBalance


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_caches():
    """Each test gets fresh caches."""
    clear_translation_cache()
    clear_profile_cache()
    yield
    clear_translation_cache()
    clear_profile_cache()


# ── _data_dir ────────────────────────────────────────────────────────


def test_data_dir_exists():
    """The bundled data directory should exist."""
    d = _data_dir()
    assert d.is_dir(), f"Expected {d} to be a directory"


def test_data_dir_contains_translations():
    """data/translations/ should exist with at least en.yaml."""
    d = _data_dir() / "translations"
    assert d.is_dir()
    assert (d / "en.yaml").exists()


def test_data_dir_contains_profiles():
    """data/profiles/ should exist with at least one .yaml file."""
    d = _data_dir() / "profiles"
    assert d.is_dir()
    assert list(d.glob("*.yaml"))


# ── Translations ─────────────────────────────────────────────────────


def test_load_english_translations():
    """Loading English translations should return a dict with expected keys."""
    t = load_translations("en")
    assert isinstance(t, dict)
    assert t["LOCATION"] == "LOCATION"
    assert t["Confidence"] == "Confidence"
    assert t["Objects"] == "Objects"


def test_load_dutch_translations():
    """Loading Dutch translations should return localized labels."""
    t = load_translations("nl")
    assert isinstance(t, dict)
    assert t["LOCATION"] == "LOCATIE"
    assert t["Confidence"] == "Betrouwbaarheid"
    assert t["Objects"] == "Objecten"


def test_load_missing_language_falls_back_to_english():
    """A missing language should fall back to English."""
    t = load_translations("xx")
    assert t["LOCATION"] == "LOCATION"


def test_translations_cache():
    """Calling load_translations twice should return the same object."""
    t1 = load_translations("en")
    t2 = load_translations("en")
    assert t1 is t2  # cached — same dict instance


def test_english_fallback_has_all_keys():
    """The hardcoded fallback should have all expected keys."""
    fb = _english_fallback()
    for key in [
        "LOCATION", "Confidence", "Location uncertain",
        "Objects", "Persons", "Weather", "Mood/Atmosphere",
        "Time of Day", "Season/Date", "Scene Type", "Setting",
        "Activity", "Photography Style", "Composition Quality",
    ]:
        assert key in fb, f"Missing key: {key}"


# ── Slide Profiles ──────────────────────────────────────────────────


def test_load_builtin_profiles():
    """Should load all 6 built-in profiles as typed SlideProfile models."""
    profiles = load_slide_profiles()
    assert isinstance(profiles, dict)
    assert len(profiles) >= 6
    for name in ["faded", "color_cast", "red_cast", "yellow_cast", "aged", "well_preserved"]:
        assert name in profiles, f"Missing profile: {name}"
        p = profiles[name]
        assert isinstance(p, SlideProfile)
        assert isinstance(p.color_balance, ColorBalance)


def test_profile_values_match_defaults():
    """YAML profile values should match the original defaults."""
    profiles = load_slide_profiles()

    faded = profiles["faded"]
    assert faded.saturation == 1.5
    assert faded.contrast == 1.6
    assert faded.brightness == 1.15
    assert faded.denoise is True
    assert faded.color_balance.blue == 1.15

    well = profiles["well_preserved"]
    assert well.saturation == 1.1
    assert well.denoise is False
    assert well.color_balance.red == 1.0
    assert well.color_balance.green == 1.0
    assert well.color_balance.blue == 1.0


def test_load_custom_profiles(tmp_path):
    """Loading from a custom directory should work."""
    # Create a custom profile
    custom_yaml = tmp_path / "custom.yaml"
    custom_yaml.write_text(
        "name: Custom Profile\n"
        "description: A test profile\n"
        "saturation: 2.0\n"
        "contrast: 1.8\n"
        "brightness: 1.2\n"
        "sharpness: 1.3\n"
        "color_balance:\n"
        "  red: 0.9\n"
        "  green: 1.1\n"
        "  blue: 1.2\n"
        "denoise: true\n"
        "denoise_radius: 0.7\n"
    )
    profiles = load_slide_profiles(custom_dir=tmp_path)
    assert "custom" in profiles
    p = profiles["custom"]
    assert p.saturation == 2.0
    assert p.color_balance.red == 0.9
    assert p.denoise is True


def test_load_custom_empty_dir_falls_back(tmp_path):
    """An empty custom dir should fall back to bundled profiles."""
    empty_dir = tmp_path / "empty_profiles"
    empty_dir.mkdir()
    profiles = load_slide_profiles(custom_dir=empty_dir)
    assert len(profiles) >= 6  # Should have loaded bundled profiles


def test_profile_cache():
    """Calling load_slide_profiles twice should return the same dict."""
    p1 = load_slide_profiles()
    p2 = load_slide_profiles()
    assert p1 is p2  # cached


# ── Report Templates ────────────────────────────────────────────────


def test_load_report_template():
    """Should load the report.md.j2 template."""
    tmpl = load_report_template("report")
    assert tmpl is not None
    # It should be a Jinja2 Template object with a render method
    assert hasattr(tmpl, "render")


def test_load_gallery_template():
    """Should load the gallery.md.j2 template."""
    tmpl = load_report_template("gallery")
    assert tmpl is not None
    assert hasattr(tmpl, "render")


def test_load_missing_template():
    """A nonexistent template should return None."""
    tmpl = load_report_template("does_not_exist_xyz")
    assert tmpl is None


def test_report_template_renders():
    """The report template should render with minimal data."""
    tmpl = load_report_template("report")
    assert tmpl is not None
    result = tmpl.render(
        analyses=[
            {
                "name": "test_photo",
                "analysis": {"metadata": {"objects": "tree, sky"}},
                "description": None,
                "analyzed_img": None,
                "enhanced_img": None,
                "restored_imgs": [],
            }
        ],
        total=1,
    )
    assert "Picture Analysis Report" in result
    assert "test_photo" in result


# ── Description Templates ────────────────────────────────────────────


def test_load_dutch_description_template():
    """Should load the Dutch description template."""
    desc = load_description_template("nl")
    assert "Albumnaam:" in desc
    assert "Locatie:" in desc


def test_load_english_description_template():
    """Should load the English description template."""
    desc = load_description_template("en")
    assert "Album name:" in desc
    assert "Location:" in desc


def test_load_missing_language_description_falls_back():
    """Missing language should fall back to Dutch template."""
    desc = load_description_template("xx")
    assert "Albumnaam:" in desc  # Falls back to nl


# ── Simple YAML parser ──────────────────────────────────────────────


def test_parse_simple_yaml(tmp_path):
    """Fallback YAML parser should handle simple key: value files."""
    f = tmp_path / "test.yaml"
    f.write_text('key1: value1\nkey2: "value2"\n# comment\nkey3: value3\n')
    result = _parse_simple_yaml(f)
    assert result == {"key1": "value1", "key2": "value2", "key3": "value3"}


def test_parse_simple_yaml_empty(tmp_path):
    """Empty file should return None."""
    f = tmp_path / "empty.yaml"
    f.write_text("# only comments\n")
    result = _parse_simple_yaml(f)
    assert result is None
