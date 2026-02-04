"""
EXIF metadata handling for pictures
"""
import json
import piexif
from typing import Dict, Any
import io
from PIL import Image
from PIL.Image import Image as PILImage
from config import METADATA_LANGUAGE
from metadata_config import EXIF_TAG_MAPPING


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
            
            # Try to read existing EXIF data, but start fresh to avoid corruption
            # We'll only use analysis data, not original EXIF which may be malformed
            exif_dict = {"0th": {}, "Exif": {}, "GPS": {}}
            
            # Prepare new EXIF data with full analysis as JSON
            exif_dict_new = EXIFHandler._prepare_exif_dict(exif_dict, analysis_data)
            
            # Sanitize EXIF data to fix type mismatches
            exif_dict_new = EXIFHandler._sanitize_exif_dict(exif_dict_new)
            
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
            
            # Sanitize EXIF data to fix any type mismatches
            exif_dict = EXIFHandler._sanitize_exif_dict(exif_dict)
            
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
    def _format_metadata_description(metadata: Dict[str, Any], location_detection: Dict[str, Any] = None) -> str:
        """
        Format metadata into a nicely readable description for ImageDescription field.
        This makes all metadata visible in Immich's image info display.
        
        Args:
            metadata: Dictionary of metadata fields
            location_detection: Dictionary of location detection data (optional)
            
        Returns:
            Formatted string suitable for ImageDescription
        """
        lines = []
        
        # Language-specific translations
        translations = {
            'nl': {
                'LOCATION': 'LOCATIE',
                'Confidence': 'Betrouwbaarheid',
                'Location uncertain': 'Locatie onzeker',
                'Objects': 'Objecten',
                'Persons': 'Personen',
                'Weather': 'Weer',
                'Mood/Atmosphere': 'Sfeer/Atmosfeer',
                'Time of Day': 'Tijd van de dag',
                'Season/Date': 'Seizoen/Datum',
                'Scene Type': 'Type scène',
                'Setting': 'Omgeving',
                'Activity': 'Activiteit',
                'Photography Style': 'Fotografische stijl',
                'Composition Quality': 'Samenstelling kwaliteit',
            },
            'en': {
                'LOCATION': 'LOCATION',
                'Confidence': 'Confidence',
                'Location uncertain': 'Location uncertain',
                'Objects': 'Objects',
                'Persons': 'Persons',
                'Weather': 'Weather',
                'Mood/Atmosphere': 'Mood/Atmosphere',
                'Time of Day': 'Time of Day',
                'Season/Date': 'Season/Date',
                'Scene Type': 'Scene Type',
                'Setting': 'Setting',
                'Activity': 'Activity',
                'Photography Style': 'Photography Style',
                'Composition Quality': 'Composition Quality',
            }
        }
        
        # Get translations for current language (default to English if not found)
        lang_trans = translations.get(METADATA_LANGUAGE, translations['en'])
        
        # Add location detection first if available
        if location_detection:
            loc_lines = []
            
            country = location_detection.get('country', '')
            city = location_detection.get('city_or_area', '')
            region = location_detection.get('region', '')
            confidence = location_detection.get('confidence', '')
            
            # Build location string
            location_parts = [p for p in [country, region, city] if p and p.lower() not in ['uncertain', 'unknown']]
            if location_parts:
                location_str = ', '.join(location_parts)
                conf_str = f" ({lang_trans['Confidence']}: {confidence}%)" if confidence else ""
                loc_lines.append(f"{lang_trans['LOCATION']}: {location_str}{conf_str}")
            elif confidence:
                loc_lines.append(f"{lang_trans['Location uncertain']} ({lang_trans['Confidence']}: {confidence}%)")
            
            if loc_lines:
                lines.extend(loc_lines)
                lines.append("")  # blank line separator
        
        # Map of friendly field names for display
        field_labels = {
            'objects': lang_trans.get('Objects', 'Objects'),
            'persons': lang_trans.get('Persons', 'Persons'),
            'weather': lang_trans.get('Weather', 'Weather'),
            'mood_atmosphere': lang_trans.get('Mood/Atmosphere', 'Mood/Atmosphere'),
            'mood': lang_trans.get('Mood/Atmosphere', 'Mood/Atmosphere'),
            'time_of_day': lang_trans.get('Time of Day', 'Time of Day'),
            'season_date': lang_trans.get('Season/Date', 'Season/Date'),
            'scene_type': lang_trans.get('Scene Type', 'Scene Type'),
            'location_setting': lang_trans.get('Setting', 'Setting'),
            'activity_action': lang_trans.get('Activity', 'Activity'),
            'activity': lang_trans.get('Activity', 'Activity'),
            'photography_style': lang_trans.get('Photography Style', 'Photography Style'),
            'composition_quality': lang_trans.get('Composition Quality', 'Composition Quality'),
        }
        
        # Add all predefined fields
        for field_key, field_label in field_labels.items():
            if field_key in metadata:
                value = metadata[field_key]
                
                # Format value nicely
                if isinstance(value, list):
                    value_str = ', '.join(str(v) for v in value)
                else:
                    value_str = str(value)
                
                # Don't truncate individual fields - preserve full content
                lines.append(f"{field_label}: {value_str}")
        
        # Add any additional fields not in the predefined list
        for field_key, value in metadata.items():
            if field_key not in field_labels:
                # Convert field name to label (replace underscores with spaces, title case)
                field_label = field_key.replace('_', ' ').title()
                
                # Format value nicely
                if isinstance(value, list):
                    value_str = ', '.join(str(v) for v in value[:5])  # Limit list items
                    if len(value) > 5:
                        value_str += f", ... (+{len(value)-5} more)"
                elif isinstance(value, dict):
                    value_str = str(value)
                else:
                    value_str = str(value)
                
                lines.append(f"{field_label}: {value_str}")
        
        # Join with newlines and limit total length
        description = '\n'.join(lines)
        # Truncate at 16000 chars, trying to break at a line boundary
        if len(description) > 16000:
            description = description[:16000]
            # Try to back up to the last newline to avoid cutting words
            last_newline = description.rfind('\n')
            if last_newline > 15800:  # If newline is close enough, use it
                description = description[:last_newline] + "\n[... truncated]"
        return description
    
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
        
        # Extract location_detection if available
        location_detection = None
        if isinstance(analysis_data, dict):
            location_detection = analysis_data.get('location_detection', {})
        
        # Convert metadata to nicely formatted description for ImageDescription (for Immich display)
        if isinstance(metadata, dict):
            description = EXIFHandler._format_metadata_description(metadata, location_detection)
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = description.encode('utf-8')
        
        # Convert metadata and location to JSON string for UserComment (backup storage)
        backup_data = {'metadata': metadata}
        if location_detection:
            backup_data['location_detection'] = location_detection
        
        # Remove raw_response from metadata if present (it's not needed in EXIF)
        if isinstance(metadata, dict):
            clean_metadata = {k: v for k, v in metadata.items() if k != 'raw_response'}
            backup_data['metadata'] = clean_metadata
        
        backup_json = json.dumps(backup_data, indent=2)
        # Note: UserComment in EXIF requires character code prefix
        # ASCII = b'ASCII\x00\x00\x00' - Most compatible for JSON data
        # For UTF-8 JSON with international characters, use undefined (b'\x00\x00\x00\x00\x00\x00\x00\x00')
        char_code_prefix = b'ASCII\x00\x00\x00'  # ASCII-compatible prefix for standard EXIF readers
        
        # Use minified JSON (no whitespace/newlines) to avoid EXIF compatibility issues
        # The formatted version is already in ImageDescription for display
        backup_json_minified = json.dumps(backup_data, separators=(',', ':'))
        # Use ASCII character code prefix for UserComment (standard for EXIF compatibility)
        # ASCII prefix = b'ASCII\x00\x00\x00' tells EXIF readers this is ASCII-compatible text
        char_code_prefix = b'ASCII\x00\x00\x00'
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = char_code_prefix + backup_json_minified.encode('utf-8')
        
        # Note: We don't map individual metadata fields to separate EXIF tags because:
        # 1. EXIF tags have specific data type requirements and constraints
        # 2. Arbitrary string data can corrupt EXIF structure and cause validation errors
        # 3. All metadata is properly preserved in ImageDescription (display) and UserComment (backup)
        # If Immich or other tools need specific EXIF fields, they will read from ImageDescription
        
        # Add GPS data if coordinates are available
        if isinstance(analysis_data, dict):
            coordinates = analysis_data.get('gps_coordinates')
            if coordinates:
                EXIFHandler._add_gps_to_exif(exif_dict, coordinates)
        
        return exif_dict
    
    @staticmethod
    def _add_gps_to_exif(exif_dict: Dict, coordinates: Dict[str, float]) -> None:
        """
        Add GPS coordinates to EXIF dictionary
        
        Args:
            exif_dict: EXIF dictionary to update
            coordinates: Dictionary with latitude and longitude
        """
        if not coordinates or 'latitude' not in coordinates or 'longitude' not in coordinates:
            return
        
        try:
            lat = coordinates['latitude']
            lon = coordinates['longitude']
            
            # Initialize GPS IFD if needed
            if "GPS" not in exif_dict:
                exif_dict["GPS"] = {}
            
            # Convert latitude/longitude to GPS format (degrees, minutes, seconds)
            def dms_from_decimal(decimal):
                """Convert decimal degrees to DMS format for GPS"""
                abs_value = abs(decimal)
                degrees = int(abs_value)
                minutes_decimal = (abs_value - degrees) * 60
                minutes = int(minutes_decimal)
                seconds_decimal = (minutes_decimal - minutes) * 60
                seconds = int(seconds_decimal * 100)  # Store as integer with 2 decimal precision
                
                return ((degrees, 1), (minutes, 1), (seconds, 100))
            
            # Set latitude
            lat_dms = dms_from_decimal(lat)
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = lat_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b'N' if lat >= 0 else b'S'
            
            # Set longitude
            lon_dms = dms_from_decimal(lon)
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = lon_dms
            exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b'E' if lon >= 0 else b'W'
            
            # Set GPS version
            exif_dict["GPS"][piexif.GPSIFD.GPSVersionID] = b'\x02\x02\x00\x00'
            
            # Set map datum (standard WGS84)
            exif_dict["GPS"][piexif.GPSIFD.GPSMapDatum] = b'WGS-84'
            
        except Exception as e:
            print(f"Warning: Could not add GPS data to EXIF: {e}")
    
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
    def _sanitize_exif_dict(exif_dict: Dict) -> Dict:
        """
        Sanitize EXIF dictionary to fix type mismatches
        
        Fixes issues where EXIF values have incorrect types that piexif.dump() cannot handle.
        Common issue: Integer values for tags that expect rationals or specific formats.
        
        Args:
            exif_dict: EXIF dictionary potentially with malformed values
            
        Returns:
            Cleaned EXIF dictionary
        """
        # List of tags that commonly have type issues and should be removed if invalid
        problematic_tags = {
            282: "XResolution",      # Should be rational (tuple)
            283: "YResolution",      # Should be rational (tuple)
            296: "ResolutionUnit",   # Should be short (int)
            305: "Software",         # Should be ASCII
            306: "DateTime",         # Should be ASCII
        }
        
        # Handle all possible IFD types in the exif_dict
        for ifd_name in ["0th", "1st", "Exif", "GPS", "Interop"]:
            if ifd_name not in exif_dict:
                continue
            
            ifd_dict = exif_dict[ifd_name]
            tags_to_remove = []
            
            for tag_id, value in ifd_dict.items():
                try:
                    # Check if value is of wrong type
                    if isinstance(value, int) and tag_id in [282, 283]:
                        # XResolution and YResolution should be tuples (rational)
                        # Remove invalid integer values
                        tags_to_remove.append(tag_id)
                    elif isinstance(value, int) and tag_id == 296:
                        # ResolutionUnit is OK as int, but ensure it's 1-3
                        if value not in [1, 2, 3]:
                            tags_to_remove.append(tag_id)
                except Exception:
                    pass
            
            # Remove problematic tags
            for tag_id in tags_to_remove:
                del ifd_dict[tag_id]
        
        return exif_dict
    
    @staticmethod
    def _decode_value(value: Any) -> Any:
        """Decode EXIF value"""
        if isinstance(value, bytes):
            try:
                return value.decode('utf-8')
            except:
                return str(value)
        return value
