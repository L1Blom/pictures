"""Click-based CLI for picture-analyzer.

Replaces the legacy argparse CLI (``cli.py``) with a modern Click
interface.  All commands use the new typed components from Phase 2
with transparent fallback to legacy modules when needed.

Entry point registered in ``pyproject.toml``::

    [project.scripts]
    picture-analyzer = "picture_analyzer.cli.app:main"
"""
from __future__ import annotations

import json
import mimetypes
import sys
from pathlib import Path
from typing import Optional

import click

from ..analyzers import create_analyzer
from ..config.defaults import DEFAULT_SUPPORTED_FORMATS
from ..config.settings import get_settings
from ..core.models import AnalysisContext, ImageData


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


def _resolve_profiles(restore_slide: str, analysis: dict) -> list[str]:
    """Determine which slide-restoration profiles to apply."""
    if restore_slide != "auto":
        return [restore_slide]

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
            return profiles
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
        detect_location=settings.prompt.detect_location,
        custom_instructions=settings.prompt.custom_instructions,
        description_text=description_text,
    )
    mime_type, _ = mimetypes.guess_type(str(image_path))
    image = ImageData(path=image_path, mime_type=mime_type or "image/jpeg")

    if effective_mode == "stepped":
        from ..pipeline import build_pipeline
        active_pipeline = pipeline or build_pipeline(settings)
        return active_pipeline.run(image, context)

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


_ANALYSIS_KEYS = frozenset({"metadata", "enhancement", "location_detection", "slide_profiles"})


def _normalise_raw_response(raw: dict) -> dict:
    """Ensure enhancement recs in raw_response are always plain strings."""
    enhancement = raw.get("enhancement", {})
    if isinstance(enhancement, dict):
        recs = enhancement.get("recommended_enhancements", [])
        normalised = []
        for rec in recs:
            if isinstance(rec, str):
                normalised.append(rec)
            elif isinstance(rec, dict):
                action = rec.get("action", "")
                value = rec.get("value", "")
                normalised.append(f"{action}: {value}" if value else action)
            else:
                normalised.append(str(rec))
        raw = {**raw, "enhancement": {**enhancement, "recommended_enhancements": normalised}}
    return raw


