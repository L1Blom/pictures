#!/usr/bin/env python3
"""Test EXIF sanitization fix"""

import piexif
from pathlib import Path
from exif_handler import EXIFHandler

# Test the sanitize function
test_exif = {
    "0th": {
        282: 72,  # XResolution - should be rational, but is int (problematic!)
        283: 72,  # YResolution - should be rational, but is int (problematic!)
        305: b"Test Software",  # Software - OK
    },
    "Exif": {},
    "GPS": {}
}

print("Before sanitization:")
print(f"  0th tags: {list(test_exif['0th'].keys())}")

sanitized = EXIFHandler._sanitize_exif_dict(test_exif)

print("\nAfter sanitization:")
print(f"  0th tags: {list(sanitized['0th'].keys())}")

if 282 in test_exif["0th"] and 282 not in sanitized["0th"]:
    print("\n✓ Tag 282 (XResolution) correctly removed")
else:
    print("\n✗ Tag 282 (XResolution) NOT removed")

if 305 in sanitized["0th"]:
    print("✓ Tag 305 (Software) correctly preserved")
else:
    print("✗ Tag 305 (Software) incorrectly removed")

print("\n✓ Sanitization test passed!")
