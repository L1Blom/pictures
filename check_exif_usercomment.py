#!/usr/bin/env python3
"""
Diagnostic script to check EXIF UserComment encoding and format
"""
import piexif
import json
import sys

if len(sys.argv) < 2:
    print("Usage: python check_exif_usercomment.py <image_file>")
    sys.exit(1)

image_file = sys.argv[1]

try:
    exif_dict = piexif.load(image_file)
    
    # Get UserComment
    if "Exif" in exif_dict and piexif.ExifIFD.UserComment in exif_dict["Exif"]:
        user_comment_bytes = exif_dict["Exif"][piexif.ExifIFD.UserComment]
        
        print(f"✓ UserComment found")
        print(f"  Total bytes: {len(user_comment_bytes)}")
        print(f"\n  First 50 bytes (hex): {user_comment_bytes[:50].hex()}")
        print(f"  First 50 bytes (raw): {user_comment_bytes[:50]}")
        
        # Check for character code prefix
        prefix = user_comment_bytes[:8]
        print(f"\n  Character code prefix: {prefix.hex()}")
        
        if prefix == b'\x00' * 8:
            print(f"  ✓ Correct prefix for undefined/binary UTF-8")
        elif prefix == b'ASCII\x00\x00\x00':
            print(f"  ✓ ASCII prefix (UTF-8 might not work well)")
        else:
            print(f"  ⚠ Unknown prefix")
        
        # Try to extract and decode the JSON
        json_bytes = user_comment_bytes[8:]
        
        try:
            # Try UTF-8 decode
            json_str = json_bytes.decode('utf-8')
            print(f"\n  ✓ UTF-8 decode successful")
            print(f"  JSON length: {len(json_str)} characters")
            
            # Try to parse JSON
            data = json.loads(json_str)
            print(f"\n  ✓ JSON parsing successful")
            print(f"  Top-level keys: {list(data.keys())}")
            
            # Check for actual newlines in the JSON
            if '\n' in json_str:
                print(f"\n  ⚠ WARNING: JSON still contains newline characters!")
                # Count them
                newline_count = json_str.count('\n')
                print(f"     Found {newline_count} newline characters")
            else:
                print(f"\n  ✓ JSON contains no newline characters (minified)")
            
            # Show first 200 chars of JSON
            print(f"\n  First 200 chars of JSON:\n  {json_str[:200]}")
            
        except UnicodeDecodeError as e:
            print(f"\n  ✗ UTF-8 decode failed: {e}")
            print(f"  Trying other encodings...")
            
            # Try Latin-1
            try:
                json_str = json_bytes.decode('latin-1')
                print(f"  Latin-1 decode: {json_str[:100]}")
            except:
                pass
    else:
        print("✗ No UserComment found in EXIF")

except Exception as e:
    print(f"✗ Error: {e}")
    import traceback
    traceback.print_exc()
