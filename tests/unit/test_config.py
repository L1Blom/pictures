"""Tests for the configuration system."""
from __future__ import annotations

from picture_analyzer.config.defaults import (
    DEFAULT_JPEG_QUALITY,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_GEO_CONFIDENCE_THRESHOLD,
    DEFAULT_METADATA_LANGUAGE,
    DEFAULT_WEB_PORT,
)
from picture_analyzer.config.settings import Settings


class TestDefaults:
    """Verify all defaults are accessible and have expected types."""

    def test_jpeg_quality_is_int(self):
        assert isinstance(DEFAULT_JPEG_QUALITY, int)
        assert 1 <= DEFAULT_JPEG_QUALITY <= 100

    def test_openai_model_is_string(self):
        assert isinstance(DEFAULT_OPENAI_MODEL, str)
        assert len(DEFAULT_OPENAI_MODEL) > 0


class TestSettings:
    """Verify Settings model loads and validates correctly."""

    def test_settings_with_api_key(self):
        s = Settings(openai={"api_key": "sk-test"})
        assert s.openai.api_key.get_secret_value() == "sk-test"
        assert s.openai.model == DEFAULT_OPENAI_MODEL

    def test_default_values(self, monkeypatch):
        # Prevent .env from being loaded and clear legacy env vars
        monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **kw: None)
        monkeypatch.delenv("METADATA_LANGUAGE", raising=False)
        monkeypatch.delenv("GPS_CONFIDENCE_THRESHOLD", raising=False)
        monkeypatch.delenv("OUTPUT_DIR", raising=False)
        monkeypatch.delenv("OPENAI_APIKEY", raising=False)
        s = Settings(openai={"api_key": "sk-test"}, _env_file=None)
        assert s.metadata.language == DEFAULT_METADATA_LANGUAGE
        assert s.geo.confidence_threshold == DEFAULT_GEO_CONFIDENCE_THRESHOLD
        assert s.web.port == DEFAULT_WEB_PORT
        assert s.metadata.jpeg_quality == DEFAULT_JPEG_QUALITY

    def test_override_nested(self):
        s = Settings(
            openai={"api_key": "sk-test", "model": "gpt-4o"},
            metadata={"language": "nl", "jpeg_quality": 90},
        )
        assert s.openai.model == "gpt-4o"
        assert s.metadata.language == "nl"
        assert s.metadata.jpeg_quality == 90

    def test_supported_formats_is_frozenset(self):
        s = Settings(openai={"api_key": "sk-test"})
        assert ".jpg" in s.supported_formats
        assert ".heic" in s.supported_formats

    def test_invalid_jpeg_quality_rejected(self):
        import pytest
        with pytest.raises(Exception):
            Settings(
                openai={"api_key": "sk-test"},
                metadata={"jpeg_quality": 200},
            )

    def test_invalid_log_level_rejected(self):
        import pytest
        with pytest.raises(Exception):
            Settings(
                openai={"api_key": "sk-test"},
                log_level="INVALID",
            )
