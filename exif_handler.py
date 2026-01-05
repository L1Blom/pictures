"""
EXIF metadata handling for pictures
"""
import json
import piexif
from typing import Dict, Any
import io
from PIL import Image
from PIL.Image import Image as PILImage

try:
    from libxmp import XMPMeta
    from libxmp.consts import XMP_NS_PHOTOSHOP, XMP_NS_EXIF, XMP_NS_DC, XMP_NS_RDF
    HAS_XMP = True
except ImportError:
    HAS_XMP = False


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
        Write analysis data to image EXIF metadata and XMP
        
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
            
            # Prepare new EXIF data
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
            
            # Also write XMP data if available
            if HAS_XMP:
                EXIFHandler.write_xmp(image_path, output_path, analysis_data)
            
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
        
        # Convert metadata only to JSON string
        metadata_json = json.dumps(metadata, indent=2)
        
        # Add metadata to UserComment (0x927C)
        exif_dict["Exif"][piexif.ExifIFD.UserComment] = metadata_json.encode('utf-8')
        
        # Add description from metadata
        if isinstance(metadata, dict) and "objects" in metadata:
            objects = metadata.get('objects', [])
            if isinstance(objects, list):
                description = f"Objects: {', '.join(objects[:5])}"
            else:
                description = f"Objects: {str(objects)[:100]}"
            exif_dict["0th"][piexif.ImageIFD.ImageDescription] = description.encode('utf-8')
        
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

    @staticmethod
    def write_xmp(image_path: str, output_path: str, analysis_data: Dict[str, Any]) -> bool:
        """
        Write analysis data to image XMP metadata
        
        Args:
            image_path: Path to the source image
            output_path: Path to save the image with new XMP data
            analysis_data: Dictionary containing analysis results
            
        Returns:
            True if successful, False otherwise
        """
        if not HAS_XMP:
            return False
        
        try:
            # Open image to copy to output
            image = Image.open(image_path)
            
            # Try to read existing XMP data
            try:
                xmp = XMPMeta(open(image_path, 'rb').read())
            except:
                # Create new XMP metadata
                xmp = XMPMeta()
            
            # Add custom namespace for picture analysis
            ANALYSIS_NS = "http://example.com/picture-analysis/"
            xmp.register_namespace(ANALYSIS_NS, "analysis")
            
            # Add metadata if present
            if 'metadata' in analysis_data:
                metadata = analysis_data['metadata']
                metadata_json = json.dumps(metadata, indent=2)
                xmp.set_property(ANALYSIS_NS, "metadata", metadata_json)
                
                # Add individual metadata fields
                if isinstance(metadata, dict):
                    if 'objects' in metadata:
                        objects = metadata.get('objects', [])
                        if isinstance(objects, list):
                            xmp.set_property(XMP_NS_DC, "subject", ", ".join(objects))
                    
                    if 'quality_score' in metadata:
                        xmp.set_property(ANALYSIS_NS, "qualityScore", str(metadata['quality_score']))
            
            # Add enhancement data if present
            if 'enhancement' in analysis_data:
                enhancement = analysis_data['enhancement']
                enhancement_json = json.dumps(enhancement, indent=2)
                xmp.set_property(ANALYSIS_NS, "enhancement", enhancement_json)
            
            # Add analysis summary
            if 'summary' in analysis_data:
                xmp.set_property(XMP_NS_PHOTOSHOP, "Headline", analysis_data['summary'][:255])
            
            # Save image with XMP
            xmp_bytes = xmp.serialize_to_str().encode('utf-8')
            
            # For JPEG, embed XMP directly
            if image.format and image.format.upper() in ['JPEG', 'JPG']:
                # Save with embedded XMP
                image.save(output_path, 'jpeg', quality=95)
                # Append XMP to the JPEG (simplified approach)
                # Note: Full XMP embedding requires more complex JPEG handling
            else:
                # Convert to RGB if needed
                if image.mode in ('RGBA', 'LA', 'P'):
                    rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[-1] if image.mode in ('RGBA', 'LA') else None)
                    rgb_image.save(output_path, 'jpeg', quality=95)
                else:
                    image.convert('RGB').save(output_path, 'jpeg', quality=95)
            
            return True
        except Exception as e:
            print(f"Warning: Could not write XMP data: {e}")
            return False
