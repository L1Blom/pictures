"""Configuration system for picture_analyzer.

Submodules:
    defaults  — Hardcoded default values (single source of truth).
    settings  — Pydantic Settings model with layered loading.
    loader    — YAML / Jinja2 / text file loaders for externalized data.
"""
from .settings import (  # noqa: F401
    PipelineConfig,
    StepConfig,
    resolve_step_config,
)