def _analysis_to_legacy_dict(result) -> dict:
    # Use raw_response when it has real parsed analysis keys — but normalise
    # enhancement recs first (some models return dicts instead of strings).
    if result.raw_response and isinstance(result.raw_response, dict):
        if _ANALYSIS_KEYS.intersection(result.raw_response):
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

    if result.enhancement_recommendations:
        payload["enhancement"]["recommended_enhancements"] = [
            e.raw_text for e in result.enhancement_recommendations
        ]

    if result.location:
        payload["location_detection"] = {
            "country": result.location.country or "",
            "region": result.location.region or "",
            "city_or_area": result.location.city or "",
            "confidence": result.location.confidence,
        }

    if result.slide_profile:
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
def analyze(image: str, output: str | None, provider: str | None, batch: bool,
            do_enhance: bool, restore_slide: str | None, no_json: bool, debug: bool,
            pipeline_mode: str | None, skip_existing: bool):
    """Analyze a single image or batch-process a directory.

    IMAGE is a path to an image file, or a directory when --batch is used.

    \b
    Examples
    --------
    Analyze one photo:
        picture-analyzer analyze photo.jpg

    Batch-analyze a directory with enhancement:
        picture-analyzer analyze photos/ --batch --enhance

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

    if batch or image_path.is_dir():
        _batch_analyze(image_path, output, do_enhance, restore_slide, provider, pipeline_mode, skip_existing=skip_existing)
    else:
        _single_analyze(image_path, output, do_enhance, restore_slide, no_json, provider, pipeline_mode)


def _single_analyze(
    image_path: Path,
    output: str | None,
    do_enhance: bool,
    restore_slide: str | None,
    no_json: bool,
    provider: str | None = None,
    pipeline_mode: str | None = None,
) -> None:
    """Analyze a single image."""
    _, SmartEnhancer, SlideRestoration, MetadataManager, _ = _get_legacy_modules()

    click.echo(f"Analyzing: {image_path}")

    # Resolve output path — treat as output directory when:
    #  • it already is one, OR
    #  • the raw string ends with a path separator (user wrote "output_dir/")
    output_path = output
    if output_path:
        _raw = str(output)
        if Path(output_path).is_dir() or _raw.endswith("/") or _raw.endswith("\\"):
            output_path = str(Path(output_path) / f"{image_path.stem}_analyzed.jpg")

    analysis_result = _analyze_with_provider(image_path, provider, pipeline_mode)
    analysis = _analysis_to_legacy_dict(analysis_result)

    analyzed_target = Path(output_path) if output_path else Path("output") / f"{image_path.stem}_analyzed.jpg"
    analyzed_target.parent.mkdir(parents=True, exist_ok=True)
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
        json_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")

    click.echo("\nAnalysis Results:")
    click.echo(json.dumps(analysis, indent=2))

    # Optional enhancement
    if do_enhance and "enhancement" in analysis:
        enhancer = SmartEnhancer()
        out_dir = output or "output"
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
        out_dir = output or "output"
        _restore_from_analysis(
            SlideRestoration, MetadataManager,
            source_path=str(analyzed_target),
            analysis=analysis,
            restore_slide=restore_slide,
            output_dir=out_dir,
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
) -> None:
    """Batch-analyze all images in a directory."""
    _, SmartEnhancer, SlideRestoration, MetadataManager, _ = _get_legacy_modules()

    if not directory.is_dir():
        raise click.ClickException(f"Not a directory: {directory}")

    enhancer = SmartEnhancer() if do_enhance else None
    output_dir = output or "output"
    Path(output_dir).mkdir(exist_ok=True)

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

    # Build the pipeline once — reusing the same 4 OllamaClient instances for all images
    settings = get_settings()
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
        try:
            analyzed_path = str(Path(output_dir) / f"{img.stem}_analyzed.jpg")
            analysis_result = _analyze_with_provider(img, provider, pipeline_mode, pipeline=shared_pipeline)
            analysis = _analysis_to_legacy_dict(analysis_result)
            Path(analyzed_path).write_bytes(img.read_bytes())

            # Embed EXIF metadata into the analyzed image copy
            try:
                from ..metadata.exif_writer import ExifWriter
                ExifWriter(language=get_settings().metadata.language).write_from_dict(
                    analyzed_path, analyzed_path, analysis
                )
            except Exception as exc:
                click.echo(f"  ⚠ Could not embed EXIF metadata: {exc}", err=True)

            Path(analyzed_path).with_suffix(".json").write_text(
                json.dumps({k: v for k, v in analysis.items() if k != "source_description"}, indent=2), encoding="utf-8"
            )

            if enhancer and "enhancement" in analysis:
                enhanced_path = str(Path(output_dir) / f"{img.stem}_enhanced.jpg")
                result = enhancer.enhance_from_analysis(
                    analyzed_path, analysis["enhancement"], enhanced_path,
                )
                if result:
                    MetadataManager().copy_exif(analyzed_path, enhanced_path, enhanced_path)

            if restore_slide:
                _restore_from_analysis(
                    SlideRestoration, MetadataManager,
                    source_path=analyzed_path,
                    analysis=analysis,
                    restore_slide=restore_slide,
                    output_dir=output_dir,
                    image_stem=img.stem,
                )

            success_count += 1
            click.echo("  ✓ Complete")
        except Exception as exc:
            click.echo(f"  ✗ Error: {exc}", err=True)
        finally:
            # Flush Ollama KV-cache between images: repeated prompt text causes
            # the previous image's visual context to bleed into the next one.
            # "ollama stop" unloads the model immediately without running inference.
            try:
                import subprocess as _sub
                _sub.run(
                    ["ollama", "stop", settings.ollama.model],
                    timeout=30,
                    capture_output=True,
                )
            except Exception:
                pass  # non-fatal: cache flush is best-effort

    click.echo(f"\n{'=' * 50}")
    click.echo(f"Batch complete: {success_count}/{total} successful" + (f" ({skipped_count} skipped)" if skipped_count else ""))
    click.echo(f"Output directory: {output_dir}")


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
    output_dir = output or "output"
    Path(output_dir).mkdir(exist_ok=True)

    analyzed_path = f"{output_dir}/{image_path.stem}_analyzed.jpg"
    enhanced_path = f"{output_dir}/{image_path.stem}_enhanced.jpg"

    # Step 1 — Analyze
    step_total = 3 if restore_slide else 2
    click.echo(f"[1/{step_total}] Analyzing: {image}")
    analysis_result = _analyze_with_provider(image_path, provider)
    analysis = _analysis_to_legacy_dict(analysis_result)
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
) -> None:
    """Re-write EXIF for one analyzed image from its JSON + current description.txt."""
    import re
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
            _update_exif_for_json(json_path, source_description, lang, geocode=not no_geocode)
            click.echo("    ✓ EXIF updated")
            updated += 1
        except Exception as exc:
            click.echo(f"    ✗ {exc}", err=True)
            errors += 1

    click.echo(f"\nDone — {updated} updated, {errors} errors")


@cli.command(name="config")
def config_cmd():
    """Show the current configuration."""
    from ..config.settings import get_settings

    settings = get_settings()
    click.echo(settings.model_dump_json(indent=2))


@cli.command()
@click.argument("directory", type=click.Path(exists=True, file_okay=False),
                default=".")
@click.option("-p", "--port", type=int, default=None,
              help="Port for the web server.")
def describe(directory: str, port: int | None):
    """Launch the description editor web UI.

    Opens a browser-based editor for writing description.txt files
    that provide context to the AI analyzer.
    """
    _inject_project_root()

    from ..config.settings import get_settings

    settings = get_settings()
    web_port = port or settings.web.port

    try:
        from run_description_editor import main as run_editor  # type: ignore[import-untyped]
        sys.argv = ["describe", directory]
        run_editor()
    except ImportError:
        click.echo(f"Starting description editor on port {web_port}...")
        click.echo(f"Photos directory: {directory}")
        click.echo(
            "Description editor not found.  Install with: pip install picture-analyzer[web]"
        )


# ── Entry point ──────────────────────────────────────────────────────


def main() -> None:
    """Entry point for the ``picture-analyzer`` console script."""
    cli()


if __name__ == "__main__":
    main()
