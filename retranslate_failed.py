#!/usr/bin/env python3
"""Re-translate English (untranslated) metadata fields in analyzed JSON files.

Scans ~/enhanced for *_analyzed.json files, detects which metadata fields are
still in English (translation failed previously), and re-translates only those
fields using the project's improved translator (with caching, backoff, throttling).

Usage:
    python3 retranslate_failed.py              # re-translate in place
    python3 retranslate_failed.py --dry-run     # just list what would change
    python3 retranslate_failed.py --limit 10    # only process 10 files (testing)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

# --- Import the project's translator -----------------------------------------
PROJECT_SRC = Path(__file__).resolve().parent / "src"
sys.path.insert(0, str(PROJECT_SRC))

from picture_analyzer.utils.translator import (  # noqa: E402
    _translate_with_retry,
    _TRANSLATION_CACHE,
)
from picture_analyzer.metadata.exif_writer import ExifWriter  # noqa: E402
from deep_translator import GoogleTranslator  # noqa: E402

# --- English detection heuristic (same as check_translations.py) -------------

ENGLISH_MARKERS = re.compile(
    r"\b("
    r"the|and|with|for|from|that|this|which|while|where|when|what|"
    r"there|their|they|them|these|those|then|than|"
    r"man|woman|people|person|child|children|boy|girl|"
    r"building|house|tree|street|car|fence|window|door|"
    r"indoor|outdoor|inside|outside|"
    r"wearing|standing|sitting|holding|walking|looking|"
    r"background|foreground|"
    r"appears|seems|likely|probably|"
    r"black|white|red|green|blue|yellow|brown|gray|grey|"
    r"large|small|young|old|"
    r"photo|photograph|image|picture|"
    r"vintage|formal|casual|"
    r"can|not|but|are|was|were|been|have|has|had|"
    r"could|would|should|"
    r"two|three|four|five|"
    r"front|back|left|right|side|"
    r"visible|seen|"
    r"setting|scene|environment|"
    r"clothing|clothes|dress|suit|hat|"
    r"grass|sky|cloud|ground|wall|roof|"
    r"wooden|metal|plastic|brick|stone|"
    r"quality|lighting|contrast|sharpness|"
    r"underexposed|overexposed|"
    r"shadows|highlights|brightness|"
    r"slightly|appears|"
    r"monochrome|grayscale|sepia|"
    r"studio|portrait|"
    r"film|grain|scan|"
    r"creases|tears|scratches|dust|"
    r"natural|artificial|"
    r"day|night|morning|evening|afternoon|"
    r"summer|winter|spring|autumn|fall"
    r")\b",
    re.IGNORECASE,
)

DUTCH_MARKERS = re.compile(
    r"\b("
    r"een|en|met|van|het|de|dat|deze|die|"
    r"vrouw|kind|kinderen|jongen|meisje|"
    r"gebouw|huis|boom|straat|auto|hek|raam|deur|"
    r"binnen|buiten|"
    r"draagt|staat|zit|houdt|loopt|kijkt|"
    r"achtergrond|voorgrond|"
    r"lijkt|waarschijnlijk|"
    r"zwart|wit|rood|groen|blauw|geel|bruin|grijs|"
    r"groot|klein|jong|oud|"
    r"foto|afbeelding|plaatje|"
    r"vintage|formeel|casual|"
    r"kan|niet|maar|zijn|was|waren|geweest|hebben|heeft|had|"
    r"zou|moest|"
    r"twee|drie|vier|vijf|"
    r"voor|achter|links|rechts|kant|"
    r"zichtbaar|gezien|"
    r"omgeving|"
    r"kleding|kleren|jurk|pak|hoed|"
    r"gras|lucht|wolk|grond|muur|dak|"
    r"houten|metalen|plastic|baksteen|steen|"
    r"kwaliteit|belichting|contrast|scherpte|"
    r"onderbelicht|overbelicht|"
    r"schaduwen|hooglichten|helderheid|"
    r"licht|lijkt|"
    r"monochroom|grijswaarden|sepia|"
    r"studio|portret|"
    r"film|korrel|scan|"
    r"vouwen|scheuren|krassen|stof|"
    r"natuurlijk|kunstmatig|"
    r"dag|nacht|ochtend|avond|middag|"
    r"zomer|winter|lente|herfst"
    r")\b",
    re.IGNORECASE,
)


def is_english(text: str) -> bool:
    """Heuristic: text is likely English if it has English markers and no Dutch markers."""
    if not text or not text.strip():
        return False
    en_hits = len(ENGLISH_MARKERS.findall(text))
    nl_hits = len(DUTCH_MARKERS.findall(text))
    return en_hits >= 2 and en_hits > nl_hits


# --- Re-translation logic ----------------------------------------------------

TARGET_LANG = "nl"


def retranslate_metadata_fields(metadata: dict, translator: GoogleTranslator) -> tuple[dict, int]:
    """Re-translate only the English fields in a metadata dict.

    Returns (updated_metadata, count_of_fields_translated).
    """
    updated = dict(metadata)
    count = 0

    for key, value in metadata.items():
        if not value:
            continue

        if isinstance(value, str):
            if is_english(value):
                try:
                    translated = _translate_with_retry(translator, value, TARGET_LANG)
                    updated[key] = translated
                    count += 1
                except RuntimeError:
                    pass  # Still failing — skip, keep original
        elif isinstance(value, list):
            new_list = []
            changed = False
            for item in value:
                if isinstance(item, str) and is_english(item):
                    try:
                        translated = _translate_with_retry(translator, item, TARGET_LANG)
                        new_list.append(translated)
                        count += 1
                        changed = True
                    except RuntimeError:
                        new_list.append(item)  # Keep original on failure
                else:
                    new_list.append(item)
            if changed:
                updated[key] = new_list

    return updated, count


def retranslate_location_fields(
    location: dict, translator: GoogleTranslator
) -> tuple[dict, int]:
    """Re-translate location_detection fields that are English descriptions."""
    updated = dict(location)
    count = 0

    for field in ["country", "region", "city_or_area"]:
        val = updated.get(field)
        if isinstance(val, str) and val and is_english(val):
            try:
                translated = _translate_with_retry(translator, val, TARGET_LANG)
                updated[field] = translated
                count += 1
            except RuntimeError:
                pass

    return updated, count


def process_file(
    path: Path,
    translator: GoogleTranslator,
    exif_writer: ExifWriter,
    dry_run: bool,
) -> tuple[int, int]:
    """Process one JSON file.

    Returns (fields_translated, images_updated).
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  ✗ Parse error in {path.name}: {e}", file=sys.stderr)
        return 0, 0

    total_translated = 0

    # Re-translate metadata fields
    metadata = data.get("metadata", {})
    if isinstance(metadata, dict) and metadata:
        new_metadata, count = retranslate_metadata_fields(metadata, translator)
        total_translated += count
        if not dry_run and count > 0:
            data["metadata"] = new_metadata

    # Re-translate location_detection fields
    location = data.get("location_detection", {})
    if isinstance(location, dict) and location:
        new_location, count = retranslate_location_fields(location, translator)
        total_translated += count
        if not dry_run and count > 0:
            data["location_detection"] = new_location

    # Write JSON back if changes were made
    images_updated = 0
    if not dry_run and total_translated > 0:
        path.write_text(
            json.dumps(data, indent=4, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        # Update EXIF metadata in ALL image variants that share the same
        # base name: _analyzed.jpg, _enhanced.jpg, _restored.jpg,
        # _preserved.jpg, _aged.jpg, _faded.jpg, _cast.jpg, _flooded.jpg, etc.
        base_name = path.stem.removesuffix("_analyzed")
        parent = path.parent
        for jpg_path in parent.glob(f"{base_name}*.jpg"):
            try:
                exif_writer.write_from_dict(jpg_path, jpg_path, data)
                images_updated += 1
            except Exception as e:
                print(
                    f"  ⚠ EXIF update failed for {jpg_path.name}: {e}",
                    file=sys.stderr,
                )

    return total_translated, images_updated


def main():
    parser = argparse.ArgumentParser(description="Re-translate failed metadata fields")
    parser.add_argument(
        "--root",
        default=str(Path.home() / "enhanced"),
        help="Root directory to scan (default: ~/enhanced)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be re-translated, don't modify files",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process N files (0 = no limit, for testing use --limit 5)",
    )
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        print(f"Error: {root} does not exist", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning {root} for *_analyzed.json files...")
    all_jsons = sorted(root.rglob("*_analyzed.json"))
    print(f"Found {len(all_jsons)} JSON files total.")

    # Pre-filter: only keep files that have English metadata
    print("Filtering for files with untranslated (English) metadata...")
    files_to_process = []
    for path in all_jsons:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        metadata = data.get("metadata", {})
        if not isinstance(metadata, dict):
            continue
        has_english = any(
            (isinstance(v, str) and is_english(v))
            or (isinstance(v, list) and any(isinstance(i, str) and is_english(i) for i in v))
            for v in metadata.values()
        )
        # Also check location_detection
        location = data.get("location_detection", {})
        if isinstance(location, dict) and not has_english:
            has_english = any(
                isinstance(location.get(f), str) and is_english(location.get(f, ""))
                for f in ["country", "region", "city_or_area"]
            )
        if has_english:
            files_to_process.append(path)

    print(f"Found {len(files_to_process)} files with untranslated metadata.")

    if args.limit > 0:
        files_to_process = files_to_process[: args.limit]
        print(f"Limited to {len(files_to_process)} files for processing.")

    if not files_to_process:
        print("Nothing to do — all files are already translated.")
        return

    mode = "DRY RUN" if args.dry_run else "TRANSLATING"
    print(f"\n{mode}: {len(files_to_process)} files...\n")

    translator = GoogleTranslator(source="en", target=TARGET_LANG)
    exif_writer = ExifWriter(language=TARGET_LANG)
    total_fields = 0
    total_files_changed = 0
    total_images_updated = 0
    errors = 0
    start_time = time.time()

    for i, path in enumerate(files_to_process, 1):
        rel = path.relative_to(root)
        try:
            fields_done, imgs_done = process_file(
                path, translator, exif_writer, args.dry_run
            )
        except Exception as e:
            print(f"  [{i}/{len(files_to_process)}] ✗ {rel}: ERROR {e}", file=sys.stderr)
            errors += 1
            continue

        if fields_done > 0:
            total_fields += fields_done
            total_files_changed += 1
            total_images_updated += imgs_done
            exif_tag = f" +EXIF({imgs_done} imgs)" if imgs_done else ""
            print(f"  [{i}/{len(files_to_process)}] ✓ {rel}: {fields_done} fields{exif_tag}")
        else:
            print(f"  [{i}/{len(files_to_process)}] · {rel}: no English fields found (skipped)")

        # Progress summary every 50 files
        if i % 50 == 0:
            elapsed = time.time() - start_time
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(files_to_process) - i) / rate if rate > 0 else 0
            cache_size = len(_TRANSLATION_CACHE)
            print(
                f"  --- Progress: {i}/{len(files_to_process)} "
                f"({i/len(files_to_process)*100:.0f}%) "
                f"| {rate:.1f} files/s | ETA: {eta:.0f}s "
                f"| Cache: {cache_size} entries"
            )

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Done in {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  Files processed:   {len(files_to_process)}")
    print(f"  Files changed:     {total_files_changed}")
    print(f"  Fields translated: {total_fields}")
    print(f"  Images updated:    {total_images_updated}")
    print(f"  Errors:            {errors}")
    print(f"  Cache entries:     {len(_TRANSLATION_CACHE)}")
    if args.dry_run:
        print(f"\n(Dry run — no files were modified. Re-run without --dry-run to apply.)")


if __name__ == "__main__":
    main()
