"""Click-based CLI for picture-analyzer.

Replaces the legacy argparse CLI (``cli.py``) with a modern Click
interface.  All commands use the new typed components from Phase 2
with transparent fallback to legacy modules when needed.

Entry point registered in ``pyproject.toml``::

    [project.scripts]
    picture-analyzer = "picture_analyzer.cli.app:main"
"""
from __future__ import annotations

import gc
import json
import mimetypes
import re
import shutil
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import click

from ..analyzers import create_analyzer
from ..analyzers.openai import OpenAIAnalyzer
from ..config.defaults import DEFAULT_SUPPORTED_FORMATS
from ..config.settings import get_settings
from ..core.models import AnalysisContext, ImageData
from ..description import (
    extract_date,
    extract_location,
    parse_date,
    parse_location_parts,
)
from ..utils.translator import translate_analysis_dict


# ── Helpers ──────────────────────────────────────────────────────────


def _inject_project_root() -> Path:
    """Add the project root to *sys.path* (for legacy imports)."""
    project_root = Path(__file__).resolve().parent.parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    return project_root


def _get_legacy_modules():
    """Import legacy modules, returning a 5-tuple.

    Returns
    -------
    tuple
        (PictureAnalyzer, SmartEnhancer, SlideRestoration,
         MetadataManager, ReportGenerator)
    """
    _inject_project_root()

    try:
        from picture_analyzer_legacy import PictureAnalyzer
        from picture_enhancer import SmartEnhancer
        from slide_restoration import SlideRestoration
        from metadata_manager import MetadataManager
        from report_generator import ReportGenerator

        return PictureAnalyzer, SmartEnhancer, SlideRestoration, MetadataManager, ReportGenerator
    except ImportError as exc:
        raise click.ClickException(
            f"Could not import legacy modules (run from project root): {exc}"
        ) from exc


PROFILE_CHOICES = [
    "auto", "faded", "color_cast", "red_cast",
    "yellow_cast", "aged", "well_preserved",
]

# Albumnaam must match: 4-digit year, optional -MM month, optional -DD day, then a space and title text
_ALBUM_NAME_RE = re.compile(r'^\d{4}(-\d{2}(-\d{2})?)? .+')


def _default_output_from_description(directory: Path) -> str | None:
    """Derive a default output path from Albumnaam in description.txt.

    Returns ``enhanced_root/album_name`` if:
    - ``description.txt`` exists and is non-empty
    - it contains an ``Albumnaam:`` line
    - the album name matches ``<year>[-<month>] <title>``
    - ``output.enhanced_root`` is set in config

    Emits a Click warning and returns None if any check fails.
    """
    desc_path = directory / "description.txt"
    if not desc_path.exists():
        return None
    text = desc_path.read_text(encoding="utf-8").strip()
    if not text:
        click.echo("  ⚠ description.txt is empty — cannot derive output directory", err=True)
        return None
    album: str | None = None
    for line in text.splitlines():
        if line.lower().startswith("albumnaam:"):
            album = line.split(":", 1)[1].strip()
            break
    if not album:
        click.echo("  ⚠ No Albumnaam: line in description.txt — cannot derive output directory", err=True)
        return None
    if not _ALBUM_NAME_RE.match(album):
        click.echo(
            f"  ⚠ Albumnaam '{album}' does not match <year>[-<month>] <title> — cannot derive output directory",
            err=True,
        )
        return None
    settings = get_settings()
    root = settings.output.enhanced_root
    if not root:
        click.echo(
            "  ⚠ output.enhanced_root not configured — cannot derive output directory from Albumnaam",
            err=True,
        )
        return None
    return str(Path(root) / album)


def _fallback_output(name: str) -> str:
    """Return ``enhanced_root/<name>`` when Albumnaam derivation fails.

    Falls back to ``./output`` if ``output.enhanced_root`` is not configured.
    """
    settings = get_settings()
    root = settings.output.enhanced_root
    if root:
        return str(Path(root) / name)
    return "output"


def _resolve_profiles(restore_slide: str, analysis: dict) -> list[str]:
    """Determine which slide-restoration profiles to apply.

    Unknown/hallucinated profile names from the AI are dropped (with a
    warning) instead of being written into output filenames — the audit
    found files like ``_restored_foggy.jpg`` from invented names.
    """
    if restore_slide != "auto":
        return [restore_slide]

    # Valid profile names (kept in sync with slide_restoration.py / YAML)
    valid = {"faded", "color_cast", "red_cast", "yellow_cast", "aged", "well_preserved"}

    slide_profiles = analysis.get("slide_profiles", [])
    if slide_profiles:
        try:
            profiles = [
                p["profile"]
                for p in slide_profiles
                if isinstance(p, dict) and "profile" in p
            ]
        except (KeyError, TypeError):
            profiles = []
        if profiles:
            known = [p for p in profiles if p in valid]
            dropped = [p for p in profiles if p not in valid]
            if dropped:
                click.echo(
                    f"  ⚠ Ignoring unknown slide profile(s) from analysis: "
                    f"{', '.join(dropped)}"
                )
            if known:
                return known
            click.echo("  ⚠ No valid profiles left — falling back to auto-detect")
    return ["auto"]


def _restore_from_analysis(
    SlideRestoration,
    MetadataManager,
    *,
    source_path: str,
    analysis: dict,
    restore_slide: str,
    output_dir: str,
    image_stem: str,
) -> None:
    """Run slide restoration for one image (shared by single + batch)."""
    profiles = _resolve_profiles(restore_slide, analysis)
    if len(profiles) > 1:
        click.echo(f"  → Suggested profiles: {', '.join(profiles)}")

    for profile in profiles:
        if len(profiles) > 1:
            restored_path = str(Path(output_dir) / f"{image_stem}_restored_{profile}.jpg")
        else:
            restored_path = str(Path(output_dir) / f"{image_stem}_restored.jpg")

        if profile == "auto":
            SlideRestoration.auto_restore_slide(source_path, analysis, restored_path)
        else:
            SlideRestoration.restore_slide(
                source_path, profile=profile, output_path=restored_path,
            )

        if Path(restored_path).exists():
            MetadataManager().copy_exif(source_path, restored_path, restored_path)


def _build_runtime_provider(provider: str | None) -> str:
    settings = get_settings()
    return (provider or settings.analyzer_provider).lower()


def _build_analyzer(provider: str | None = None):
    settings = get_settings()
    selected = _build_runtime_provider(provider)

    return create_analyzer(
        provider=selected,
        openai_api_key=settings.openai.api_key.get_secret_value(),
        openai_model=settings.openai.model,
        ollama_model=settings.ollama.model,
        ollama_host=settings.ollama.host,
        max_tokens=settings.openai.max_tokens,
    )


def _analyze_with_provider(
    image_path: Path,
    provider: str | None = None,
    pipeline_mode: str | None = None,
    pipeline=None,
    partial=None,
    only_steps: list[str] | None = None,
    detect_location: bool | None = None,
):
    settings = get_settings()
    effective_mode = pipeline_mode or settings.pipeline.mode

    # Per-image description takes priority over the folder-wide description.txt
    per_image_desc = image_path.parent / (image_path.stem + ".txt")
    folder_desc = image_path.parent / "description.txt"
    desc_file = per_image_desc if per_image_desc.is_file() else (folder_desc if folder_desc.is_file() else None)
    description_text = desc_file.read_text(encoding="utf-8").strip() if desc_file else None
    context = AnalysisContext(
        language=settings.metadata.language,
        detect_slide_profiles=settings.prompt.detect_slide_profiles,
        recommend_enhancements=settings.prompt.recommend_enhancements,
        detect_location=settings.prompt.detect_location if detect_location is None else detect_location,
        custom_instructions=settings.prompt.custom_instructions,
        description_text=description_text,
    )
    mime_type, _ = mimetypes.guess_type(str(image_path))
    image = ImageData(path=image_path, mime_type=mime_type or "image/jpeg")

    if effective_mode == "stepped":
        from ..pipeline import build_pipeline
        active_pipeline = pipeline or build_pipeline(settings)
        return active_pipeline.run(image, context, partial=partial, only_steps=only_steps)

    analyzer = _build_analyzer(provider)
    result = analyzer.analyze(image, context)

    # ── Geocoding: resolve GPS coordinates from AI-detected location ──
    if result.location and settings.geo.provider != "none":
        try:
            from ..geo.nominatim import NominatimGeocoder
            geocoder = NominatimGeocoder(
                cache_path=settings.geo.cache_path,
                confidence_threshold=settings.geo.confidence_threshold,
                user_agent=settings.geo.user_agent,
                timeout=settings.geo.timeout_seconds,
                max_results=settings.geo.max_results,
            )
            enriched_location = geocoder.geocode_location_info(result.location)
            if enriched_location.coordinates:
                result = result.model_copy(update={"location": enriched_location})
                # Propagate GPS into raw_response so legacy metadata writers pick it up
                geo = enriched_location.coordinates
                raw = dict(result.raw_response)
                raw["gps_coordinates"] = {
                    "latitude": geo.latitude,
                    "longitude": geo.longitude,
                    "display_name": geo.display_name,
                }
                result = result.model_copy(update={"raw_response": raw})
        except Exception as exc:
            click.echo(f"  ⚠ Geocoding failed: {exc}", err=True)

    return result


# ── description.txt ground-truth (location/date) ─────────────────────


