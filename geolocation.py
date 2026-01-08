"""
Geolocation utilities for converting location text to GPS coordinates
"""
import requests
import json
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import os

# Geocoding cache file
GEOCODING_CACHE_FILE = Path(__file__).parent / ".geocoding_cache.json"


class GeoLocator:
    """Convert location text to GPS coordinates using Nominatim (OpenStreetMap)"""
    
    # Nominatim API endpoint
    NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"
    
    # User agent for Nominatim (required by their API)
    USER_AGENT = "picture-analyzer/1.0"
    
    @staticmethod
    def _load_cache() -> Dict[str, Dict[str, Any]]:
        """Load geocoding cache from disk"""
        if GEOCODING_CACHE_FILE.exists():
            try:
                with open(GEOCODING_CACHE_FILE, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Warning: Could not load geocoding cache: {e}")
        return {}
    
    @staticmethod
    def _save_cache(cache: Dict[str, Dict[str, Any]]) -> None:
        """Save geocoding cache to disk"""
        try:
            with open(GEOCODING_CACHE_FILE, 'w') as f:
                json.dump(cache, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save geocoding cache: {e}")
    
    @staticmethod
    def geocode_location(
        location_detection: Dict[str, Any],
        confidence_threshold: int = 80
    ) -> Optional[Dict[str, Any]]:
        """
        Convert location detection data to GPS coordinates
        
        Args:
            location_detection: Dictionary with country, region, city_or_area, confidence
            confidence_threshold: Minimum confidence (0-100) to attempt geocoding
            
        Returns:
            Dictionary with latitude, longitude, or None if below threshold or geocoding fails
        """
        # Check confidence threshold
        confidence = location_detection.get('confidence', 0)
        if confidence < confidence_threshold:
            return None
        
        # Build location query
        country = location_detection.get('country', '').strip()
        region = location_detection.get('region', '').strip()
        city = location_detection.get('city_or_area', '').strip()
        
        # Filter out uncertain/unknown values and vague descriptions
        vague_terms = [
            'uncertain', 'unknown', 'dichtbij', 'near', 'around', 'approximately',
            'stadscentrum', 'city center', 'centrum', 'ergens', 'somewhere',
            'onbekend', 'onzeker', 'het', 'de', 'een'
        ]
        
        location_parts = []
        if city and city.lower() not in vague_terms and not any(v in city.lower() for v in vague_terms):
            location_parts.append(city)
        if region and region.lower() not in vague_terms and not any(v in region.lower() for v in vague_terms):
            location_parts.append(region)
        if country and country.lower() not in vague_terms and not any(v in country.lower() for v in vague_terms):
            location_parts.append(country)
        
        if not location_parts:
            return None
        
        query = ', '.join(location_parts)
        
        # Check cache first
        cache = GeoLocator._load_cache()
        if query in cache:
            cached = cache[query]
            # Check if cache entry is fresh (not older than reasonable time)
            return cached.get('coordinates')
        
        # Query Nominatim
        try:
            coords = GeoLocator._query_nominatim(query)
            
            # Store in cache
            if coords:
                cache[query] = {
                    'coordinates': coords,
                    'query': query,
                    'confidence': confidence
                }
                GeoLocator._save_cache(cache)
            
            return coords
        except Exception as e:
            print(f"Warning: Geocoding failed for '{query}': {e}")
            return None
    
    @staticmethod
    def _query_nominatim(query: str) -> Optional[Dict[str, float]]:
        """
        Query Nominatim API for location coordinates
        
        Args:
            query: Location query string (e.g., "Treptower Park, Berlin, Germany")
            
        Returns:
            Dictionary with latitude, longitude, or None if not found
        """
        try:
            params = {
                'q': query,
                'format': 'json',
                'limit': 1  # Get best match only
            }
            
            headers = {
                'User-Agent': GeoLocator.USER_AGENT
            }
            
            # Add timeout to avoid hanging
            response = requests.get(
                GeoLocator.NOMINATIM_BASE,
                params=params,
                headers=headers,
                timeout=5
            )
            
            if response.status_code == 200:
                results = response.json()
                if results:
                    result = results[0]
                    return {
                        'latitude': float(result['lat']),
                        'longitude': float(result['lon']),
                        'display_name': result.get('display_name', query)
                    }
            
            return None
        except requests.Timeout:
            print(f"Warning: Nominatim API timeout for '{query}'")
            return None
        except Exception as e:
            print(f"Warning: Error querying Nominatim: {e}")
            return None
    
    @staticmethod
    def format_gps_string(coordinates: Dict[str, float]) -> str:
        """
        Format GPS coordinates as human-readable string
        
        Args:
            coordinates: Dictionary with latitude, longitude
            
        Returns:
            Formatted string like "52.4351°N, 13.4434°E"
        """
        lat = coordinates['latitude']
        lon = coordinates['longitude']
        
        lat_dir = 'N' if lat >= 0 else 'S'
        lon_dir = 'E' if lon >= 0 else 'W'
        
        lat_abs = abs(lat)
        lon_abs = abs(lon)
        
        return f"{lat_abs:.4f}°{lat_dir}, {lon_abs:.4f}°{lon_dir}"
