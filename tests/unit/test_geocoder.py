"""Tests for NominatimGeocoder."""
from unittest.mock import MagicMock, patch

from picture_analyzer.core.interfaces import Geocoder, GeocoderWithCache
from picture_analyzer.core.models import GeoLocation, LocationInfo
from picture_analyzer.geo.nominatim import NominatimGeocoder

# ── Protocol conformance ────────────────────────────────────────────


def test_geocoder_satisfies_protocol():
    """NominatimGeocoder should satisfy the Geocoder protocol."""
    geo = NominatimGeocoder(cache_path="/tmp/test_geo_cache.json")
    assert isinstance(geo, Geocoder)


def test_geocoder_satisfies_cache_protocol():
    """NominatimGeocoder should satisfy the GeocoderWithCache protocol."""
    geo = NominatimGeocoder(cache_path="/tmp/test_geo_cache.json")
    assert isinstance(geo, GeocoderWithCache)


# ── Unit tests ───────────────────────────────────────────────────────


def test_geocode_empty_string():
    """Geocoding an empty string should return None."""
    geo = NominatimGeocoder(cache_path="/tmp/test_geo_cache.json")
    assert geo.geocode("") is None


def test_geocode_returns_geolocation():
    """Successful geocode should return a GeoLocation model."""
    geo = NominatimGeocoder(cache_path="/tmp/test_geo_cache.json")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"lat": "51.5074", "lon": "-0.1278", "display_name": "London, UK"}
    ]

    with patch("requests.get", return_value=mock_response):
        result = geo.geocode("London, UK")

    assert result is not None
    assert isinstance(result, GeoLocation)
    assert abs(result.latitude - 51.5074) < 0.001
    assert abs(result.longitude - (-0.1278)) < 0.001
    assert result.display_name == "London, UK"


def test_geocode_not_found():
    """Geocode should return None when location is not found."""
    geo = NominatimGeocoder(cache_path="/tmp/test_geo_cache.json")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = []

    with patch("requests.get", return_value=mock_response):
        result = geo.geocode("zzz_nonexistent_location_zzz")

    assert result is None


def test_geocode_uses_cache(tmp_path):
    """Second geocode for same location should use cache, not API."""
    cache_file = tmp_path / "cache.json"
    geo = NominatimGeocoder(cache_path=cache_file)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"lat": "52.37", "lon": "4.90", "display_name": "Amsterdam"}
    ]

    with patch("requests.get", return_value=mock_response) as mock_get:
        result1 = geo.geocode("Amsterdam, Netherlands")
        result2 = geo.geocode("Amsterdam, Netherlands")

    # API should only be called once
    assert mock_get.call_count == 1
    assert result1 is not None
    assert result2 is not None
    assert result1.latitude == result2.latitude


def test_cache_operations(tmp_path):
    """Cache clear and size should work correctly."""
    cache_file = tmp_path / "cache.json"
    geo = NominatimGeocoder(cache_path=cache_file)

    assert geo.cache_size() == 0

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"lat": "51.5", "lon": "0.0", "display_name": "London"}
    ]

    with patch("requests.get", return_value=mock_response):
        geo.geocode("London")

    assert geo.cache_size() == 1

    geo.clear_cache()
    assert geo.cache_size() == 0


def test_geocode_from_location_info_below_threshold():
    """Geocoding should skip when confidence is below threshold."""
    geo = NominatimGeocoder(
        cache_path="/tmp/test_geo_cache.json",
        confidence_threshold=80,
    )

    result = geo.geocode_from_location_info(
        {"country": "NL", "confidence": 50}
    )
    assert result is None


def test_geocode_from_location_info_filters_vague():
    """Vague location terms should be filtered out."""
    geo = NominatimGeocoder(cache_path="/tmp/test_geo_cache.json")

    result = geo.geocode_from_location_info(
        {
            "country": "unknown",
            "region": "uncertain",
            "city_or_area": "somewhere",
            "confidence": 90,
        }
    )
    assert result is None


def test_format_gps_string():
    """GPS formatting should produce correct output."""
    geo = GeoLocation(latitude=52.4351, longitude=13.4434)
    result = NominatimGeocoder.format_gps_string(geo)
    assert "52.4351°N" in result
    assert "13.4434°E" in result


def test_format_gps_string_southern_hemisphere():
    """Negative latitude should use S."""
    geo = GeoLocation(latitude=-33.8688, longitude=151.2093)
    result = NominatimGeocoder.format_gps_string(geo)
    assert "S" in result
    assert "E" in result


def test_geocode_location_info_model():
    """geocode_location_info should enrich a LocationInfo with coordinates."""
    geo = NominatimGeocoder(cache_path="/tmp/test_geo_cache.json")

    location = LocationInfo(
        location_name="Berlin, Germany",
        country="Germany",
        city="Berlin",
        confidence=90,
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"lat": "52.52", "lon": "13.405", "display_name": "Berlin"}
    ]

    with patch("requests.get", return_value=mock_response):
        result = geo.geocode_location_info(location)

    assert result.coordinates is not None
    assert abs(result.coordinates.latitude - 52.52) < 0.01