def _geocode_location_str(location_str: str, settings) -> dict | None:
    """Geocode a description.txt location string to {lat, lon, display_name}.

    Uses the configured geocoder with confidence_threshold=0 because the
    location comes from description.txt (ground truth, not an AI guess).
    Returns None if geocoding is disabled or the location cannot be resolved.
    """
    if settings.geo.provider == "none":
        return None
    try:
        from ..geo.nominatim import NominatimGeocoder
        geocoder = NominatimGeocoder(
            cache_path=settings.geo.cache_path,
            confidence_threshold=0,
            user_agent=settings.geo.user_agent,
            timeout=settings.geo.timeout_seconds,
            max_results=settings.geo.max_results,
        )
        result = geocoder.geocode(location_str)
        if result:
            return {
                "latitude": result.latitude,
                "longitude": result.longitude,
                "display_name": result.display_name or location_str,
            }
    except Exception as exc:
        click.echo(f"  ⚠ Geocoding error: {exc}", err=True)
    return None


def _load_description_ground_truth(directory: Path, settings) -> dict:
    """Read location/date ground truth from a folder's description.txt.

    Returns a dict describing the outcome:

    - ``{"status": "absent"}`` — no description.txt; the batch should proceed
      with the normal LLM flow (no override, no skip).
    - ``{"status": "failed", "reason": ...}`` — description.txt exists but
      location/date could not be extracted/parsed; the folder should be
      skipped after reporting the failure.
    - ``{"status": "ok", ...}`` — extraction succeeded; the returned fields
      (``location_str``, ``parsed_date``, ``coords``, ``description_text``)
      are used to override the LLM analysis with ground truth.
    """
    desc_path = directory / "description.txt"
    if not desc_path.is_file():
        return {"status": "absent"}

    description_text = desc_path.read_text(encoding="utf-8").strip()
    if not description_text:
        return {"status": "failed", "reason": "description.txt is empty"}

    location_str = extract_location(desc_path)
    if not location_str:
        return {
            "status": "failed",
            "reason": "no 'Locatie:'/'Location:' line in description.txt",
        }

    date_str = extract_date(desc_path)
    if not date_str:
        return {
            "status": "failed",
            "reason": "no 'Datum:'/'Date:' line in description.txt",
        }

    parsed_date = parse_date(date_str)
    if not parsed_date:
        return {"status": "failed", "reason": f"could not parse date '{date_str}'"}

    coords = _geocode_location_str(location_str, settings)
    return {
        "status": "ok",
        "description_text": description_text,
        "location_str": location_str,
        "date_str": date_str,
        "parsed_date": parsed_date,
        "coords": coords,
    }


def _read_image_exif_date(image_path: Path) -> datetime | None:
    """Return the DateTimeOriginal from an image's EXIF, or None.

    Uses piexif when available; silently returns None on any error
    (missing tag, corrupt EXIF, piexif not installed, etc.).
    """
    try:
        import piexif
        raw = piexif.load(str(image_path))
        tag = raw.get("Exif", {}).get(piexif.ExifIFD.DateTimeOriginal)
        if not tag:
            tag = raw.get("0th", {}).get(piexif.ImageIFD.DateTime)
        if isinstance(tag, bytes):
            tag = tag.decode("utf-8", errors="ignore")
        if tag:
            return datetime.strptime(tag.strip(), "%Y:%m:%d %H:%M:%S")
    except Exception:
        pass
    return None


def _next_sequential_timestamp(output_dir: Path, parsed_date: str, own_json: Path | None = None) -> datetime:
    """Return the timestamp to use for a single-image processing run.

    Batch mode assigns each image date + N seconds. For single-image runs:

    1. If the image's OWN previous JSON exists with a same-day ``date_taken``,
       reuse it (re-processing must not move the photo in the Immich timeline).
    2. Otherwise continue from the highest same-day ``date_taken`` in the
       folder (+1s) so the sequence doesn't reset or collide.
    """
    base = datetime.strptime(parsed_date, "%Y-%m-%d")

    def _read_date(jf: Path) -> datetime | None:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            return datetime.strptime(str(data.get("date_taken", "")), "%Y-%m-%d %H:%M:%S")
        except (ValueError, OSError, json.JSONDecodeError):
            return None

    if own_json is not None and own_json.is_file():
        own_dt = _read_date(own_json)
        if own_dt is not None and own_dt.date() == base.date():
            return own_dt

    max_existing = _max_existing_date_taken(str(output_dir), base)
    if max_existing is not None:
        return max_existing + timedelta(seconds=1)
    return base


def _exif_date_within_months(exif_dt: datetime, base_dt: datetime, months: int = 6) -> bool:
    """Return True if *exif_dt* is within *months* calendar months of *base_dt*."""
    from dateutil.relativedelta import relativedelta  # type: ignore[import]
    window = relativedelta(months=months)
    return (base_dt - window) <= exif_dt <= (base_dt + window)


def _apply_description_ground_truth(
    analysis: dict, ground_truth: dict, timestamp: datetime
) -> None:
    """Apply description.txt location/date/GPS to an analysis dict.

    The description.txt location is GROUND TRUTH and wins by default. The
    LLM's location is only kept when it identified a specific, recognizable
    landmark (e.g. the Brandenburg Gate) with really high confidence — a
    generic city/area guess never overrides the description, even at high
    confidence (the LLM confidently guessed the wrong province for 'Gouda').

    Date from description.txt is always applied; GPS follows the location
    that won (landmark geocoding if the LLM won, description coords else).
    """
    # Check if the LLM identified a specific landmark with high confidence
    loc = analysis.get("location_detection", {})
    if isinstance(loc, dict):
        llm_confidence = int(loc.get("confidence", 0) or 0)
        llm_landmark = (loc.get("landmark_name") or "").strip()
    else:
        llm_confidence = 0
        llm_landmark = ""

    # The LLM only wins with a named landmark at very high confidence —
    # AND the landmark must be an INDEPENDENT visual identification: if the
    # landmark text is (partly) copied from the description.txt context, it
    # is not a recognition and the description wins. E.g. description says
    # "Berlin" and the LLM sees the Brandenburger Tor → LLM wins; description
    # says "Han Hollanderweg, Gouda" and the LLM parrots "Han Hollanderweg"
    # back as landmark → description wins.
    LANDMARK_CONFIDENCE = 85
    description_text = (ground_truth.get("description_text") or "").lower()
    landmark_is_independent = bool(llm_landmark) and not any(
        word in description_text
        for word in llm_landmark.lower().replace("(", " ").replace(")", " ").split()
        if len(word) >= 4  # ignore short/stop words
    )
    llm_won = landmark_is_independent and llm_confidence >= LANDMARK_CONFIDENCE

    if not llm_won:
        analysis["location_detection"] = parse_location_parts(ground_truth["location_str"])

    # GPS: keep the LLM's landmark geocoding only when the LLM won;
    # otherwise use the description.txt coordinates (or drop wrong ones).
    coords = ground_truth.get("coords")
    if coords:
        if not llm_won or not analysis.get("gps_coordinates"):
            analysis["gps_coordinates"] = coords
    elif "gps_coordinates" in analysis and not llm_won:
        del analysis["gps_coordinates"]
    description_text = ground_truth.get("description_text")
    if description_text:
        analysis["source_description"] = description_text
    analysis["date_taken"] = timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _max_existing_date_taken(output_dir: str, base: datetime) -> datetime | None:
    """Return the max ``date_taken`` in output_dir JSONs on the same day as base.

    Used to continue the per-image timestamp sequence on a ``--skip-existing``
    resume so newly-processed images don't collide with already-stored
    ``DateTimeOriginal`` values.  Only same-day timestamps are considered so
    older LLM-set dates on other days don't skew the sequence.
    """
    max_ts: datetime | None = None
    for json_path in Path(output_dir).glob("*_analyzed.json"):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        value = data.get("date_taken")
        if not isinstance(value, str):
            continue
        try:
            ts = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if ts.date() == base.date() and (max_ts is None or ts > max_ts):
            max_ts = ts
    return max_ts


_ANALYSIS_KEYS = frozenset({"metadata", "enhancement", "location_detection", "slide_profiles"})


def _normalise_raw_response(raw: dict) -> dict:
    """Apply normalization to merged raw_response from pipeline.
    
    Handles the fact that raw_response is a MERGED structure from all pipeline
    steps (each step returns all 4 sections), not a single model response.
    
    Normalizes each section independently to handle model-specific quirks.
    """
    if not isinstance(raw, dict):
        return raw
    
    # Normalize each section independently 
    normalized = dict(raw)
    
    # Extract just the metadata section and normalize it as if it were a complete response
    if "metadata" in normalized and isinstance(normalized["metadata"], dict):
        metadata_section = normalized["metadata"]
        # Create a minimal complete response structure just for normalization
        complete_response = {
            "metadata": metadata_section,
            "enhancement": {},
            "location_detection": {},
            "slide_profiles": []
        }
        # Normalize just this structure
        norm_complete = OpenAIAnalyzer._normalise_response(complete_response)
        # Extract back the normalized metadata
        if "metadata" in norm_complete:
            normalized["metadata"] = norm_complete["metadata"]

    # Ensure all 11 metadata fields always exist (fill missing with None)
    _METADATA_FIELDS = [
        "objects", "persons", "weather", "mood_atmosphere", "time_of_day",
        "season_date", "scene_type", "location_setting", "activity_action",
        "photography_style", "composition_quality",
    ]
    if "metadata" in normalized and isinstance(normalized["metadata"], dict):
        for field in _METADATA_FIELDS:
            if field not in normalized["metadata"]:
                normalized["metadata"][field] = None

    return normalized


