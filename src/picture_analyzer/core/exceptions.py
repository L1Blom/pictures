"""Custom exception hierarchy for picture_analyzer.

All exceptions raised by this package inherit from :class:`PictureAnalyzerError`
so callers can catch the base class for generic handling, or specific subclasses
for targeted recovery.

Usage::

    from picture_analyzer.core.exceptions import AnalysisError, ValidationError

    try:
        result = pipeline.run(image, context)
    except ValidationError as exc:
        logger.warning("LLM returned malformed output: %s", exc)
    except AnalysisError as exc:
        logger.error("Analysis failed: %s", exc)
    except PictureAnalyzerError as exc:
        logger.error("Unexpected error: %s", exc)
"""
from __future__ import annotations


class PictureAnalyzerError(Exception):
    """Base class for all picture_analyzer exceptions."""


class AnalysisError(PictureAnalyzerError):
    """Raised when an LLM analysis call fails (network, timeout, API error)."""


class ValidationError(PictureAnalyzerError):
    """Raised when an LLM response does not meet the expected schema.

    Attributes:
        raw_response: The raw text or dict that failed validation.
        missing_fields: Fields that were expected but absent.
    """

    def __init__(
        self,
        message: str,
        raw_response: object = None,
        missing_fields: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.raw_response = raw_response
        self.missing_fields = missing_fields or []

    def __str__(self) -> str:
        base = super().__str__()
        if self.missing_fields:
            return f"{base} (missing: {', '.join(self.missing_fields)})"
        return base


class ConfigError(PictureAnalyzerError):
    """Raised when configuration is invalid or missing required values."""


class IOError(PictureAnalyzerError):  # noqa: A001 — intentional shadow of built-in
    """Raised when reading/writing image files or metadata fails."""


class GeocodingError(PictureAnalyzerError):
    """Raised when a geocoding request fails."""
