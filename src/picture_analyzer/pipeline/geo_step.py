"""GeocodingStep — wraps NominatimGeocoder as a pipeline step.

This step reads ``partial.location.location_name``, looks up GPS
coordinates via Nominatim, and writes them back as
``partial.location.coordinates``.

No LLM is called; this step delegates entirely to
``NominatimGeocoder``.  It is skipped when:
- ``context.detect_location`` is ``False``
- ``partial.location`` is ``None`` (no location was detected by a prior step)
- The location name is empty or too vague to geocode
"""
from __future__ import annotations

import logging

from ..config.settings import Settings
from ..core.models import AnalysisContext, AnalysisResult, ImageData
from ..geo.nominatim import NominatimGeocoder

logger = logging.getLogger(__name__)


class GeocodingStep:
    """Resolves a location name from a prior step to GPS coordinates."""

    name = "geocoding"

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def run(
        self,
        image: ImageData,
        context: AnalysisContext,
        partial: AnalysisResult,
    ) -> AnalysisResult:
        if not context.detect_location:
            return partial
        if partial.location is None:
            return partial
        if partial.location.coordinates is not None:
            # Already geocoded (e.g. from EXIF GPS)
            return partial

        location_name = partial.location.location_name
        if not location_name or not location_name.strip():
            return partial

        try:
            geo_cfg = self._settings.geo
            geocoder = NominatimGeocoder(
                cache_path=geo_cfg.cache_path,
                confidence_threshold=geo_cfg.confidence_threshold,
                user_agent=geo_cfg.user_agent,
                timeout=geo_cfg.timeout_seconds,
                max_results=geo_cfg.max_results,
                vague_terms=geo_cfg.vague_terms,
            )
            # Only geocode when AI confidence exceeds the configured threshold
            if partial.location.confidence < geo_cfg.confidence_threshold:
                logger.debug(
                    "GeocodingStep: skipping '%s' — confidence %d < threshold %d",
                    location_name,
                    partial.location.confidence,
                    geo_cfg.confidence_threshold,
                )
                return partial

            coords = geocoder.geocode(location_name)
            if coords is None:
                logger.debug("GeocodingStep: geocoder returned None for '%s'", location_name)
                return partial

            updated_location = partial.location.model_copy(update={"coordinates": coords})
            return partial.model_copy(update={"location": updated_location})

        except Exception:
            logger.exception("GeocodingStep: error geocoding '%s'", location_name)
            return partial
