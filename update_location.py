#!/usr/bin/env python3
"""Update location data in JSON and image EXIF from description.txt.

Run from the SOURCE folder (original photos with description.txt).
The script reads Albumnaam + Locatie from description.txt, finds the
corresponding enhanced output folder, then writes GPS data there.

Usage
-----
# Probe a single source folder (shows what would happen, no changes):
    python3 update_location.py "/path/to/source/2000-07 Vakantie Oostenrijk" --probe

# Update a single source folder:
    python3 update_location.py "/path/to/source/2000-07 Vakantie Oostenrijk"

# Update ALL source subfolders recursively:
    python3 update_location.py "/home/leen/bigfoot/NieuwVolume/media/Foto's" --recursive

# Probe all source subfolders:
    python3 update_location.py "/home/leen/bigfoot/NieuwVolume/media/Foto's" --recursive --probe

# Override location (skip description.txt Locatie lookup):
    python3 update_location.py /path/to/source/folder --location "Pruggern, Steiermark, Austria"

# Specify a different enhanced root:
    python3 update_location.py /path/to/source/folder --enhanced-root /path/to/enhanced
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False
    print("⚠ PyYAML not installed. Config file parsing will be disabled.", file=sys.stderr)

try:
    import piexif
    PIEXIF_AVAILABLE = True
except ImportError:
    PIEXIF_AVAILABLE = False
    print("⚠ piexif not installed. EXIF writing will be disabled.", file=sys.stderr)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠ Pillow not installed. Image processing will be disabled.", file=sys.stderr)


# ── Config helpers ───────────────────────────────────────────────────────────

def _default_enhanced_root() -> Path | None:
    """Read enhanced_root from config.yaml."""
    if not YAML_AVAILABLE:
        print("⚠ PyYAML not available. Using default enhanced root.", file=sys.stderr)
        candidate = Path("/home/leen/enhanced")
        return candidate if candidate.is_dir() else None
    
    try:
        cfg_path = Path(__file__).parent / "config.yaml"
        if cfg_path.exists():
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
            root = (cfg.get("output", {}) or {}).get("enhanced_root")
            if root:
                return Path(root)
    except Exception as exc:
        print(f"⚠ Error reading config.yaml: {exc}", file=sys.stderr)
    
    candidate = Path("/home/leen/enhanced")
    return candidate if candidate.is_dir() else None


# ── Description parsing ──────────────────────────────────────────────────────

def _read_description_field(desc_path: Path, *labels: str) -> str | None:
    """Return the first non-empty value for any of the given field labels."""
    pattern = r"(?im)^(?:" + "|".join(re.escape(l) for l in labels) + r")\s*:\s*(.+)$"
    text = desc_path.read_text(encoding="utf-8")
    m = re.search(pattern, text)
    if m:
        v = m.group(1).strip()
        return v if v else None
    return None


def extract_album_name(desc_path: Path) -> str | None:
    return _read_description_field(desc_path, "Albumnaam", "Album name")


def extract_location(desc_path: Path) -> str | None:
    return _read_description_field(desc_path, "Locatie", "Location")


def extract_date(desc_path: Path) -> str | None:
    """Extract the date from description.txt (e.g., 'Juni 1984')."""
    return _read_description_field(desc_path, "Datum", "Date")


# ── Enhanced folder lookup ───────────────────────────────────────────────────

def find_enhanced_folder(source_folder: Path, enhanced_root: Path | None) -> Path | None:
    """Return the enhanced output folder for a source folder.

    Uses Albumnaam from description.txt as the subfolder name under enhanced_root.
    """
    desc = source_folder / "description.txt"
    if not desc.exists():
        return None
    album = extract_album_name(desc)
    if not album:
        return None
    if enhanced_root:
        candidate = enhanced_root / album
        return candidate if candidate.is_dir() else None
    return None


# ── Date parsing ───────────────────────────────────────────────────────────────

def parse_date(date_str: str) -> str | None:
    """Parse a date string into 'YYYY-MM-DD'. Supports:
    - 'Juni 1984' → '1984-06-01'
    - 'juni 1984' → '1984-06-01'
    - '1984' → '1984-01-01'
    - '1984-06' → '1984-06-01'
    - '1984-06-01' → '1984-06-01'
    - '03-01-1991' → '1991-01-03'
    - '29 september 1970' → '1970-09-29'
    - '20 maart 1998' → '1998-03-20'
    - '13 mei 1991' → '1991-05-13'
    - '6 september 1985' → '1985-09-06'
    """
    month_map = {
        "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
        "juli": 7, "augustus": 8, "september": 9, "oktober": 10, "november": 11, "december": 12,
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    }
    
    date_str = date_str.strip().lower()
    
    # Try to match "DD-MM-YYYY" (e.g., "03-01-1991")
    match = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"
    
    # Try to match "YYYY-MM-DD" (e.g., "1991-01-03")
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"
    
    # Try to match patterns like "29 september 1970" or "20 maart 1998"
    match = re.match(r"^(\d{1,2})\s+([a-z]+)\s+(\d{4})$", date_str)
    if match:
        day, month_name, year = match.groups()
        month = month_map.get(month_name)
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"
    
    # Try to match patterns like "Juni 1984" or "juni 1984"
    match = re.match(r"^([a-z]+)\s+(\d{4})$", date_str)
    if match:
        month_name, year = match.groups()
        month = month_map.get(month_name)
        if month:
            return f"{year}-{month:02d}-01"
    
    # Try to match "YYYY" (year only)
    match = re.match(r"^(\d{4})$", date_str)
    if match:
        year = match.group(1)
        return f"{year}-01-01"
    
    # Try to match "YYYY-MM" (year and month)
    match = re.match(r"^(\d{4})-(\d{2})$", date_str)
    if match:
        year, month = match.groups()
        return f"{year}-{month}-01"
    
    return None


# ── Geocoding ────────────────────────────────────────────────────────────────

def geocode(location_str: str) -> dict | None:
    try:
        from src.picture_analyzer.geo.nominatim import NominatimGeocoder
        result = NominatimGeocoder().geocode(location_str)
        if result:
            return {
                "latitude": result.latitude,
                "longitude": result.longitude,
                "display_name": result.display_name or location_str,
            }
    except Exception as exc:
        print(f"  ⚠ Geocoding error: {exc}", file=sys.stderr)
    return None


def parse_location_parts(location_str: str) -> dict:
    """Split 'city, region, country' into location_detection fields."""
    if "/" in location_str:
        country = " / ".join(p.strip() for p in location_str.split("/") if p.strip())
        return {"country": country, "region": "", "city_or_area": "", "confidence": 100,
                "reasoning": "Set from description.txt"}
    parts = [p.strip() for p in location_str.split(",") if p.strip()]
    result = {"country": "", "region": "", "city_or_area": "", "confidence": 100,
              "reasoning": "Set from description.txt"}
    if len(parts) >= 1:
        result["city_or_area"] = parts[0]
    if len(parts) >= 2:
        result["region"] = parts[1]
    if len(parts) >= 3:
        result["country"] = parts[2]
    return result


# ── EXIF GPS writing ─────────────────────────────────────────────────────────

def write_gps_and_date_to_image(image_path: Path, lat: float, lon: float, display_name: str, date_taken: str | None) -> bool:
    if not PIEXIF_AVAILABLE or not PIL_AVAILABLE:
        print("⚠ piexif or Pillow not available. EXIF writing disabled.", file=sys.stderr)
        return False
    
    try:
        exif_dict = piexif.load(str(image_path))
        if "GPS" not in exif_dict:
            exif_dict["GPS"] = {}

        def to_dms(decimal: float):
            d = int(abs(decimal))
            m = int((abs(decimal) - d) * 60)
            s = round(((abs(decimal) - d) * 60 - m) * 60 * 100)
            return ((d, 1), (m, 1), (s, 100))

        exif_dict["GPS"][piexif.GPSIFD.GPSLatitude] = to_dms(lat)
        exif_dict["GPS"][piexif.GPSIFD.GPSLatitudeRef] = b"N" if lat >= 0 else b"S"
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitude] = to_dms(lon)
        exif_dict["GPS"][piexif.GPSIFD.GPSLongitudeRef] = b"E" if lon >= 0 else b"W"

        # Add date taken to EXIF if provided
        if date_taken and "Exif" not in exif_dict:
            exif_dict["Exif"] = {}
        if date_taken:
            # Handle both date-only and full timestamp formats
            if len(date_taken) == 10:  # e.g., "1984-06-01"
                exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = f"{date_taken} 00:00:00".encode("utf-8")
            else:  # e.g., "1984-06-01 00:00:00"
                exif_dict["Exif"][piexif.ExifIFD.DateTimeOriginal] = date_taken.encode("utf-8")

        exif_bytes = piexif.dump(exif_dict)
        img = Image.open(str(image_path))
        img.save(str(image_path), exif=exif_bytes, quality=95)
        return True
    except Exception as exc:
        print(f"    ⚠ EXIF write failed for {image_path.name}: {exc}", file=sys.stderr)
        return False


# ── Folder processing ────────────────────────────────────────────────────────

IMAGE_SUFFIXES = {".jpg", ".jpeg"}


def process_source_folder(
    source_folder: Path,
    location_override: str | None,
    probe: bool,
    enhanced_root: Path | None,
) -> bool:
    """Process one source folder: read description.txt, find enhanced dir, update it.

    Returns True if location was successfully applied.
    """
    print(f"\n📁 {source_folder.name}")

    desc = source_folder / "description.txt"
    if not desc.exists() and not location_override:
        print(f"  ⚠ No description.txt — skipping")
        return False

    # 1. Resolve location string
    if location_override:
        location_str = location_override
        print(f"  Location (override): {location_str}")
    else:
        location_str = extract_location(desc)
        if not location_str:
            print("  ⚠ No 'Locatie:' / 'Location:' in description.txt — skipping")
            return False
        print(f"  Location: {location_str}")

    # 2. Extract and parse date
    date_str = extract_date(desc)
    parsed_date = None
    if date_str:
        parsed_date = parse_date(date_str)
        if parsed_date:
            print(f"  Date: {date_str} → {parsed_date}")
        else:
            print(f"  ⚠ Could not parse date: {date_str}")
    else:
        print("  ⚠ No 'Date:' in description.txt")

    # 3. Find enhanced folder
    enhanced_folder = find_enhanced_folder(source_folder, enhanced_root)
    if not enhanced_folder:
        album = extract_album_name(desc) if desc.exists() else None
        if album:
            print(f"  ⚠ Enhanced folder not found: {enhanced_root}/{album} — skipping")
        else:
            print(f"  ⚠ No Albumnaam in description.txt — cannot find enhanced folder — skipping")
        return False
    print(f"  Enhanced: {enhanced_folder}")

    # 3. Geocode
    coords = geocode(location_str)
    if coords:
        print(f"  ✓ GPS: {coords['latitude']:.6f}, {coords['longitude']:.6f}")
        print(f"    ({coords['display_name']})")
    else:
        print("  ⚠ Could not geocode location (too vague or not found)")

    if probe:
        print("  [probe — no changes made]")
        return bool(coords)

    # 4. Update JSONs and images in enhanced folder
    json_files = sorted(enhanced_folder.glob("*_analyzed.json"))
    if not json_files:
        print(f"  ⚠ No *_analyzed.json files in {enhanced_folder}")
        return False

    location_det = parse_location_parts(location_str)

    for json_path in json_files:
        # Initialize the timestamp for the first image in EACH folder
        if parsed_date:
            from datetime import datetime, timedelta
            try:
                # Parse the date into a datetime object (e.g., "1984-06-01" → "1984-06-01 00:00:00")
                timestamp = datetime.strptime(parsed_date, "%Y-%m-%d")
            except ValueError:
                # Fallback to the original date if parsing fails
                timestamp = datetime.strptime("1970-01-01", "%Y-%m-%d")
        else:
            timestamp = datetime.strptime("1970-01-01", "%Y-%m-%d")
        stem = json_path.stem.replace("_analyzed", "")
        data = json.loads(json_path.read_text(encoding="utf-8"))
        data["location_detection"] = location_det
        if coords:
            data["gps_coordinates"] = coords
        elif "gps_coordinates" in data:
            del data["gps_coordinates"]
        
        # Set the incremented timestamp for this image
        incremented_timestamp = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        data["date_taken"] = incremented_timestamp
        if "date_taken" not in data:
            del data["date_taken"]  # This line is redundant, removing it
        
        json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  ✓ JSON: {json_path.name}")

        if coords:
            for suffix in IMAGE_SUFFIXES:
                for pattern in (f"{stem}_analyzed", f"{stem}_enhanced", f"{stem}_restored", stem):
                    img = enhanced_folder / (pattern + suffix)
                    if img.exists():
                        if write_gps_and_date_to_image(img, coords["latitude"], coords["longitude"],
                                                       coords["display_name"], incremented_timestamp):
                            print(f"    ✓ GPS and Date: {img.name}")
        
        # Increment the timestamp by 1 second for the next image
        timestamp += timedelta(seconds=1)

    return True


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Update location/GPS in JSON and images from description.txt",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "folder",
        help="Source folder containing description.txt (or source root when --recursive)",
    )
    parser.add_argument("--probe", action="store_true",
                        help="Show what would happen without making any changes")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Process all subfolders that contain description.txt")
    parser.add_argument("--location", "-l", default=None,
                        help="Override location string (e.g. 'Pruggern, Steiermark, Austria')")
    parser.add_argument("--enhanced-root", "-e", default=None,
                        help="Root of enhanced output folders. Defaults to enhanced_root from config.yaml.")
    args = parser.parse_args()

    root = Path(args.folder)
    if not root.is_dir():
        print(f"Error: not a directory: {root}", file=sys.stderr)
        sys.exit(1)

    enhanced_root = Path(args.enhanced_root) if args.enhanced_root else _default_enhanced_root()
    print(f"Enhanced root: {enhanced_root or '(not configured)'}")

    if args.recursive:
        source_folders = sorted(f.parent for f in root.rglob("description.txt"))
        if not source_folders:
            print(f"No description.txt files found under {root}", file=sys.stderr)
            sys.exit(1)
        print(f"Found {len(source_folders)} source folder(s)")
        updated = sum(
            1 for f in source_folders
            if process_source_folder(f, args.location, args.probe, enhanced_root)
        )
        print(f"\n{'=' * 50}")
        print(f"Done: {updated}/{len(source_folders)} folders updated")
    else:
        process_source_folder(root, args.location, args.probe, enhanced_root)


if __name__ == "__main__":
    main()

