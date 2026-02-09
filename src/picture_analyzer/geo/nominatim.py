"""Nominatim (OpenStreetMap) geocoder implementation.

Implements the ``Geocoder`` and ``GeocoderWithCache`` protocols using
the free Nominatim geocoding service.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Set

import requests

from ..config.defaults import (
    DEFAULT_GEO_CACHE_PATH,
    DEFAULT_GEO_CONFIDENCE_THRESHOLD,
    DEFAULT_GEO_MAX_RESULTS,
    DEFAULT_GEO_TIMEOUT,
    DEFAULT_GEO_USER_AGENT,
    DEFAULT_VAGUE_LOCATION_TERMS,
)
from ..core.models import GeoLocation, LocationInfo


class NominatimGeocoder:
    """Geocoder using OpenStreetMap's Nominatim service.

    Satisfies both ``Geocoder`` and ``GeocoderWithCache`` protocols::

        geo: Geocoder = NominatimGeocoder()
        location = geo.geocode("Oostkapelle, Nederland")

    Args:
        cache_path: Path to JSON cache file.
        confidence_threshold: Minimum confidence to attempt geocoding.
        user_agent: HTTP User-Agent for Nominatim API.
        timeout: Request timeout in seconds.
        vague_terms: Set of terms considered too vague for geocoding.
    """

    NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"

    def __init__(
        self,
        cache_path: Path | str = DEFAULT_GEO_CACHE_PATH,
        confidence_threshold: int = DEFAULT_GEO_CONFIDENCE_THRESHOLD,
        user_agent: str = DEFAULT_GEO_USER_AGENT,
        timeout: int = DEFAULT_GEO_TIMEOUT,
        max_results: int = DEFAULT_GEO_MAX_RESULTS,
        vague_terms: frozenset[str] | set[str] | None = None,
    ):
        self._cache_path = Path(cache_path)
        self.confidence_threshold = confidence_threshold
        self.user_agent = user_agent
        self.timeout = timeout
        self.max_results = max_results
        self.vague_terms: set[str] = set(vague_terms or DEFAULT_VAGUE_LOCATION_TERMS)
        self._cache: dict[str, dict[str, Any]] = self._load_cache()

    # ── Geocoder Protocol ────────────────────────────────────────────

    def geocode(self, location: str) -> GeoLocation | None:
        """Convert a location string to GPS coordinates.

        Returns None if the location is too vague or not found.
        """
        location = location.strip()
        if not location:
            return None

        # Check cache
        if location in self._cache:
            cached = self._cache[location]
            coords = cached.get("coordinates", cached)
            if "latitude" in coords and "longitude" in coords:
                return GeoLocation(
                    latitude=float(coords["latitude"]),
                    longitude=float(coords["longitude"]),
                    display_name=coords.get("display_name"),
                )

        # Query API
        result = self._query_nominatim(location)
        if result:
            # Cache the result
            self._cache[location] = {
                "coordinates": {
                    "latitude": result.latitude,
                    "longitude": result.longitude,
                    "display_name": result.display_name,
                },
                "query": location,
            }
            self._save_cache()
        return result

    # ── GeocoderWithCache Protocol ───────────────────────────────────

    def clear_cache(self) -> None:
        """Clear all cached geocoding results."""
        self._cache = {}
        self._save_cache()

    def cache_size(self) -> int:
        """Return number of cached geocoding entries."""
        return len(self._cache)

    # ── High-level helpers ───────────────────────────────────────────

    def geocode_from_location_info(
        self,
        location_data: dict[str, Any],
        confidence_threshold: int | None = None,
    ) -> GeoLocation | None:
        """Geocode from a legacy location_detection dict.

        This provides backward compatibility with the existing dict-based
        ``location_detection`` structure from the AI response.

        Args:
            location_data: Dict with country, region, city_or_area, confidence.
            confidence_threshold: Override instance threshold.

        Returns:
            GeoLocation or None.
        """
        threshold = confidence_threshold or self.confidence_threshold
        confidence = int(location_data.get("confidence", 0))
        if confidence < threshold:
            return None

        query = self._build_query(location_data)
        if not query:
            return None

        return self.geocode(query)

    def geocode_location_info(self, location: LocationInfo) -> LocationInfo:
        """Enrich a ``LocationInfo`` with GPS coordinates from geocoding.

        Returns a new ``LocationInfo`` with the ``coordinates`` field populated
        (or unchanged if geocoding fails).
        """
        if location.confidence < self.confidence_threshold:
            return location

        query = self._build_query_from_info(location)
        if not query:
            return location

        geo = self.geocode(query)
        if geo:
            return location.model_copy(update={"coordinates": geo})
        return location

    # ── Formatting ───────────────────────────────────────────────────

    @staticmethod
    def format_gps_string(geo: GeoLocation) -> str:
        """Format a GeoLocation as a human-readable string."""
        lat = geo.latitude
        lon = geo.longitude
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        return f"{abs(lat):.4f}°{lat_dir}, {abs(lon):.4f}°{lon_dir}"

    @staticmethod
    def format_gps_string_from_dict(coordinates: dict[str, float]) -> str:
        """Format GPS coordinates dict as readable string (legacy compat)."""
        lat = coordinates["latitude"]
        lon = coordinates["longitude"]
        lat_dir = "N" if lat >= 0 else "S"
        lon_dir = "E" if lon >= 0 else "W"
        return f"{abs(lat):.4f}°{lat_dir}, {abs(lon):.4f}°{lon_dir}"

    # ── Internal helpers ─────────────────────────────────────────────

    def _build_query(self, location_data: dict[str, Any]) -> str | None:
        """Build a geocoding query from a location detection dict."""
        country = (location_data.get("country") or "").strip()
        region = (location_data.get("region") or "").strip()
        city = (location_data.get("city_or_area") or "").strip()

        parts = []
        for part in [city, region, country]:
            if part and part.lower() not in self.vague_terms:
                if not any(v in part.lower() for v in self.vague_terms):
                    parts.append(part)

        return ", ".join(parts) if parts else None

    def _build_query_from_info(self, location: LocationInfo) -> str | None:
        """Build a geocoding query from a LocationInfo model."""
        parts = []
        for part in [location.city, location.region, location.country]:
            if part and part.strip().lower() not in self.vague_terms:
                parts.append(part.strip())
        return ", ".join(parts) if parts else None

    def _query_nominatim(self, query: str) -> GeoLocation | None:
        """Query the Nominatim API."""
        try:
            response = requests.get(
                self.NOMINATIM_BASE,
                params={"q": query, "format": "json", "limit": self.max_results},
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )

            if response.status_code == 200:
                results = response.json()
                if results:
                    best = results[0]
                    return GeoLocation(
                        latitude=float(best["lat"]),
                        longitude=float(best["lon"]),
                        display_name=best.get("display_name", query),
                    )
            return None
        except requests.Timeout:
            print(f"Warning: Nominatim API timeout for '{query}'")
            return None
        except Exception as e:
            print(f"Warning: Error querying Nominatim: {e}")
            return None

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        """Load geocoding cache from disk."""
        if self._cache_path.exists():
            try:
                return json.loads(self._cache_path.read_text())
            except Exception as e:
                print(f"Warning: Could not load geocoding cache: {e}")
        return {}

    def _save_cache(self) -> None:
        """Persist geocoding cache to disk."""
        try:
            self._cache_path.write_text(json.dumps(self._cache, indent=2))
        except Exception as e:
            print(f"Warning: Could not save geocoding cache: {e}")
