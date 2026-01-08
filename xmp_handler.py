"""
XMP metadata handler for embedding analysis results into images
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import xml.etree.ElementTree as ET
from PIL import Image

try:
    from xmp_toolkit import XMPMeta
    HAS_XMP_TOOLKIT = True
except ImportError:
    HAS_XMP_TOOLKIT = False


class XMPHandler:
    """Handle XMP metadata embedding in images"""
    
    # XMP namespaces
    NS_CUSTOM = "http://example.com/picture-analysis/1.0/"
    NS_DC = "http://purl.org/dc/elements/1.1/"
    NS_RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    NS_X = "adobe:ns:meta/"
    
    @staticmethod
    def write_analysis_metadata_simple(image_path: Path, analysis_data: Dict[str, Any]) -> bool:
        """
        Write analysis results to image using simple method (comment fields).
        This is a lightweight alternative that doesn't require xmp_toolkit.
        
        Args:
            image_path: Path to the image file
            analysis_data: Analysis results dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            image = Image.open(str(image_path))
            
            # Create metadata dictionary from analysis
            metadata = analysis_data.get('metadata', {})
            
            # Store as image info/comment
            if image.info is None:
                image.info = {}
            
            # Add metadata fields as separate comment entries
            for key, value in metadata.items():
                if isinstance(value, (list, dict)):
                    image.info[f'analysis_{key}'] = json.dumps(value)
                else:
                    image.info[f'analysis_{key}'] = str(value)
            
            # Add timestamp
            image.info['analysis_timestamp'] = datetime.now().isoformat()
            
            # Save back (this preserves comments in most formats)
            if image.format and image.format.upper() in ['JPEG', 'JPG']:
                image.save(str(image_path), 'jpeg', quality=95)
            
            return True
        except Exception as e:
            print(f"Warning: Could not embed metadata in {image_path} (simple method): {e}")
            return False
    
    @staticmethod
    def write_analysis_metadata(image_path: Path, analysis_data: Dict[str, Any]) -> bool:
        """
        Write analysis results to image XMP metadata
        
        Args:
            image_path: Path to the image file
            analysis_data: Analysis results dictionary containing metadata, enhancement, etc.
            
        Returns:
            True if successful, False otherwise
        """
        # Use simple method if xmp_toolkit not available
        if not HAS_XMP_TOOLKIT:
            return XMPHandler.write_analysis_metadata_simple(image_path, analysis_data)
        
        try:
            # Create XMP metadata object
            xmp = XMPMeta()
            
            # Register custom namespace
            xmp.register_namespace(XMPHandler.NS_CUSTOM, "analysis")
            
            # Add basic analysis info
            xmp.set_property(
                XMPHandler.NS_CUSTOM,
                "analysis:timestamp",
                datetime.now().isoformat()
            )
            
            # Add analysis metadata
            metadata = analysis_data.get('metadata', {})
            if metadata:
                xmp.set_property(
                    XMPHandler.NS_CUSTOM,
                    "analysis:metadata",
                    json.dumps(metadata)
                )
            
            # Add enhancement recommendations
            enhancement = analysis_data.get('enhancement', {})
            if enhancement:
                # Store summary if available
                if 'summary' in enhancement:
                    xmp.set_property(
                        XMPHandler.NS_CUSTOM,
                        "analysis:enhancement_summary",
                        enhancement['summary']
                    )
                
                # Store enhancement parameters as JSON (excluding raw_response)
                enhancement_params = {
                    k: v for k, v in enhancement.items()
                    if k not in ['summary', 'raw_response']
                }
                if enhancement_params:
                    xmp.set_property(
                        XMPHandler.NS_CUSTOM,
                        "analysis:enhancement_params",
                        json.dumps(enhancement_params)
                    )
            
            # Add other analysis results
            for key in ['color_analysis', 'quality_metrics', 'damage_assessment']:
                if key in analysis_data:
                    value = analysis_data[key]
                    if isinstance(value, (dict, list)):
                        xmp.set_property(
                            XMPHandler.NS_CUSTOM,
                            f"analysis:{key}",
                            json.dumps(value)
                        )
                    else:
                        xmp.set_property(
                            XMPHandler.NS_CUSTOM,
                            f"analysis:{key}",
                            str(value)
                        )
            
            # Write metadata to file
            xmp.serialize(str(image_path), in_place=True)
            return True
            
        except Exception as e:
            print(f"Warning: Could not embed XMP metadata in {image_path}: {e}")
            return False
    
    @staticmethod
    def read_analysis_metadata(image_path: Path) -> Optional[Dict[str, Any]]:
        """
        Read analysis results from image XMP metadata
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Dictionary of analysis data if found, None otherwise
        """
        if XMPMeta is None:
            return None
        
        try:
            xmp = XMPMeta.from_file(str(image_path))
            
            analysis_data = {}
            
            # Read timestamp
            timestamp = xmp.get_property(
                XMPHandler.NS_CUSTOM,
                "analysis:timestamp"
            )
            if timestamp:
                analysis_data['timestamp'] = str(timestamp)
            
            # Read metadata
            metadata_json = xmp.get_property(
                XMPHandler.NS_CUSTOM,
                "analysis:metadata"
            )
            if metadata_json:
                analysis_data['metadata'] = json.loads(str(metadata_json))
            
            # Read enhancement data
            enhancement_summary = xmp.get_property(
                XMPHandler.NS_CUSTOM,
                "analysis:enhancement_summary"
            )
            if enhancement_summary:
                analysis_data['enhancement_summary'] = str(enhancement_summary)
            
            enhancement_params = xmp.get_property(
                XMPHandler.NS_CUSTOM,
                "analysis:enhancement_params"
            )
            if enhancement_params:
                analysis_data['enhancement_params'] = json.loads(str(enhancement_params))
            
            return analysis_data if analysis_data else None
            
        except Exception as e:
            print(f"Warning: Could not read XMP metadata from {image_path}: {e}")
            return None
