"""Layered configuration using Pydantic Settings.

Configuration priority (highest wins):
    1. CLI arguments (applied by the CLI layer on top of settings)
    2. Environment variables  (PA_OPENAI__MODEL=gpt-4o)
    3. .env file              (OPENAI_APIKEY=sk-...)
    4. config.yaml            (optional, loaded if present)
    5. Defaults               (from defaults.py)

Environment variable naming:
    - Top-level:  PA_BATCH_SIZE=10
    - Nested:     PA_OPENAI__MODEL=gpt-4o  (double underscore = nesting)
    - Legacy:     OPENAI_APIKEY is also accepted (backward compat)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, FrozenSet, Optional, Tuple

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from . import defaults as d


# ── Nested Config Models ────────────────────────────────────────────


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""

    api_key: SecretStr = Field(default=SecretStr(""), description="OpenAI API key")
    model: str = Field(default=d.DEFAULT_OPENAI_MODEL, description="Vision model name")
    max_tokens: int = Field(default=d.DEFAULT_MAX_TOKENS, ge=1, le=16384)
    detail: str = Field(default=d.DEFAULT_DETAIL_LEVEL, pattern="^(auto|low|high)$")


class GeoConfig(BaseModel):
    """Geocoding configuration."""

    provider: str = Field(default=d.DEFAULT_GEO_PROVIDER, description="Geocoding provider")
    cache_path: Path = Field(default=Path(d.DEFAULT_GEO_CACHE_PATH))
    cache_enabled: bool = True
    confidence_threshold: int = Field(default=d.DEFAULT_GEO_CONFIDENCE_THRESHOLD, ge=0, le=100)
    user_agent: str = Field(default=d.DEFAULT_GEO_USER_AGENT)
    timeout_seconds: int = Field(default=d.DEFAULT_GEO_TIMEOUT, ge=1, le=60)
    max_results: int = Field(default=d.DEFAULT_GEO_MAX_RESULTS, ge=1)
    vague_terms: FrozenSet[str] = Field(default=d.DEFAULT_VAGUE_LOCATION_TERMS)
    # Future: Google Maps
    google_api_key: Optional[SecretStr] = None


class MetadataConfig(BaseModel):
    """Metadata writing configuration."""

    language: str = Field(default=d.DEFAULT_METADATA_LANGUAGE, min_length=2, max_length=5)
    write_exif: bool = d.DEFAULT_WRITE_EXIF
    write_xmp: bool = d.DEFAULT_WRITE_XMP
    write_gps: bool = d.DEFAULT_WRITE_GPS
    jpeg_quality: int = Field(default=d.DEFAULT_JPEG_QUALITY, ge=1, le=100)
    description_max_length: int = Field(default=d.DEFAULT_DESCRIPTION_MAX_LENGTH, ge=100)


class EnhancementConfig(BaseModel):
    """AI-guided image enhancement configuration."""

    enabled: bool = True
    jpeg_quality: int = Field(default=d.DEFAULT_JPEG_QUALITY, ge=1, le=100)
    color_temperature_baseline: int = Field(
        default=d.DEFAULT_COLOR_TEMP_BASELINE,
        ge=d.DEFAULT_KELVIN_RANGE[0],
        le=d.DEFAULT_KELVIN_RANGE[1],
    )
    kelvin_range: Tuple[int, int] = Field(default=d.DEFAULT_KELVIN_RANGE)
    channel_factor_range: Tuple[float, float] = Field(default=d.DEFAULT_CHANNEL_FACTOR_RANGE)
    unsharp_mask_defaults: dict[str, int] = Field(default_factory=lambda: dict(d.DEFAULT_UNSHARP_MASK))


class SlideRestorationConfig(BaseModel):
    """Slide/dia restoration configuration."""

    enabled: bool = True
    profiles_dir: Optional[Path] = Field(default=None, description="Dir for custom YAML profiles")
    auto_detect: bool = True
    confidence_threshold: int = Field(default=d.DEFAULT_PROFILE_CONFIDENCE_THRESHOLD, ge=0, le=100)
    jpeg_quality: int = Field(default=d.DEFAULT_JPEG_QUALITY, ge=1, le=100)
    denoise_radius: float = Field(default=d.DEFAULT_DENOISE_RADIUS, ge=0.0, le=5.0)


class OutputConfig(BaseModel):
    """Output file and directory configuration."""

    directory: Path = Field(default=Path(d.DEFAULT_OUTPUT_DIR))
    temp_directory: Path = Field(default=Path(d.DEFAULT_TEMP_DIR))
    naming_pattern: str = Field(default=d.DEFAULT_NAMING_PATTERN)
    enhanced_pattern: str = Field(default=d.DEFAULT_ENHANCED_PATTERN)
    restored_pattern: str = Field(default=d.DEFAULT_RESTORED_PATTERN)
    thumbnails_dir: str = Field(default=d.DEFAULT_THUMBNAILS_DIR)
    thumbnail_size: int = Field(default=d.DEFAULT_THUMBNAIL_SIZE, ge=16, le=1024)
    thumbnail_quality: int = Field(default=d.DEFAULT_THUMBNAIL_QUALITY, ge=1, le=100)
    cleanup_temp: bool = d.DEFAULT_CLEANUP_TEMP


class WebConfig(BaseModel):
    """Description editor web UI configuration."""

    host: str = Field(default=d.DEFAULT_WEB_HOST)
    port: int = Field(default=d.DEFAULT_WEB_PORT, ge=1, le=65535)
    debug: bool = d.DEFAULT_WEB_DEBUG
    thumbnail_size: int = Field(default=d.DEFAULT_WEB_THUMBNAIL_SIZE, ge=16, le=2048)
    thumbnail_format: str = Field(default=d.DEFAULT_WEB_THUMBNAIL_FORMAT, pattern="^(PNG|JPEG|WEBP)$")
    photos_dir: Path = Field(default=Path(d.DEFAULT_WEB_PHOTOS_DIR))
    description_template: str = Field(default=d.DEFAULT_DESCRIPTION_TEMPLATE)


class ReportConfig(BaseModel):
    """Report generation configuration."""

    format: str = Field(default=d.DEFAULT_REPORT_FORMAT, pattern="^(markdown|html)$")
    template: str = Field(default=d.DEFAULT_REPORT_TEMPLATE)
    include_thumbnails: bool = d.DEFAULT_REPORT_INCLUDE_THUMBNAILS
    thumbnail_max_size: int = Field(default=d.DEFAULT_REPORT_THUMBNAIL_MAX_SIZE, ge=16, le=2048)
    base64_thumbnails: bool = d.DEFAULT_REPORT_BASE64_THUMBNAILS
    report_filename: str = Field(default=d.DEFAULT_REPORT_FILENAME)
    gallery_filename: str = Field(default=d.DEFAULT_GALLERY_FILENAME)


class PromptConfig(BaseModel):
    """Controls which sections the AI analysis prompt includes."""

    detect_slide_profiles: bool = d.DEFAULT_DETECT_SLIDE_PROFILES
    recommend_enhancements: bool = d.DEFAULT_RECOMMEND_ENHANCEMENTS
    detect_location: bool = d.DEFAULT_DETECT_LOCATION
    detect_people: bool = d.DEFAULT_DETECT_PEOPLE
    detect_era: bool = d.DEFAULT_DETECT_ERA
    custom_instructions: Optional[str] = Field(
        default=None,
        description="Extra instructions appended to the analysis prompt",
    )


# ── Root Settings ────────────────────────────────────────────────────


class Settings(BaseSettings):
    """Root configuration — aggregates all sub-configs.

    Load priority: defaults → config.yaml → .env → environment variables.
    Environment variables use PA_ prefix and __ for nesting:
        PA_OPENAI__MODEL=gpt-4o
        PA_METADATA__LANGUAGE=nl
        PA_GEO__CONFIDENCE_THRESHOLD=70
    """

    model_config = SettingsConfigDict(
        env_prefix="PA_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-configurations
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    geo: GeoConfig = Field(default_factory=GeoConfig)
    metadata: MetadataConfig = Field(default_factory=MetadataConfig)
    enhancement: EnhancementConfig = Field(default_factory=EnhancementConfig)
    slide_restoration: SlideRestorationConfig = Field(default_factory=SlideRestorationConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)
    prompt: PromptConfig = Field(default_factory=PromptConfig)

    # Top-level settings
    supported_formats: FrozenSet[str] = Field(default=d.DEFAULT_SUPPORTED_FORMATS)
    batch_size: int = Field(default=d.DEFAULT_BATCH_SIZE, ge=1, le=100)
    log_level: str = Field(default=d.DEFAULT_LOG_LEVEL, pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")

    @model_validator(mode="before")
    @classmethod
    def _handle_legacy_env_vars(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Accept legacy env var names for backward compatibility.

        The old .env used OPENAI_APIKEY; the new system expects
        PA_OPENAI__API_KEY.  This validator bridges the gap.
        """
        import os
        from dotenv import load_dotenv

        # Ensure .env is loaded before checking legacy vars
        load_dotenv()

        # Legacy: OPENAI_APIKEY → openai.api_key
        legacy_key = os.getenv("OPENAI_APIKEY")
        if legacy_key:
            openai_cfg = data.get("openai", {})
            if isinstance(openai_cfg, dict) and not openai_cfg.get("api_key"):
                openai_cfg["api_key"] = legacy_key
                data["openai"] = openai_cfg

        # Legacy: METADATA_LANGUAGE → metadata.language
        legacy_lang = os.getenv("METADATA_LANGUAGE")
        if legacy_lang:
            meta_cfg = data.get("metadata", {})
            if isinstance(meta_cfg, dict) and not meta_cfg.get("language"):
                meta_cfg["language"] = legacy_lang
                data["metadata"] = meta_cfg

        # Legacy: GPS_CONFIDENCE_THRESHOLD → geo.confidence_threshold
        legacy_gps = os.getenv("GPS_CONFIDENCE_THRESHOLD")
        if legacy_gps:
            geo_cfg = data.get("geo", {})
            if isinstance(geo_cfg, dict) and not geo_cfg.get("confidence_threshold"):
                geo_cfg["confidence_threshold"] = int(legacy_gps)
                data["geo"] = geo_cfg

        # Legacy: OUTPUT_DIR → output.directory
        legacy_out = os.getenv("OUTPUT_DIR")
        if legacy_out:
            out_cfg = data.get("output", {})
            if isinstance(out_cfg, dict) and not out_cfg.get("directory"):
                out_cfg["directory"] = legacy_out
                data["output"] = out_cfg

        return data


# ── Singleton / lazy loader ──────────────────────────────────────────

_settings: Settings | None = None


def get_settings(**overrides: Any) -> Settings:
    """Get the global Settings instance (created on first call).

    Args:
        **overrides: Values to override (useful for CLI args or tests).
                     Nested keys use dict: ``openai={"model": "gpt-4o"}``.

    Returns:
        Configured Settings instance.
    """
    global _settings
    if _settings is None or overrides:
        _settings = Settings(**overrides)
    return _settings


def reset_settings() -> None:
    """Reset the cached settings (for testing)."""
    global _settings
    _settings = None
