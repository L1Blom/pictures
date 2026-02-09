"""Shared pytest fixtures for picture_analyzer tests."""
from __future__ import annotations

import pytest

from picture_analyzer.config.settings import Settings, reset_settings


@pytest.fixture(autouse=True)
def _reset_settings():
    """Ensure each test gets a fresh Settings instance."""
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def settings() -> Settings:
    """Provide a Settings instance with test-safe defaults."""
    return Settings(
        openai={"api_key": "sk-test-key-not-real"},
    )
