"""Tests for the configuration system."""
from __future__ import annotations

from picture_analyzer.config.defaults import (
    DEFAULT_GEO_CONFIDENCE_THRESHOLD,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_METADATA_LANGUAGE,
    DEFAULT_OPENAI_MODEL,
    DEFAULT_PIPELINE_MODE,
    DEFAULT_WEB_PORT,
)
from picture_analyzer.config.settings import (
    PipelineConfig,
    Settings,
    StepConfig,
    resolve_step_config,
)


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

    def test_default_values(self, monkeypatch, tmp_path):
        # Prevent .env from being loaded and clear legacy env vars
        monkeypatch.chdir(tmp_path)  # no config.yaml in tmp_path
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


class TestPipelineConfig:
    """Verify PipelineConfig and StepConfig defaults and validation."""

    def test_default_mode_is_single(self):
        assert DEFAULT_PIPELINE_MODE == "single"
        cfg = PipelineConfig()
        assert cfg.mode == "single"

    def test_all_steps_enabled_by_default(self):
        cfg = PipelineConfig()
        assert cfg.metadata.enabled is True
        assert cfg.location.enabled is True
        assert cfg.enhancement.enabled is True
        assert cfg.slide_profiles.enabled is True

    def test_step_defaults_are_none(self):
        step = StepConfig()
        assert step.provider is None
        assert step.model is None
        assert step.max_tokens is None
        assert step.prompt_template is None

    def test_stepped_mode_accepted(self):
        cfg = PipelineConfig(mode="stepped")
        assert cfg.mode == "stepped"

    def test_invalid_mode_rejected(self):
        import pytest
        with pytest.raises(Exception):
            PipelineConfig(mode="invalid")

    def test_settings_has_pipeline_field(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)  # no config.yaml in tmp_path
        s = Settings(openai={"api_key": "sk-test"})
        assert hasattr(s, "pipeline")
        assert isinstance(s.pipeline, PipelineConfig)
        assert s.pipeline.mode == "single"

    def test_env_var_overrides_pipeline_mode(self, monkeypatch):
        monkeypatch.setenv("PA_PIPELINE__MODE", "stepped")
        s = Settings(openai={"api_key": "sk-test"})
        assert s.pipeline.mode == "stepped"

    def test_env_var_overrides_location_model(self, monkeypatch):
        monkeypatch.setenv("PA_PIPELINE__LOCATION__MODEL", "gpt-4o")
        s = Settings(openai={"api_key": "sk-test"})
        assert s.pipeline.location.model == "gpt-4o"

    def test_env_var_disables_slide_profiles_step(self, monkeypatch):
        monkeypatch.setenv("PA_PIPELINE__SLIDE_PROFILES__ENABLED", "false")
        s = Settings(openai={"api_key": "sk-test"})
        assert s.pipeline.slide_profiles.enabled is False

    def test_pipeline_config_in_override_dict(self):
        s = Settings(
            openai={"api_key": "sk-test"},
            pipeline={"mode": "stepped", "location": {"model": "gpt-4o"}},
        )
        assert s.pipeline.mode == "stepped"
        assert s.pipeline.location.model == "gpt-4o"


class TestResolveStepConfig:
    """Verify resolve_step_config merges step overrides with global defaults."""

    def _settings(self, **kwargs) -> Settings:
        kwargs.setdefault("analyzer_provider", "openai")
        return Settings(openai={"api_key": "sk-test"}, **kwargs)

    def test_falls_back_to_global_openai_model(self):
        s = self._settings()
        result = resolve_step_config(StepConfig(), s)
        assert result["provider"] == "openai"
        assert result["model"] == s.openai.model

    def test_step_model_overrides_global(self):
        s = self._settings()
        result = resolve_step_config(StepConfig(model="gpt-4o"), s)
        assert result["model"] == "gpt-4o"

    def test_step_provider_openai_uses_openai_model(self):
        s = self._settings(analyzer_provider="ollama")
        result = resolve_step_config(StepConfig(provider="openai"), s)
        assert result["provider"] == "openai"
        assert result["model"] == s.openai.model

    def test_step_provider_ollama_uses_ollama_model(self):
        s = self._settings(analyzer_provider="openai")
        result = resolve_step_config(StepConfig(provider="ollama"), s)
        assert result["provider"] == "ollama"
        assert result["model"] == s.ollama.model

    def test_step_max_tokens_overrides_global(self):
        s = self._settings()
        result = resolve_step_config(StepConfig(max_tokens=512), s)
        assert result["max_tokens"] == 512

    def test_max_tokens_falls_back_to_global_for_openai(self):
        s = self._settings()
        result = resolve_step_config(StepConfig(), s)
        assert result["max_tokens"] == s.openai.max_tokens

    def test_max_tokens_is_none_for_ollama(self):
        s = self._settings(analyzer_provider="ollama")
        result = resolve_step_config(StepConfig(), s)
        assert result["max_tokens"] is None  # OllamaConfig has no max_tokens

    def test_prompt_template_none_by_default(self):
        s = self._settings()
        result = resolve_step_config(StepConfig(), s)
        assert result["prompt_template"] is None

    def test_prompt_template_passed_through(self):
        s = self._settings()
        result = resolve_step_config(StepConfig(prompt_template="custom.txt"), s)
        assert result["prompt_template"] == "custom.txt"