def _analysis_to_legacy_dict(result) -> dict:
    # Use raw_response when it has real parsed analysis keys — but normalise
    # enhancement recs first (some models return dicts instead of strings).
    if isinstance(result.raw_response, dict) and _ANALYSIS_KEYS.intersection(result.raw_response):
        data = _normalise_raw_response(result.raw_response)
        # Inject GPS from GeocodingStep result (stepped mode sets location.coordinates
        # but never writes it back into raw_response)
        if (
            "gps_coordinates" not in data
            and result.location is not None
            and result.location.coordinates is not None
        ):
            geo = result.location.coordinates
            data = {
                **data,
                "gps_coordinates": {
                    "latitude": geo.latitude,
                    "longitude": geo.longitude,
                    "display_name": getattr(geo, "display_name", ""),
                },
            }
        # Inject source_description so ExifWriter embeds description.txt in ImageDescription
        if "source_description" not in data and result.description_context:
            data = {**data, "source_description": result.description_context}
        return data

    metadata = {
        "scene_type": result.scene_type or result.title or "",
        "location_setting": result.description or "",
        "objects": result.keywords or [],
        "persons": result.people or [],
        "mood_atmosphere": result.mood or "",
        "photography_style": result.photography_style or "",
        "composition_quality": result.composition_quality or "",
    }
    if result.era:
        if result.era.time_of_day:
            metadata["time_of_day"] = result.era.time_of_day
        if result.era.season:
            metadata["season_date"] = result.era.season

    payload: dict = {"metadata": metadata, "enhancement": {"recommended_enhancements": []}}

    # Populate enhancement from raw_response or from enhancement_recommendations field
    if result.raw_response and isinstance(result.raw_response, dict):
        enhancement = result.raw_response.get("enhancement")
        if isinstance(enhancement, dict):
            recs = enhancement.get("recommended_enhancements")
            if isinstance(recs, list):
                payload["enhancement"] = enhancement
            elif result.enhancement_recommendations:
                payload["enhancement"]["recommended_enhancements"] = [
                    e.raw_text for e in result.enhancement_recommendations
                ]
        elif result.enhancement_recommendations:
            payload["enhancement"]["recommended_enhancements"] = [
                e.raw_text for e in result.enhancement_recommendations
            ]
    elif result.enhancement_recommendations:
        payload["enhancement"]["recommended_enhancements"] = [
            e.raw_text for e in result.enhancement_recommendations
        ]

    if result.location:
        payload["location_detection"] = {
            "country": result.location.country or "",
            "region": result.location.region or "",
            "city_or_area": result.location.city or "",
            "landmark_name": result.location.landmark_name or "",
            "confidence": result.location.confidence,
        }

    # Populate slide_profiles from raw_response (full array) or from slide_profile (single best)
    if result.raw_response and isinstance(result.raw_response, dict):
        slide_profiles = result.raw_response.get("slide_profiles")
        if isinstance(slide_profiles, list):  # Check type, not truthiness (empty lists are falsy)
            payload["slide_profiles"] = slide_profiles
        elif result.slide_profile:
            payload["slide_profiles"] = [
                {
                    "profile": result.slide_profile.profile_name,
                    "confidence": result.slide_profile.confidence,
                }
            ]
    elif result.slide_profile:
        payload["slide_profiles"] = [
            {
                "profile": result.slide_profile.profile_name,
                "confidence": result.slide_profile.confidence,
            }
        ]

    return payload


