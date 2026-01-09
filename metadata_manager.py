"""
Unified metadata management interface

Provides a single facade for:
- EXIF metadata handling
- XMP metadata handling
- Geolocation and GPS handling
"""

from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from exif_handler import EXIFHandler
from xmp_handler import XMPHandler
from geolocation import GeoLocator


class MetadataManager:
    """
    Unified interface for all metadata operations
    
    Provides a single access point for EXIF, XMP, and geolocation handling
    making the code more testable and reducing tight coupling.
    """
    
    def __init__(
        self,
        exif_handler: Optional[EXIFHandler] = None,
        xmp_handler: Optional[XMPHandler] = None,
        geo_locator: Optional[type] = None
    ):
        """
        Initialize MetadataManager with optional dependency injection
        
        Args:
            exif_handler: EXIFHandler instance (creates new if None)
            xmp_handler: Not needed - XMPHandler is static, but kept for consistency
            geo_locator: Not needed - GeoLocator is static, but kept for consistency
        """
        self.exif = exif_handler or EXIFHandler()
        # XMP and GeoLocator are static, so we reference them directly
        self.xmp = XMPHandler
        self.geo = GeoLocator
    
    def embed_metadata(
        self,
        image_path: str,
        output_path: str,
        analysis_data: Dict[str, Any]
    ) -> bool:
        """
        Embed all metadata (EXIF, XMP, GPS) into image
        
        Args:
            image_path: Path to source image
            output_path: Path to save image with metadata
            analysis_data: Complete analysis dictionary
            
        Returns:
            True if successful, False otherwise
        """
        success = True
        
        # Write EXIF data
        exif_success = self.exif.write_exif(image_path, output_path, analysis_data)
        if exif_success:
            print(f"✓ Image saved with EXIF data: {output_path}")
        else:
            print(f"⚠ Could not embed EXIF, saved without: {output_path}")
            success = False
        
        # Write XMP metadata
        xmp_success = self.xmp.write_analysis_metadata(Path(output_path), analysis_data)
        if xmp_success:
            print(f"✓ XMP metadata embedded: {output_path}")
        else:
            print(f"⚠ Could not embed XMP metadata (non-critical)")
        
        return success
    
    def geocode_location(self, location_data: Dict[str, Any], confidence_threshold: int = 80) -> Optional[Dict[str, Any]]:
        """
        Geocode location detection data to GPS coordinates
        
        Args:
            location_data: Location detection dictionary with country, region, city_or_area, confidence
            confidence_threshold: Minimum confidence (0-100) to attempt geocoding
            
        Returns:
            Dictionary with latitude/longitude or None if failed
        """
        return self.geo.geocode_location(location_data, confidence_threshold)
    
    def format_gps_string(self, coordinates: Tuple[float, float]) -> str:
        """
        Format GPS coordinates as readable string
        
        Args:
            coordinates: Tuple of (latitude, longitude)
            
        Returns:
            Formatted GPS string
        """
        return self.geo.format_gps_string(coordinates)
    
    def read_exif(self, image_path: str) -> Dict[str, Any]:
        """
        Read EXIF data from image
        
        Args:
            image_path: Path to image file
            
        Returns:
            Dictionary containing EXIF data
        """
        return self.exif.read_exif(image_path)
    
    def copy_exif(
        self,
        source_image_path: str,
        target_image_path: str,
        output_path: str
    ) -> bool:
        """
        Copy EXIF data from source image to target image
        
        Args:
            source_image_path: Path to source image
            target_image_path: Path to target image
            output_path: Path to save result
            
        Returns:
            True if successful, False otherwise
        """
        return self.exif.copy_exif(source_image_path, target_image_path, output_path)
