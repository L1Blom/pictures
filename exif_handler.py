"""
EXIF metadata handling for pictures
"""
import json
import piexif
from typing import Dict, Any
import io
from PIL import Image
from PIL.Image import Image as PILImage
from config import EXIF_TAG_MAPPING


class EXIFHandler:
    """Handles EXIF metadata reading and writing"""
    
    @staticmethod
    def read_exif(image_path: str) -> Dict[str, Any]:
        """
        Read EXIF data from an image file
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary containing EXIF data
        """
        try:
            exif_dict = piexif.load(image_path)
            return EXIFHandler._parse_exif_dict(exif_dict)
        except Exception as e:
            print(f"Warning: Could not read EXIF data: {e}")
            return {}
    
    @staticmethod
    def write_exif(
        image_path: str,
        output_path: str,
        analysis_data: Dict[str, Any]
    ) -> bool:
        """
        Write analysis data to image EXIF metadata (and XMP if available)
        
        Args:
            image_path: Path to the source image
            output_path: Path to save the image with new EXIF data
            analysis_data: Dictionary containing analysis results
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Open the image
            image = Image.open(image_path)
            
            # Try to read existing EXIF data
            try:
                exif_dict = piexif.load(image_path)
            except:
                exif_dict = {"0th": {}, "Exif": {}, "GPS": {}}
            
            # Prepare new EXIF data with full analysis as JSON
            exif_dict_new = EXIFHandler._prepare_exif_dict(exif_dict, analysis_data)
            
            # Convert back to bytes
            exif_bytes = piexif.dump(exif_dict_new)
            
            # Save image with EXIF data
            if image.format and image.format.upper() in ['JPEG', 'JPG']:
                image.save(output_path, 'jpeg', exif=exif_bytes, quality=95)
            else:
                # For non-JPEG formats, convert to JPEG
                if image.mode in ('RGBA', 'LA', 'P'):
                    # Convert RGBA to RGB
                    rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                    rgb_image.save(output_path, 'jpeg', exif=exif_bytes, quality=95)
                else:
                    image.convert('RGB').save(output_path, 'jpeg', exif=exif_bytes, quality=95)
            
            return True
        except Exception as e:
            print(f"Warning: Could not write EXIF data: {e}")
            # Save without EXIF if it fails
            try:
                image.save(output_path)
                return True
            except:
                return False
    
    @staticmethod
    def copy_exif(source_image_path: str, target_image_path: str, output_path: str) -> bool:
        """
        Copy EXIF data from source image to target image
        
        Args:
            source_image_path: Path to the image with EXIF data
            target_image_path: Path to the image to add EXIF data to
            output_path: Path to save the result
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Read EXIF from source
            try:
                exif_dict = piexif.load(source_image_path)
            except:
                # No EXIF to copy
                return False
            
            # Open target image
            image = Image.open(target_image_path)
            
            # Convert back to bytes and save
            exif_bytes = piexif.dump(exif_dict)
            
            if image.format and image.format.upper() in ['JPEG', 'JPG']:
                image.save(output_path, 'jpeg', exif=exif_bytes, quality=95)
            else:
                # For non-JPEG formats, convert to JPEG
                if image.mode in ('RGBA', 'LA', 'P'):
                    rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                    rgb_image.save(output_path, 'jpeg', exif=exif_bytes, quality=95)
                else:
                    image.convert('RGB').save(output_path, 'jpeg', exif=exif_bytes, quality=95)
            
            return True
        except Exception as e:
            print(f"Warning: Could not copy EXIF data: {e}")
            return False
    
    @staticmethod
    def _format_metadata_description(metadata: Dict[str, Any]) -> str:
        """
        Format metadata into a nicely readable description for ImageDescription field.
        This makes all metadata visible in Immich's image info display.
        
        Args:
            metadata: Dictionary of metadata fields
            
        Returns:
            Formatted string suitable for ImageDescription
        """
        lines = []
        
        # Map of friendly field names for display
        field_labels = {
            'objects': 'Objects',
            'persons': 'Persons',
            'weather': 'Weather',
            'mood_atmosphere': 'Mood/Atmosphere',
            'time_of_day': 'Time of Day',
            'season_date': 'Season/Date',
            'scene_type': 'Scene Type',
            'location_setting': 'Location/Setting',
            'activity_action': 'Activity',
            'photography_style': 'Photography Style',
            'composition_quality': 'Composition Quality',
        }
        
        for field_key, field_label in field_labels.items():
            if field_key in metadata:
                value = metadata[field_key]
                
                # Format value nicely
                if isinstance(value, list):
                    value_str = ', '.join(str(v) for v in value)
                else:
                    value_str = str(value)
                
                # Truncate to reasonable length for display
                value_str = value_str[:150]
                lines.append(f"{field_label}: {value_str}")
        
        # Join with newlines and limit total length
        description = '\n'.join(lines)
        return description[:500]  # EXIF ImageDescription has limits
    
    @staticmethod
    def _prepare_exif_dict(exif_dict: Dict, analysis_data: Dict[str, Any]) -> Dict:
        """
        Prepare EXIF dictionary with metadata only (separates from enhancement data)
        
        Args:
            exif_dict: Existing EXIF dictionary
            analysis_data: Analysis results (expected to have 'metadata' and 'enhancement' keys)
            
        Returns:
            Updated EXIF dictionary
        """
        # Ensure proper structure
        if "0th" not in exif_dict:
            exif_dict["0th"] = {}
        if "Exif" not in exif_dict:
            exif_dict["Exif"] = {}
        
        # Extract metadata section if it exists, otherwise use entire analysis_data for backward compatibility
        if isinstance(analysis_data, dict) and 'metadata' in analysis_data:
            metadata = analysis_data['metadata']
        else:
            metadata = analysis_data
        
        # Convert metadata to nicely formatted description for ImageDescription (for Immich display)
        if isinstance(metadata, dict):
            description = EXIFHandler._format_metadata_description(metadata)
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = description.encode('utf-8')
        
        # Convert metadata only to JSON string for UserComment (backup storage)
        metadata_json = json.dumps(metadata, indent=2)
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = metadata_json.encode('utf-8')
        
        # Map metadata fields to corresponding EXIF tags for Immich compatibility
        if isinstance(metadata, dict):
            for field_name, field_value in metadata.items():
                # Convert field value to string representation
                if isinstance(field_value, (list, dict)):
                    field_str = ', '.join(str(x) for x in (field_value if isinstance(field_value, list) else [field_value]))
                else:
                    field_str = str(field_value)
                
                # Get EXIF tag name from mapping
                exif_tag_name = EXIF_TAG_MAPPING.get(field_name)
                
                # Skip ImageDescription as we already set it with formatted metadata
                if exif_tag_name == 'ImageDescription':
                    continue
                
                if exif_tag_name:
                    try:
                        # Map tag name to piexif constant
                        if exif_tag_name in dir(piexif.ImageIFD):
                            tag_id = getattr(piexif.ImageIFD, exif_tag_name)
                            exif_dict["0th"][tag_id] = field_str[:100].encode('utf-8')  # Limit length
                        elif exif_tag_name in dir(piexif.ExifIFD):
                            tag_id = getattr(piexif.ExifIFD, exif_tag_name)
                            exif_dict["Exif"][tag_id] = field_str[:100].encode('utf-8')
                        elif exif_tag_name == 'GPSInfo':
                            # GPSInfo requires special handling
                            if "GPS" not in exif_dict:
                                exif_dict["GPS"] = {}
                            # Store location as string for now
                            exif_dict["GPS"][piexif.GPSIFD.GPSMapDatum] = b'WGS-84'
                    except Exception as e:
                        print(f"Warning: Could not set EXIF tag {exif_tag_name}: {e}")
        
        return exif_dict
    
    @staticmethod
    def _parse_exif_dict(exif_dict: Dict) -> Dict[str, Any]:
        """Parse EXIF dictionary into readable format"""
        result = {}
        
        try:
            if "0th" in exif_dict:
                for tag, value in exif_dict["0th"].items():
                    tag_name = piexif.TAGS["0th"][tag]["name"]
                    result[tag_name] = EXIFHandler._decode_value(value)
            
            if "Exif" in exif_dict:
                for tag, value in exif_dict["Exif"].items():
                    tag_name = piexif.TAGS["Exif"][tag]["name"]
                    result[tag_name] = EXIFHandler._decode_value(value)
        except Exception as e:
            print(f"Warning: Error parsing EXIF: {e}")
        
        return result
    
    @staticmethod
    def _decode_value(value: Any) -> Any:
        """Decode EXIF value"""
        if isinstance(value, bytes):
            try:
                return value.decode('utf-8')
            except:
                return str(value)
        return value