# ── Root group ───────────────────────────────────────────────────────


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
    invoke_without_command=True,
)
@click.version_option(package_name="picture-analyzer", prog_name="picture-analyzer")
@click.pass_context
def cli(ctx: click.Context):
    """AI-powered photo analysis, enhancement, and metadata embedding.

    Analyze images with OpenAI Vision, embed EXIF/XMP metadata,
    enhance based on AI recommendations, restore scanned slides,
    and generate reports.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ══════════════════════════════════════════════════════════════════════
# ANALYZE
# ══════════════════════════════════════════════════════════════════════


@cli.command()
@click.argument("image", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output directory or file path.")
@click.option("--provider", type=click.Choice(["openai", "ollama"], case_sensitive=False),
              default=None,
              help="AI analyzer provider override (openai or ollama).")
@click.option("-b", "--batch", is_flag=True,
              help="Treat IMAGE as a directory and process all images.")
@click.option("--enhance", "do_enhance", is_flag=True,
              help="Also enhance images based on AI recommendations.")
@click.option("--restore-slide",
              type=click.Choice(PROFILE_CHOICES, case_sensitive=False),
              default=None,
              help="Also restore slides using the given profile (or 'auto').")
@click.option("--no-json", is_flag=True,
              help="Do not save the JSON analysis sidecar.")
@click.option("--debug", is_flag=True,
              help="Print raw AI response before parsing (useful for diagnosing empty results).")
@click.option("--pipeline-mode", "pipeline_mode",
              type=click.Choice(["single", "stepped"], case_sensitive=False),
              default=None,
              help="Analysis pipeline mode override (single or stepped).")
@click.option("--skip-existing", "skip_existing", is_flag=True,
              help="Skip images that already have a completed analysis JSON in the output dir.")
@click.option("--steps", "only_steps", default=None,
              help="Comma-separated list of steps to run, e.g. 'metadata,slide_profiles'. "
                   "All other steps are skipped. Valid values: metadata, location, slide_profiles, enhancement, geocoding.")
@click.option("--update-existing", "update_existing", is_flag=True,
              help="Load existing JSON as starting point and merge new step results into it. "
                   "Use with --steps to re-run only specific steps without re-analyzing everything.")
def analyze(image: str, output: str | None, provider: str | None, batch: bool,
            do_enhance: bool, restore_slide: str | None, no_json: bool, debug: bool,
            pipeline_mode: str | None, skip_existing: bool,
            only_steps: str | None, update_existing: bool):
    """Analyze a single image or batch-process a directory.

    IMAGE is a path to an image file, or a directory when --batch is used.

    \b
    Examples
    --------
    Analyze one photo:
        picture-analyzer analyze photo.jpg

    Batch-analyze a directory with enhancement:
        picture-analyzer analyze photos/ --batch --enhance

    Re-run only slide_profiles on existing analyses:
        picture-analyzer analyze photos/ --batch --steps slide_profiles --update-existing

    Analyze + restore a scanned slide:
        picture-analyzer analyze scan.jpg --restore-slide auto

    Use stepped pipeline mode:
        picture-analyzer analyze photo.jpg --pipeline-mode stepped
    """
    image_path = Path(image)

    if provider:
        click.echo(f"Using analyzer provider: {provider.lower()}")

    if debug:
        import os; os.environ["PA_ANALYZER_DEBUG"] = "1"

    steps_list = [s.strip() for s in only_steps.split(",")] if only_steps else None

    if batch or image_path.is_dir():
        _batch_analyze(image_path, output, do_enhance, restore_slide, provider, pipeline_mode,
                       skip_existing=skip_existing, only_steps=steps_list,
                       update_existing=update_existing)
    else:
        _single_analyze(image_path, output, do_enhance, restore_slide, no_json, provider,
                        pipeline_mode, only_steps=steps_list, update_existing=update_existing)


def _load_partial_if_requested(
    update_existing: bool,
    only_steps: list[str] | None,
    image_path: Path,
    output_dir: str | None,
):
    """Return a partial AnalysisResult loaded from an existing JSON, or None.

    Only loads when ``update_existing`` is True and an existing JSON is found.
    The JSON is looked up next to the image or inside output_dir.
    """
    if not update_existing and not only_steps:
        return None
    # Try output dir first, then alongside the image
    candidates = []
    if output_dir:
        candidates.append(Path(output_dir) / f"{image_path.stem}_analyzed.json")
    candidates.append(image_path.parent / f"{image_path.stem}_analyzed.json")
    for candidate in candidates:
        if candidate.exists():
            try:
                from ..pipeline import load_partial_from_json
                partial = load_partial_from_json(candidate)
                click.echo(f"  ↺ Loaded existing analysis from {candidate.name}")
                return partial
            except Exception as exc:
                click.echo(f"  ⚠ Could not load existing JSON ({exc}), starting fresh", err=True)
                return None
    if update_existing:
        click.echo("  ⚠ --update-existing set but no existing JSON found — starting fresh", err=True)
    return None


def _preserve_pick(json_path: Path, analysis: dict) -> None:
    """Carry the preferred-variant pick over from an existing analysis JSON.

    Reprocessing writes a fresh analysis dict, which would silently drop the
    user's ``preferred_variant``/``preferred_path`` pick. Called before the
    JSON is (re)written; copies the pick fields into *analysis* when the old
    JSON has them and the new one does not.
    """
    try:
        if not json_path.is_file():
            return
        old = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    for field in ("preferred_variant", "preferred_path"):
        if not analysis.get(field) and old.get(field):
            analysis[field] = old[field]


def _single_analyze(
    image_path: Path,
    output: str | None,
    do_enhance: bool,
    restore_slide: str | None,
    no_json: bool,
    provider: str | None = None,
    pipeline_mode: str | None = None,
    only_steps: list[str] | None = None,
    update_existing: bool = False,
) -> None:
    """Analyze a single image."""
    _, SmartEnhancer, SlideRestoration, MetadataManager, _ = _get_legacy_modules()

    click.echo(f"Analyzing: {image_path}")

    # Resolve output path — treat as output DIRECTORY by default.
    # A path is only treated as an output FILE when it clearly names one:
    #  • it already exists as a file, OR
    #  • it has an image extension (e.g. ".../photo_analyzed.jpg")
    # Anything else (including a not-yet-existing album folder like
    # ``<enhanced_root>/<Albumnaam>``) is a directory: the analyzed copy is
    # written as ``<output>/<stem>_analyzed.jpg`` inside it.
    # The old heuristic (directory only when it already existed or ended with
    # a separator) wrote the analyzed image AS the album folder itself on a
    # first run, which then made batch mkdir() crash with FileExistsError.
    output_path = output
    if output_path:
        _is_file_target = (
            Path(output_path).is_file()
            or Path(output_path).suffix.lower() in DEFAULT_SUPPORTED_FORMATS
        )
        if not _is_file_target:
            output_path = str(Path(output_path) / f"{image_path.stem}_analyzed.jpg")

    analysis_result = _analyze_with_provider(
        image_path, provider, pipeline_mode,
        partial=_load_partial_if_requested(update_existing, only_steps, image_path, output),
        only_steps=only_steps,
    )
    analysis = _analysis_to_legacy_dict(analysis_result)
    
    # Translate to configured language if not English
    settings = get_settings()
    if settings.metadata.language != "en":
        analysis = translate_analysis_dict(analysis, settings.metadata.language)

    analyzed_target = Path(output_path) if output_path else Path("output") / f"{image_path.stem}_analyzed.jpg"
    analyzed_target.parent.mkdir(parents=True, exist_ok=True)

    # Apply description.txt ground truth (date/location/GPS) — same rules as
    # batch mode, so single-image processing produces identical EXIF dates
    # for the Immich timeline.
    ground_truth = _load_description_ground_truth(image_path.parent, settings)
    if ground_truth["status"] == "ok":
        # Sequential timestamp: reuse this image's own previous timestamp if
        # it has one (re-processing must not move it in the Immich timeline),
        # else continue the folder's sequence.
        gt_timestamp = _next_sequential_timestamp(
            analyzed_target.parent, ground_truth["parsed_date"],
            own_json=analyzed_target.with_suffix(".json"),
        )
        exif_dt = _read_image_exif_date(image_path)
        use_timestamp: datetime
        if exif_dt is not None:
            try:
                in_range = _exif_date_within_months(
                    exif_dt,
                    datetime.strptime(ground_truth["parsed_date"], "%Y-%m-%d"),
                )
            except Exception:
                in_range = False
            if in_range:
                use_timestamp = exif_dt
                click.echo(
                    f"  ↩ Keeping original EXIF date: "
                    f"{exif_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                )
            else:
                use_timestamp = gt_timestamp
        else:
            use_timestamp = gt_timestamp
        _apply_description_ground_truth(analysis, ground_truth, use_timestamp)
    elif ground_truth["status"] == "failed":
        click.echo(
            f"  ⚠ description.txt present but unusable: {ground_truth['reason']}",
            err=True,
        )
    analyzed_target.write_bytes(image_path.read_bytes())

    # Embed EXIF metadata (including GPS if geocoding resolved coordinates)
    try:
        from ..metadata.exif_writer import ExifWriter
        exif_writer = ExifWriter(language=get_settings().metadata.language)
        exif_writer.write_from_dict(analyzed_target, analyzed_target, analysis)
    except Exception as exc:
        click.echo(f"  ⚠ Could not embed EXIF metadata: {exc}", err=True)

    if not no_json:
        json_path = analyzed_target.with_suffix(".json")
        # Preserve the user's preferred-variant pick across reprocessing —
        # the fresh analysis dict does not carry it.
        _preserve_pick(json_path, analysis)
        json_path.write_text(
            json.dumps({k: v for k, v in analysis.items() if k not in ("source_description", "raw_response")}, indent=2),
            encoding="utf-8"
        )

    click.echo("\nAnalysis Results:")
    click.echo(json.dumps(analysis, indent=2))

    # Optional enhancement
    if do_enhance and "enhancement" in analysis:
        enhancer = SmartEnhancer()
        out_dir = str(analyzed_target.parent)
        enhanced_path = str(Path(out_dir) / f"{image_path.stem}_enhanced.jpg")
        result = enhancer.enhance_from_analysis(
            str(analyzed_target), analysis["enhancement"], enhanced_path,
        )
        if result:
            click.echo(f"✓ Enhanced: {result}")
            MetadataManager().copy_exif(
                str(analyzed_target), enhanced_path, enhanced_path,
            )

    # Optional slide restoration
    if restore_slide:
        _restore_from_analysis(
            SlideRestoration, MetadataManager,
            source_path=str(analyzed_target),
            analysis=analysis,
            restore_slide=restore_slide,
            output_dir=str(analyzed_target.parent),
            image_stem=image_path.stem,
        )


def _is_complete_analysis(json_path: Path) -> bool:
    """Return True only if *json_path* exists and contains real analysis content."""
    if not json_path.is_file() or json_path.stat().st_size < 200:
        return False
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    # Must have a metadata section with at least one non-empty value
    metadata = data.get("metadata", {})
    if not isinstance(metadata, dict):
        return False
    return any(v for v in metadata.values() if v)


def _batch_analyze(
    directory: Path,
    output: str | None,
    do_enhance: bool,
    restore_slide: str | None,
    provider: str | None = None,
    pipeline_mode: str | None = None,
    skip_existing: bool = False,
    only_steps: list[str] | None = None,
    update_existing: bool = False,
) -> None:
    """Batch-analyze all images in a directory."""
    _, SmartEnhancer, SlideRestoration, MetadataManager, _ = _get_legacy_modules()

    if not directory.is_dir():
        raise click.ClickException(f"Not a directory: {directory}")

    enhancer = SmartEnhancer() if do_enhance else None
    if output is None:
        output = _default_output_from_description(directory)
    output_dir = output or _fallback_output(directory.name)

    # A regular file occupying the output path (e.g. an analyzed image that
    # was once written AS the album folder) makes mkdir() crash with a raw
    # FileExistsError — fail with a clear, actionable message instead.
    if Path(output_dir).exists() and not Path(output_dir).is_dir():
        raise click.ClickException(
            f"Output path exists but is not a directory: {output_dir}\n"
            f"A file is blocking the album folder — remove or rename it, then retry."
        )
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Collect image files
    image_files: list[Path] = []
    for fmt in DEFAULT_SUPPORTED_FORMATS:
        image_files.extend(directory.glob(f"*{fmt}"))
        image_files.extend(directory.glob(f"*{fmt.upper()}"))
    image_files = sorted(set(image_files))

    if not image_files:
        raise click.ClickException(
            f"No supported images found in {directory}\n"
            f"Supported formats: {', '.join(sorted(DEFAULT_SUPPORTED_FORMATS))}"
        )

    # ── description.txt ground-truth gate (location + date) ──────────────
    # When a folder has a description.txt, location/date are read from it using
    # the same proven methods as update_location.py and used as ground truth
    # (overriding the LLM). If extraction fails, the folder is skipped.
    settings = get_settings()
    ground_truth = _load_description_ground_truth(directory, settings)
    if ground_truth["status"] == "failed":
        click.echo(f"\n📁 {directory.name}")
        click.echo(f"  ⚠ {ground_truth['reason']}")
        click.echo("  ⏭ Skipping folder (description.txt location/date incomplete)")
        return
    gt_timestamp: datetime | None = None
    if ground_truth["status"] == "ok":
        click.echo(f"\n📁 {directory.name}")
        click.echo(f"  Location (description.txt): {ground_truth['location_str']}")
        click.echo(
            f"  Date: {ground_truth['date_str']} → {ground_truth['parsed_date']}"
        )
        coords = ground_truth.get("coords")
        if coords:
            click.echo(
                f"  ✓ GPS: {coords['latitude']:.6f}, {coords['longitude']:.6f}"
                f" ({coords['display_name']})"
            )
        else:
            click.echo("  ⚠ Could not geocode location (too vague or not found)")
        gt_timestamp = datetime.strptime(ground_truth["parsed_date"], "%Y-%m-%d")
        # On a --skip-existing resume, continue after the last stored date_taken
        # so new images don't collide with already-written timestamps.
        if skip_existing:
            max_existing = _max_existing_date_taken(output_dir, gt_timestamp)
            if max_existing is not None:
                gt_timestamp = max_existing + timedelta(seconds=1)
                click.echo(
                    f"  ↺ Resuming: date_taken continues from "
                    f"{gt_timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
                )

    total = len(image_files)
    click.echo(f"Found {total} image(s) to process")
    if skip_existing:
        click.echo("  + Skipping already-completed images")
    if enhancer:
        click.echo("  + Enhancement enabled")
    if restore_slide:
        click.echo(f"  + Slide restoration enabled ({restore_slide} profile)")
    click.echo()

    success_count = 0
    skipped_count = 0
    errors: list[tuple[str, str]] = []  # (filename, error_message)

    # Build the pipeline once — reusing the same 4 OllamaClient instances for all images
    shared_pipeline = None
    if (pipeline_mode or settings.pipeline.mode) == "stepped":
        from ..pipeline import build_pipeline
        shared_pipeline = build_pipeline(settings)

    for idx, img in enumerate(image_files, 1):
        json_path = Path(output_dir) / f"{img.stem}_analyzed.json"
        if skip_existing and _is_complete_analysis(json_path):
            click.echo(f"[{idx}/{total}] Skipping (already done): {img.name}")
            skipped_count += 1
            continue
        click.echo(f"[{idx}/{total}] Processing: {img.name}")
        _t_img_start = time.perf_counter()
        try:
            analyzed_path = str(Path(output_dir) / f"{img.stem}_analyzed.jpg")
            _t_llm_start = time.perf_counter()
            analysis_result = _analyze_with_provider(
                img, provider, pipeline_mode, pipeline=shared_pipeline,
                partial=_load_partial_if_requested(update_existing, only_steps, img, output_dir),
                only_steps=only_steps,
                # Always run the location step — the LLM can identify specific
                # landmarks even when description.txt provides a general location.
                # The description.txt location is used as a fallback when the LLM
                # doesn't find a more specific landmark (see _apply_description_ground_truth).
                detect_location=None,
            )
            _t_llm = time.perf_counter() - _t_llm_start
            analysis = _analysis_to_legacy_dict(analysis_result)
            
            # Translate to configured language if not English
            if settings.metadata.language != "en":
                analysis = translate_analysis_dict(analysis, settings.metadata.language)

            # Override LLM location/date with description.txt ground truth
            if ground_truth["status"] == "ok":
                # If the image already carries an EXIF date that falls within
                # 6 months of the description date, preserve it instead of
                # overwriting with a sequential synthetic timestamp.
                exif_dt = _read_image_exif_date(img)
                use_timestamp: datetime
                if exif_dt is not None:
                    try:
                        in_range = _exif_date_within_months(
                            exif_dt,
                            datetime.strptime(ground_truth["parsed_date"], "%Y-%m-%d"),
                        )
                    except Exception:
                        in_range = False
                    if in_range:
                        use_timestamp = exif_dt
                        click.echo(
                            f"  ↩ Keeping original EXIF date: "
                            f"{exif_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                        )
                    else:
                        use_timestamp = gt_timestamp
                        gt_timestamp += timedelta(seconds=1)
                else:
                    use_timestamp = gt_timestamp
                    gt_timestamp += timedelta(seconds=1)
                _apply_description_ground_truth(analysis, ground_truth, use_timestamp)

            del analysis_result  # release model result immediately
            _t_copy_start = time.perf_counter()
            shutil.copy2(img, analyzed_path)  # copy without loading into Python memory
            _t_copy = time.perf_counter() - _t_copy_start

            # Embed EXIF metadata into the analyzed image copy
            _t_exif_start = time.perf_counter()
            try:
                from ..metadata.exif_writer import ExifWriter
                ExifWriter(language=get_settings().metadata.language).write_from_dict(
                    analyzed_path, analyzed_path, analysis
                )
            except Exception as exc:
                click.echo(f"  ⚠ Could not embed EXIF metadata: {exc}", err=True)
            _t_exif = time.perf_counter() - _t_exif_start

            _t_json_start = time.perf_counter()
            _json_path = Path(analyzed_path).with_suffix(".json")
            # Preserve the user's preferred-variant pick across reprocessing —
            # the fresh analysis dict does not carry it.
            _preserve_pick(_json_path, analysis)
            _json_path.write_text(
                json.dumps({k: v for k, v in analysis.items() if k not in ("source_description", "raw_response")}, indent=2), encoding="utf-8"
            )
            _t_json = time.perf_counter() - _t_json_start

            _t_enhance = 0.0
            if enhancer and "enhancement" in analysis:
                enhanced_path = str(Path(output_dir) / f"{img.stem}_enhanced.jpg")
                _t_enh_start = time.perf_counter()
                result = enhancer.enhance_from_analysis(
                    analyzed_path, analysis["enhancement"], enhanced_path,
                )
                if result:
                    MetadataManager().copy_exif(analyzed_path, enhanced_path, enhanced_path)
                    click.echo(f"  ✓ Enhanced: {enhanced_path}")
                _t_enhance = time.perf_counter() - _t_enh_start

            _t_restore = 0.0
            if restore_slide:
                _t_restore_start = time.perf_counter()
                _restore_from_analysis(
                    SlideRestoration, MetadataManager,
                    source_path=analyzed_path,
                    analysis=analysis,
                    restore_slide=restore_slide,
                    output_dir=output_dir,
                    image_stem=img.stem,
                )
                _t_restore = time.perf_counter() - _t_restore_start

            _t_total = time.perf_counter() - _t_img_start
            _t_post = _t_copy + _t_exif + _t_json + _t_enhance + _t_restore
            _post_pct = (_t_post / _t_total * 100) if _t_total > 0 else 0
            click.echo(
                f"  ⏱  LLM {_t_llm:.1f}s | "
                f"copy {_t_copy:.1f}s | exif {_t_exif:.1f}s | json {_t_json:.1f}s | "
                f"enhance {_t_enhance:.1f}s | restore {_t_restore:.1f}s | "
                f"total {_t_total:.1f}s (post-LLM {_t_post:.1f}s, {_post_pct:.0f}%)"
            )
            success_count += 1
            click.echo("  ✓ Complete")
        except Exception as exc:
            from ..core.exceptions import AnalysisError, ValidationError
            if isinstance(exc, ValidationError):
                msg = f"Validation: {exc}"
            elif isinstance(exc, AnalysisError):
                msg = f"Analysis failed: {exc}"
            else:
                msg = str(exc)
            errors.append((img.name, msg))
            click.echo(f"  ✗ Error: {msg}", err=True)
        finally:
            # Free analysis data and force GC to reclaim image buffers
            analysis = None  # type: ignore[assignment]
            gc.collect()
            # NOTE: Per-image "ollama stop" was removed to avoid cold model
            # reloads between images.  The model now stays loaded per
            # ``keep_alive`` (config.yaml, default 3600s).  To revert to the
            # old per-image unload behaviour, uncomment the block below:
            #
            # try:
            #     import subprocess as _sub
            #     _sub.run(
            #         ["ollama", "stop", settings.ollama.model],
            #         timeout=30,
            #         capture_output=True,
            #     )
            # except Exception:
            #     pass

    # Unload the model once after the entire batch completes (best-effort).
    # This frees VRAM when processing is done, while keeping the model hot
    # between images for throughput.  Remove if you want the model to stay
    # loaded indefinitely (controlled by keep_alive).
    try:
        import subprocess as _sub
        _sub.run(
            ["ollama", "stop", settings.ollama.model],
            timeout=30,
            capture_output=True,
        )
    except Exception:
        pass

    click.echo(f"\n{'=' * 50}")
    failed_count = len(errors)
    parts = [f"✓ {success_count} succeeded"]
    if skipped_count:
        parts.append(f"⏭ {skipped_count} skipped")
    if failed_count:
        parts.append(f"✗ {failed_count} failed")
    click.echo("Batch complete: " + ", ".join(parts))
    click.echo(f"Output directory: {output_dir}")

    if errors:
        import csv
        errors_csv = Path(output_dir) / "errors.csv"
        with errors_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["filename", "error"])
            writer.writerows(errors)
        click.echo(f"Error details written to: {errors_csv}", err=True)


# ══════════════════════════════════════════════════════════════════════
# REGENERATE  (rebuild images from existing JSON — no LLM calls)
# ══════════════════════════════════════════════════════════════════════


@cli.command()
@click.argument("source", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output directory. Defaults to the same directory as SOURCE.")
@click.option("-b", "--batch", is_flag=True,
              help="Treat SOURCE as a directory and regenerate all images that have an *_analyzed.json.")
@click.option("--restore-slide",
              type=click.Choice(PROFILE_CHOICES, case_sensitive=False),
              default=None,
              help="Slide restoration profile to apply (or 'auto' to use the detected profile).")
def regenerate(source: str, output: str | None, batch: bool, restore_slide: str | None):
    """Regenerate enhanced/restored images from existing analysis JSON files.

    No LLM calls are made — the existing JSON is used as-is.
    Use this after manually editing a JSON or after re-running specific steps.

    \b
    Examples
    --------
    Regenerate images from a single JSON:
        picture-analyzer regenerate output/photo_analyzed.json

    Regenerate all images in a folder:
        picture-analyzer regenerate output/ --batch

    Regenerate with slide restoration:
        picture-analyzer regenerate output/ --batch --restore-slide auto
    """
    _, SmartEnhancer, SlideRestoration, MetadataManager, _ = _get_legacy_modules()
    source_path = Path(source)

    if batch or source_path.is_dir():
        json_files = sorted(source_path.glob("*_analyzed.json"))
        if not json_files:
            raise click.ClickException(f"No *_analyzed.json files found in {source_path}")
        click.echo(f"Found {len(json_files)} analysis file(s) to regenerate")
        success, failed = 0, 0
        for json_file in json_files:
            try:
                _regenerate_from_json(json_file, output or str(source_path),
                                      SmartEnhancer, SlideRestoration, MetadataManager,
                                      restore_slide)
                success += 1
            except Exception as exc:
                click.echo(f"  ✗ {json_file.name}: {exc}", err=True)
                failed += 1
        click.echo(f"\nRegenerate complete: ✓ {success} succeeded" + (f", ✗ {failed} failed" if failed else ""))
    else:
        # Single JSON file
        if source_path.suffix != ".json":
            raise click.ClickException("SOURCE must be a *_analyzed.json file or a directory with --batch")
        out_dir = output or str(source_path.parent)
        _regenerate_from_json(source_path, out_dir,
                              SmartEnhancer, SlideRestoration, MetadataManager,
                              restore_slide)


def _regenerate_from_json(
    json_path: Path,
    output_dir: str,
    SmartEnhancer,
    SlideRestoration,
    MetadataManager,
    restore_slide: str | None,
) -> None:
    """Regenerate enhanced/restored images for one JSON file."""
    import json as _json

    analysis = _json.loads(json_path.read_text(encoding="utf-8"))

    # The source image is expected alongside the JSON (e.g. *_analyzed.jpg)
    stem = json_path.stem.replace("_analyzed", "")
    analyzed_jpg = json_path.with_name(f"{stem}_analyzed.jpg")
    if not analyzed_jpg.exists():
        # Fall back to original image in same dir
        for ext in (".jpg", ".jpeg", ".JPG", ".JPEG", ".png", ".PNG"):
            candidate = json_path.with_name(stem + ext)
            if candidate.exists():
                analyzed_jpg = candidate
                break
        else:
            raise FileNotFoundError(f"No source image found for {json_path.name}")

    click.echo(f"  Regenerating: {stem}")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    settings = get_settings()

    # Enhancement
    if "enhancement" in analysis:
        enhanced_path = str(Path(output_dir) / f"{stem}_enhanced.jpg")
        enhancer = SmartEnhancer()
        result = enhancer.enhance_from_analysis(str(analyzed_jpg), analysis["enhancement"], enhanced_path)
        if result:
            MetadataManager().copy_exif(str(analyzed_jpg), enhanced_path, enhanced_path)
            click.echo(f"    ✓ Enhanced: {Path(enhanced_path).name}")

    # Slide restoration
    if restore_slide:
        _restore_from_analysis(
            SlideRestoration, MetadataManager,
            source_path=str(analyzed_jpg),
            analysis=analysis,
            restore_slide=restore_slide,
            output_dir=output_dir,
            image_stem=stem,
        )


# ══════════════════════════════════════════════════════════════════════
# PROCESS  (analyze + enhance + optional restore in one step)
# ══════════════════════════════════════════════════════════════════════


@cli.command()
@click.argument("image", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output directory.")
@click.option("--provider", type=click.Choice(["openai", "ollama"], case_sensitive=False),
              default=None,
              help="AI analyzer provider override (openai or ollama).")
@click.option("--restore-slide",
              type=click.Choice(PROFILE_CHOICES, case_sensitive=False),
              default=None,
              help="Also restore slide using given profile.")
def process(image: str, output: str | None, provider: str | None, restore_slide: str | None):
    """Analyze, enhance, and optionally restore in one step.

    \b
    Examples
    --------
    Full pipeline:
        picture-analyzer process photo.jpg

    Include slide restoration:
        picture-analyzer process scan.jpg --restore-slide auto

    Custom output:
        picture-analyzer process photo.jpg -o results/
    """
    _, SmartEnhancer, SlideRestoration, MetadataManager, _ = _get_legacy_modules()

    image_path = Path(image)

    if provider:
        click.echo(f"Using analyzer provider: {provider.lower()}")
    output_dir = output or _fallback_output(image_path.stem)
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    analyzed_path = f"{output_dir}/{image_path.stem}_analyzed.jpg"
    enhanced_path = f"{output_dir}/{image_path.stem}_enhanced.jpg"

    # Step 1 — Analyze
    step_total = 3 if restore_slide else 2
    click.echo(f"[1/{step_total}] Analyzing: {image}")
    analysis_result = _analyze_with_provider(image_path, provider)
    analysis = _analysis_to_legacy_dict(analysis_result)
    
    # Translate to configured language if not English
    settings = get_settings()
    if settings.metadata.language != "en":
        analysis = translate_analysis_dict(analysis, settings.metadata.language)
    
    Path(analyzed_path).write_bytes(image_path.read_bytes())
    # Embed EXIF metadata (includes GPS when geocoding resolved coordinates)
    try:
        from ..metadata.exif_writer import ExifWriter
        ExifWriter(language=get_settings().metadata.language).write_from_dict(
            analyzed_path, analyzed_path, analysis
        )
    except Exception as exc:
        click.echo(f"  ⚠ Could not embed EXIF metadata: {exc}", err=True)
    Path(analyzed_path).with_suffix(".json").write_text(
        json.dumps(analysis, indent=2), encoding="utf-8"
    )
    click.echo("  ✓ Analysis complete")

    # Step 2 — Enhance
    click.echo(f"\n[2/{step_total}] Enhancing based on recommendations")
    enhancer = SmartEnhancer()
    if "enhancement" in analysis:
        result = enhancer.enhance_from_analysis(
            analyzed_path, analysis["enhancement"], enhanced_path,
        )
        if result:
            click.echo(f"  ✓ Enhanced: {result}")
            MetadataManager().copy_exif(analyzed_path, enhanced_path, enhanced_path)
        else:
            click.echo("  ⚠ Enhancement failed — analysis was still saved", err=True)
    else:
        click.echo("  ⚠ No enhancement data in analysis", err=True)

    # Step 3 — Optional slide restoration
    if restore_slide:
        click.echo(f"\n[3/{step_total}] Restoring slide")
        _restore_from_analysis(
            SlideRestoration, MetadataManager,
            source_path=analyzed_path,
            analysis=analysis,
            restore_slide=restore_slide,
            output_dir=output_dir,
            image_stem=image_path.stem,
        )

    click.echo(f"\nResults in: {output_dir}/")
    click.echo(f"  Analyzed:  {analyzed_path}")
    click.echo(f"  Enhanced:  {enhanced_path}")
    if restore_slide:
        click.echo(f"  Restored:  {output_dir}/{image_path.stem}_restored*.jpg")


# ══════════════════════════════════════════════════════════════════════
# REPORT / GALLERY
# ══════════════════════════════════════════════════════════════════════


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output path for the report file.")
def report(directory: str, output: str | None):
    """Generate a Markdown analysis report.

    DIRECTORY should contain analyzed images and *_analyzed.json files.
    """
    _, _, _, _, ReportGenerator = _get_legacy_modules()

    dir_path = Path(directory)
    report_path = Path(output) if output else dir_path / "analysis_report.md"

    click.echo(f"Generating report from: {dir_path}")
    ReportGenerator().generate_report(dir_path, report_path)
    click.echo(f"✓ Report saved to: {report_path}")


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output path for the gallery file.")
def gallery(directory: str, output: str | None):
    """Generate a Markdown image gallery report.

    Shows all processed images (original, enhanced, restored) in a table.
    """
    _, _, _, _, ReportGenerator = _get_legacy_modules()

    dir_path = Path(directory)
    gallery_path = Path(output) if output else dir_path / "gallery.md"

    click.echo(f"Generating gallery from: {dir_path}")
    ReportGenerator().generate_gallery_report(dir_path, gallery_path)
    click.echo(f"✓ Gallery saved to: {gallery_path}")


# ══════════════════════════════════════════════════════════════════════
# LEGACY / BACKWARD-COMPAT COMMANDS  (hidden from --help)
# ══════════════════════════════════════════════════════════════════════


@cli.command(name="batch", hidden=True)
@click.argument("directory", type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--output", type=click.Path(), default=None)
@click.option("--enhance", "do_enhance", is_flag=True)
@click.option("--restore-slide",
              type=click.Choice(PROFILE_CHOICES, case_sensitive=False), default=None)
def batch_cmd(directory: str, output: str | None,
              do_enhance: bool, restore_slide: str | None):
    """[LEGACY] Batch-analyze images — use 'analyze --batch' instead."""
    click.echo("Tip: use 'picture-analyzer analyze DIR --batch' instead.\n")
    _batch_analyze(Path(directory), output, do_enhance, restore_slide)


@cli.command(name="enhance", hidden=True)
@click.argument("image", type=click.Path(exists=True))
@click.option("-a", "--analysis", "analysis_path",
              type=click.Path(exists=True), default=None,
              help="Path to *_analyzed.json.")
@click.option("-o", "--output", type=click.Path(), default=None)
def enhance_cmd(image: str, analysis_path: str | None, output: str | None):
    """[LEGACY] Enhance an image from analysis JSON — use 'process' instead."""
    _, SmartEnhancer, _, _, _ = _get_legacy_modules()

    image_path = Path(image)

    if analysis_path is None:
        candidate = image_path.parent / f"{image_path.stem}_analyzed.json"
        if not candidate.exists():
            raise click.ClickException(
                f"Analysis file not found. Provide with -a or run 'analyze' first.\n"
                f"Looked for: {candidate}"
            )
        analysis_path = str(candidate)

    output_path = output or str(image_path.parent / f"{image_path.stem}_enhanced.jpg")

    click.echo(f"Enhancing: {image}")
    click.echo(f"Using analysis: {analysis_path}")
    enhancer = SmartEnhancer()
    result = enhancer.enhance_from_json(str(image_path), analysis_path, output_path)

    if result:
        click.echo(f"✓ Enhanced: {result}")
    else:
        raise click.ClickException("Enhancement failed")


@cli.command(name="restore-slide", hidden=True)
@click.argument("image", type=click.Path(exists=True))
@click.option("-p", "--profile",
              type=click.Choice(PROFILE_CHOICES, case_sensitive=False),
              default="auto", show_default=True)
@click.option("-a", "--analysis", "analysis_path",
              type=click.Path(exists=True), default=None,
              help="Path to *_analyzed.json (required for auto profile).")
@click.option("-o", "--output", type=click.Path(), default=None)
@click.option("--no-denoise", is_flag=True, help="Disable noise reduction.")
@click.option("--no-despeckle", is_flag=True, help="Disable despeckle filter.")
def restore_slide_cmd(image: str, profile: str, analysis_path: str | None,
                      output: str | None, no_denoise: bool, no_despeckle: bool):
    """[LEGACY] Restore a scanned slide — use 'process --restore-slide' instead."""
    _, _, SlideRestoration, _, _ = _get_legacy_modules()

    image_path = Path(image)
    output_path = output or str(image_path.parent / f"{image_path.stem}_restored.jpg")

    if profile == "auto":
        if analysis_path is None:
            candidate = image_path.parent / f"{image_path.stem}_analyzed.json"
            if not candidate.exists():
                raise click.ClickException(
                    "Auto profile requires analysis. Provide -a or specify a profile (-p faded)."
                )
            analysis_path = str(candidate)

        with open(analysis_path) as fh:
            analysis = json.load(fh)

        result = SlideRestoration.auto_restore_slide(
            str(image_path), analysis, output_path,
        )
    else:
        click.echo(f"Restoring slide with '{profile}' profile: {image}")
        result = SlideRestoration.restore_slide(
            str(image_path), profile=profile, output_path=output_path,
            denoise=not no_denoise, despeckle=not no_despeckle,
        )

    if result:
        click.echo(f"✓ Restored: {result}")
    else:
        raise click.ClickException("Slide restoration failed")


# ══════════════════════════════════════════════════════════════════════
# UTILITY COMMANDS
# ══════════════════════════════════════════════════════════════════════


def _update_exif_for_json(
    json_path: Path,
    source_description: str | None,
    language: str,
    geocode: bool = True,
    source_dir: Path | None = None,
) -> None:
    """Re-write EXIF for one analyzed image from its JSON + current description.txt.

    If *source_dir* is given and contains the original image, the image's
    original EXIF ``DateTimeOriginal`` is preserved when it falls within
    6 months of the description.txt date (same logic as the batch flow).
    """
    from ..metadata.exif_writer import ExifWriter

    analyzed_jpg = json_path.with_suffix(".jpg")
    if not analyzed_jpg.exists():
        raise FileNotFoundError(f"No image found at {analyzed_jpg}")

    analysis = json.loads(json_path.read_text(encoding="utf-8"))

    # Inject current description.txt content
    if source_description is not None:
        analysis["source_description"] = source_description

        # Override location_detection with ground truth from description.txt
        loc_match = re.search(r"(?im)^(?:location|locatie)\s*:\s*(.+)$", source_description)
        if loc_match:
            raw_location = loc_match.group(1).strip()
            loc = dict(analysis.get("location_detection") or {})
            if "/" in raw_location:
                loc.update({
                    "country": " / ".join(p.strip() for p in raw_location.split("/") if p.strip()),
                    "region": "",
                    "city_or_area": "",
                    "location_type": loc.get("location_type", "country"),
                })
            else:
                parts = [p.strip() for p in raw_location.split(",") if p.strip()]
                if len(parts) >= 1:
                    loc["city_or_area"] = parts[0]
                if len(parts) >= 2:
                    loc["region"] = parts[1]
                if len(parts) >= 3:
                    loc["country"] = parts[2]
            loc["confidence"] = 100
            loc["reasoning"] = "Explicitly named in the description"
            analysis["location_detection"] = loc

            # Re-geocode the updated location to get fresh GPS coordinates
            if geocode:
                settings = get_settings()
                if settings.geo.provider != "none":
                    try:
                        from ..geo.nominatim import NominatimGeocoder
                        geocoder = NominatimGeocoder(
                            cache_path=settings.geo.cache_path,
                            confidence_threshold=0,  # always geocode ground-truth location
                            user_agent=settings.geo.user_agent,
                            timeout=settings.geo.timeout_seconds,
                            max_results=settings.geo.max_results,
                        )
                        geo = geocoder.geocode_from_location_info(loc, confidence_threshold=0)
                        if geo:
                            analysis["gps_coordinates"] = {
                                "latitude": geo.latitude,
                                "longitude": geo.longitude,
                                "display_name": getattr(geo, "display_name", ""),
                            }
                            click.echo(
                                f"    GPS: {geo.latitude:.4f}, {geo.longitude:.4f}"
                                f" ({getattr(geo, 'display_name', '')})"
                            )
                    except Exception as exc:
                        click.echo(f"    ⚠ Geocoding failed: {exc}", err=True)

    # ── Preserve original EXIF date when it's within 6 months of description.txt ──
    # The analyzed JPG was copied from the source image, so its EXIF may
    # already have been overwritten by a previous run.  Read the date from
    # the *original* source image instead.
    if source_dir is not None and source_description:
        desc_path = source_dir / "description.txt"
        if desc_path.is_file():
            date_str_desc = extract_date(desc_path)
            if date_str_desc:
                parsed_desc = parse_date(date_str_desc)
                if parsed_desc:
                    base_dt = datetime.strptime(parsed_desc, "%Y-%m-%d")
                    # Find the original source image (same stem, any supported ext)
                    stem = json_path.stem.removesuffix("_analyzed")
                    src_img: Path | None = None
                    for ext in (".jpg", ".jpeg", ".png", ".heic",
                                ".JPG", ".JPEG", ".PNG", ".HEIC"):
                        candidate = source_dir / f"{stem}{ext}"
                        if candidate.is_file():
                            src_img = candidate
                            break
                    if src_img is not None:
                        exif_dt = _read_image_exif_date(src_img)
                        if exif_dt is not None:
                            try:
                                in_range = _exif_date_within_months(exif_dt, base_dt)
                            except Exception:
                                in_range = False
                            if in_range:
                                analysis["date_taken"] = exif_dt.strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                                click.echo(
                                    f"    ↩ Keeping original EXIF date: "
                                    f"{exif_dt.strftime('%Y-%m-%d %H:%M:%S')}"
                                )

    # Write updated analysis (GPS coordinates, location_detection) back to JSON
    json_path.write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")

    ExifWriter(language=language).write_from_dict(analyzed_jpg, analyzed_jpg, analysis)

    # Propagate EXIF to derived files (_enhanced.jpg, _restored_*.jpg)
    base = analyzed_jpg.stem.removesuffix("_analyzed")
    out_dir = analyzed_jpg.parent
    derived = [
        *out_dir.glob(f"{base}_enhanced.jpg"),
        *out_dir.glob(f"{base}_restored_*.jpg"),
    ]
    if derived:
        _inject_project_root()
        from metadata_manager import MetadataManager  # type: ignore[import-untyped]
        mm = MetadataManager()
        for d in derived:
            mm.copy_exif(str(analyzed_jpg), str(d), str(d))
            click.echo(f"    → Copied EXIF to {d.name}")


@cli.command(name="update-exif")
@click.argument("output_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--language", default=None,
              help="Language for EXIF labels (default: from config).")
@click.option("--no-geocode", is_flag=True,
              help="Skip re-geocoding even if the Location line changed.")
def update_exif(output_dir: str, source_dir: str, language: str | None, no_geocode: bool):
    """Re-write EXIF metadata from current description.txt without re-analyzing.

    \b
    OUTPUT_DIR  Directory containing *_analyzed.json / *_analyzed.jpg files.
    SOURCE_DIR  Directory with description.txt (default: current directory).

    \b
    Examples
    --------
    Update EXIF for all images in an output folder:
        picture-analyzer update-exif ./output ./Photos/1986-Vakantie
    Update EXIF without specifying source dir (uses current directory):
        picture-analyzer update-exif ./output
    Skip geocoding:
        picture-analyzer update-exif ./output ./Photos/1986-Vakantie --no-geocode
    Override language:
        picture-analyzer update-exif ./output ./Photos/1986-Vakantie --language nl
    """
    settings = get_settings()
    lang = language or settings.metadata.language
    out_path = Path(output_dir)
    src_path = Path(source_dir)

    # Read description.txt once
    desc_file = src_path / "description.txt"
    source_description: str | None = None
    if desc_file.exists():
        source_description = desc_file.read_text(encoding="utf-8").strip()
        click.echo(f"Using description.txt from: {desc_file}")
    else:
        click.echo(f"No description.txt found in {src_path} — updating EXIF without it")

    json_files = sorted(out_path.glob("*_analyzed.json"))
    if not json_files:
        raise click.ClickException(f"No *_analyzed.json files found in {out_path}")

    click.echo(f"Found {len(json_files)} analyzed image(s) to update\n")

    updated, errors = 0, 0
    for json_path in json_files:
        click.echo(f"  {json_path.stem} …")
        try:
            _update_exif_for_json(json_path, source_description, lang,
                                  geocode=not no_geocode, source_dir=src_path)
            click.echo("    ✓ EXIF updated")
            updated += 1
        except Exception as exc:
            click.echo(f"    ✗ {exc}", err=True)
            errors += 1

    click.echo(f"\nDone — {updated} updated, {errors} errors")


@cli.command(name="check-locations")
@click.argument("root_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--no-geocode", is_flag=True, help="Only parse location text, skip geocoding.")
@click.option("--failed-only", is_flag=True, help="Only show entries that failed to resolve.")
@click.option("--language", default="nl", show_default=True,
              help="Label for the location line in description.txt (nl → 'Locatie', en → 'Location').")
def check_locations(root_dir: str, no_geocode: bool, failed_only: bool, language: str):
    """Check geolocation from description.txt files in all subfolders.

    \b
    Scans ROOT_DIR recursively for subfolders containing a description.txt,
    parses the Locatie/Location line, and optionally resolves GPS coordinates
    via Nominatim. Useful to verify description.txt files before re-processing.

    \b
    Examples
    --------
    Check all locations under a media root:
        picture-analyzer check-locations ./media
    Only show failures:
        picture-analyzer check-locations ./media --failed-only
    Only parse, no geocoding:
        picture-analyzer check-locations ./media --no-geocode
    """
    import re as _re

    root = Path(root_dir)
    desc_files = sorted(root.rglob("description.txt"))

    if not desc_files:
        raise click.ClickException(f"No description.txt files found under {root}")

    click.echo(f"Found {len(desc_files)} description.txt file(s)\n")

    geocoder = None
    if not no_geocode:
        settings = get_settings()
        if settings.geo.provider != "none":
            from ..geo.nominatim import NominatimGeocoder
            geocoder = NominatimGeocoder(
                cache_path=settings.geo.cache_path,
                confidence_threshold=0,
                user_agent=settings.geo.user_agent,
                timeout=settings.geo.timeout_seconds,
                max_results=settings.geo.max_results,
            )

    ok = 0
    failed = 0
    for desc_file in desc_files:
        folder = desc_file.parent.name
        text = desc_file.read_text(encoding="utf-8").strip()

        # Parse location line
        loc_match = _re.search(r"(?im)^(?:location|locatie)\s*:\s*(.+)$", text)
        raw_location = loc_match.group(1).strip() if loc_match else None

        if not raw_location:
            click.echo(f"  {folder}")
            click.echo(f"    ⚠  No location line found")
            click.echo()
            failed += 1
            continue

        # Detect noise in the location text for suggestion
        _noise_present = bool(_re.search(r"\(|o\.a\.|e\.a\.| en ", raw_location, _re.I))

        # Build location dict (same logic as _update_exif_for_json)
        if "/" in raw_location:
            loc = {
                "country": " / ".join(p.strip() for p in raw_location.split("/") if p.strip()),
                "region": "",
                "city_or_area": "",
                "confidence": 100,
            }
        else:
            parts = [p.strip() for p in raw_location.split(",") if p.strip()]
            loc = {
                "city_or_area": parts[0] if len(parts) >= 1 else "",
                "region": parts[1] if len(parts) >= 2 else "",
                "country": parts[2] if len(parts) >= 3 else "",
                "confidence": 100,
            }

        resolved = False
        geo = None
        if geocoder:
            try:
                geo = geocoder.geocode_from_location_info(loc, confidence_threshold=0)
                resolved = geo is not None
            except Exception:
                resolved = False

        if failed_only and resolved:
            ok += 1
            continue

        click.echo(f"  {folder}")
        click.echo(f"    Location text : {raw_location}")

        # Show parsed components
        if "/" not in raw_location:
            city = loc.get("city_or_area", "")
            region = loc.get("region", "")
            country = loc.get("country", "")
            if geocoder:
                from ..geo.nominatim import NominatimGeocoder as _GC
                city_n = _GC._strip_noise(city)
                region_n = _GC._strip_noise(region)
                country_n = _GC._normalize_country(_GC._strip_noise(country))
                click.echo(f"    Parsed as     : city={city_n!r}  region={region_n!r}  country={country_n!r}")
            else:
                click.echo(f"    Parsed as     : city={city!r}  region={region!r}  country={country!r}")

        if geocoder:
            if resolved:
                click.echo(f"    GPS           : {geo.latitude:.4f}, {geo.longitude:.4f}")
                click.echo(f"    Resolved as   : {geo.display_name}")
                ok += 1
            else:
                click.echo(f"    GPS           : ✗ not resolved by Nominatim")
                # Suggest a cleaner format
                if _noise_present:
                    _clean = _re.sub(r"\s*\([^)]*\)", "", raw_location)
                    _clean = _re.sub(r",?\s*o\.a\..*$", "", _clean, flags=_re.I)
                    _clean = _re.sub(r",?\s*e\.a\..*$", "", _clean, flags=_re.I)
                    _clean = _re.sub(r",?\s* en .*$", "", _clean, flags=_re.I)
                    _clean = _clean.strip().rstrip(",").strip()
                    click.echo(f"    Suggestion    : try simplifying to: {_clean!r}")
                else:
                    _parts = [p.strip() for p in raw_location.split(",") if p.strip()]
                    if len(_parts) == 2:
                        click.echo(f"    Suggestion    : add country, e.g.: {raw_location}, Nederland")
                    elif len(_parts) == 1:
                        click.echo(f"    Suggestion    : add city/country, e.g.: {raw_location}, [regio], [land]")
                failed += 1
        else:
            ok += 1

        click.echo()

    summary = f"Done — {ok} resolved"
    if failed:
        summary += f", {failed} failed/missing"
    click.echo(summary)


@cli.command(name="config")
def config_cmd():
    """Show the current configuration."""
    from ..config.settings import get_settings

    settings = get_settings()
    click.echo(settings.model_dump_json(indent=2))


# ── Immich album publishing ─────────────────────────────────────────


def _immich_settings():
    """Load settings and validate the Immich section."""
    from ..config.settings import get_settings

    settings = get_settings()
    cfg = settings.immich
    if not cfg.api_key:
        raise click.ClickException(
            "immich.api_key not configured — add it to config.yaml "
            "(Immich → Settings → API Keys)"
        )
    if not cfg.picks_root:
        raise click.ClickException(
            "immich.picks_root not configured — add it to config.yaml "
            "(host path of the picks external library)"
        )
    return settings, cfg


@cli.command(name="publish-immich")
@click.argument("directory", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--dry-run", is_flag=True, help="Show what would be published without writing.")
def publish_immich(directory: str, dry_run: bool):
    """Publish the preferred picks of a folder into the picks root.

    DIRECTORY is a photos folder (Albumnaam routing, same as analyze).
    Each picked variant is hardlinked into <picks_root>/<Albumnaam>/<stem>.jpg
    so Immich sees exactly one asset per image. Re-picking replaces the file.
    """
    settings, cfg = _immich_settings()
    from ..immich.publisher import publish_folder

    result = publish_folder(
        Path(directory), settings.output.enhanced_root, cfg.picks_root, dry_run
    )
    click.echo(f"Album: {_album_name(Path(directory))}")
    click.echo(f"  published: {len(result.published)}")
    click.echo(f"  removed:   {len(result.removed)}")
    click.echo(f"  skipped:   {len(result.skipped)} (no pick yet)")
    for e in result.errors:
        click.echo(f"  ✗ {e}", err=True)
    if dry_run:
        click.echo("(dry run — nothing written)")


def _album_name(folder: Path) -> str:
    from ..immich.publisher import _album_for_folder

    return _album_for_folder(folder)


@cli.command(name="sync-immich")
@click.option("--dry-run", is_flag=True, help="Show what would change without changing.")
@click.option("--scan", is_flag=True, help="Trigger an Immich library scan first and wait briefly.")
def sync_immich(dry_run: bool, scan: bool):
    """Make Immich albums mirror the picks root.

    Creates missing albums, adds new assets, removes gone assets. Run after
    publish-immich (and after the Immich library scan has picked up new files).
    """
    import time as _time

    settings, cfg = _immich_settings()
    from ..immich.client import ImmichClient, ImmichError
    from ..immich.sync import sync_albums, trigger_scan

    immich_root = cfg.immich_picks_root or cfg.picks_root
    client = ImmichClient(cfg.url, cfg.api_key)
    if not client.ping():
        raise click.ClickException(f"Immich not reachable at {cfg.url}")

    if scan:
        lib_id = trigger_scan(client, cfg.picks_root)
        if lib_id:
            click.echo(f"Library scan triggered ({lib_id}) — waiting 20s for new files…")
            _time.sleep(20)
        else:
            click.echo("⚠ No Immich library imports the picks root — skipping scan", err=True)

    try:
        report = sync_albums(client, cfg.picks_root, str(immich_root), dry_run)
    except ImmichError as exc:
        raise click.ClickException(str(exc))

    for name in report.albums_created:
        click.echo(f"  + album created: {name}")
    click.echo(f"  assets added:    {report.assets_added}")
    click.echo(f"  assets removed:  {report.assets_removed}")
    if report.missing_assets:
        click.echo(f"  ⚠ {len(report.missing_assets)} pick files not found in Immich "
                   f"(library scan pending?)")
        for p in report.missing_assets[:5]:
            click.echo(f"      {p}")
    for e in report.errors:
        click.echo(f"  ✗ {e}", err=True)
    if dry_run:
        click.echo("(dry run — nothing changed)")


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    """Entry point for the ``picture-analyzer`` console script."""
    cli()


if __name__ == "__main__":
    main()
