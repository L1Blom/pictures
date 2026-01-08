#!/usr/bin/env python3
"""
Verify metadata stored in analyzed images
"""
import piexif
import json
from pathlib import Path
from typing import Optional, Dict, Any

def verify_image_metadata(image_path: str) -> Dict[str, Any]:
    """
    Read and display all metadata stored in an image
    
    Args:
        image_path: Path to the image file
        
    Returns:
        Dictionary with all metadata found
    """
    try:
        exif_dict = piexif.load(image_path)
        result = {
            'file': image_path,
            'status': 'success',
            'metadata': {},
            'exif_fields': {}
        }
        
        # Read standard EXIF fields
        if "0th" in exif_dict:
            for tag, value in exif_dict["0th"].items():
                tag_name = piexif.TAGS["0th"][tag]["name"]
                try:
                    if isinstance(value, bytes):
                        result['exif_fields'][tag_name] = value.decode('utf-8', errors='ignore')[:100]
                    else:
                        result['exif_fields'][tag_name] = str(value)[:100]
                except:
                    pass
        
        # Read UserComment (where our analysis metadata is stored)
        if "Exif" in exif_dict:
            if piexif.ExifIFD.UserComment in exif_dict["Exif"]:
                comment = exif_dict["Exif"][piexif.ExifIFD.UserComment]
                try:
                    metadata = json.loads(comment.decode('utf-8'))
                    result['metadata'] = metadata
                except:
                    result['metadata'] = {'raw': comment.decode('utf-8', errors='ignore')[:200]}
        
        return result
    
    except Exception as e:
        return {
            'file': image_path,
            'status': 'error',
            'error': str(e)
        }

def print_verification(image_path: str):
    """Pretty print metadata verification"""
    result = verify_image_metadata(image_path)
    
    print(f"\n{'='*60}")
    print(f"Image: {result['file']}")
    print(f"Status: {result['status']}")
    print(f"{'='*60}")
    
    if result['status'] == 'error':
        print(f"Error: {result['error']}")
        return
    
    # Print analysis metadata
    if result['metadata']:
        metadata = result['metadata'].get('metadata', {})
        enhancement = result['metadata'].get('enhancement', {})
        
        print("\n✓ ANALYSIS METADATA (in UserComment):")
        print(f"  Timestamp: {result['metadata'].get('timestamp', 'N/A')}")
        
        if metadata:
            print(f"\n  METADATA FIELDS ({len(metadata)} found):")
            for key, value in metadata.items():
                if isinstance(value, list):
                    val_str = ', '.join(str(v) for v in value[:3])
                    if len(value) > 3:
                        val_str += f" ... (+{len(value)-3} more)"
                else:
                    val_str = str(value)[:80]
                print(f"    • {key}: {val_str}")
        
        if enhancement:
            print(f"\n  ENHANCEMENT FIELDS ({len(enhancement)} found):")
            for key in list(enhancement.keys())[:5]:
                val = enhancement[key]
                val_str = str(val)[:60]
                print(f"    • {key}: {val_str}")
            if len(enhancement) > 5:
                print(f"    ... +{len(enhancement)-5} more fields")
    
    # Print standard EXIF fields
    if result['exif_fields']:
        print(f"\n✓ STANDARD EXIF FIELDS ({len(result['exif_fields'])} found):")
        for key, value in list(result['exif_fields'].items())[:8]:
            print(f"  • {key}: {value[:60]}")
        if len(result['exif_fields']) > 8:
            print(f"  ... +{len(result['exif_fields'])-8} more fields")
    
    print()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python verify_image_metadata.py <image_path> [image_path2] ...")
        print("\nExample:")
        print("  python verify_image_metadata.py output_test_xmp2/test_result_analyzed.jpg")
        sys.exit(1)
    
    for image_path in sys.argv[1:]:
        if Path(image_path).exists():
            print_verification(image_path)
        else:
            print(f"✗ File not found: {image_path}")
