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
import sys
from pathlib import Path
from typing import Optional

import click

from ..config.defaults import DEFAULT_SUPPORTED_FORMATS


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
                if isinstance(p, dict) and "profile" in p and p.get("confidence", 0) >= 50
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
def analyze(image: str, output: str | None, batch: bool,
            do_enhance: bool, restore_slide: str | None, no_json: bool):
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
    """
    image_path = Path(image)

    if batch or image_path.is_dir():
        _batch_analyze(image_path, output, do_enhance, restore_slide)
    else:
        _single_analyze(image_path, output, do_enhance, restore_slide, no_json)


def _single_analyze(
    image_path: Path,
    output: str | None,
    do_enhance: bool,
    restore_slide: str | None,
    no_json: bool,
) -> None:
    """Analyze a single image."""
    PictureAnalyzer, SmartEnhancer, SlideRestoration, MetadataManager, _ = _get_legacy_modules()

    analyzer = PictureAnalyzer()
    click.echo(f"Analyzing: {image_path}")

    # Resolve output path
    output_path = output
    if output_path and Path(output_path).is_dir():
        output_path = str(Path(output_path) / f"{image_path.stem}_analyzed.jpg")

    analysis = analyzer.analyze_and_save(
        str(image_path), output_path=output_path, save_json=not no_json,
    )
    click.echo("\nAnalysis Results:")
    click.echo(json.dumps(analysis, indent=2))

    # Optional enhancement
    if do_enhance and "enhancement" in analysis:
        enhancer = SmartEnhancer()
        out_dir = output or "output"
        enhanced_path = str(Path(out_dir) / f"{image_path.stem}_enhanced.jpg")
        result = enhancer.enhance_from_analysis(
            output_path or str(image_path), analysis["enhancement"], enhanced_path,
        )
        if result:
            click.echo(f"✓ Enhanced: {result}")
            MetadataManager().copy_exif(
                output_path or str(image_path), enhanced_path, enhanced_path,
            )

    # Optional slide restoration
    if restore_slide:
        out_dir = output or "output"
        _restore_from_analysis(
            SlideRestoration, MetadataManager,
            source_path=output_path or str(image_path),
            analysis=analysis,
            restore_slide=restore_slide,
            output_dir=out_dir,
            image_stem=image_path.stem,
        )


def _batch_analyze(
    directory: Path,
    output: str | None,
    do_enhance: bool,
    restore_slide: str | None,
) -> None:
    """Batch-analyze all images in a directory."""
    PictureAnalyzer, SmartEnhancer, SlideRestoration, MetadataManager, _ = _get_legacy_modules()

    if not directory.is_dir():
        raise click.ClickException(f"Not a directory: {directory}")

    analyzer = PictureAnalyzer()
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
    if enhancer:
        click.echo("  + Enhancement enabled")
    if restore_slide:
        click.echo(f"  + Slide restoration enabled ({restore_slide} profile)")
    click.echo()

    success_count = 0
    for idx, img in enumerate(image_files, 1):
        click.echo(f"[{idx}/{total}] Processing: {img.name}")
        try:
            analyzed_path = str(Path(output_dir) / f"{img.stem}_analyzed.jpg")
            analysis = analyzer.analyze_and_save(str(img), analyzed_path, save_json=True)

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

    click.echo(f"\n{'=' * 50}")
    click.echo(f"Batch complete: {success_count}/{total} successful")
    click.echo(f"Output directory: {output_dir}")


# ══════════════════════════════════════════════════════════════════════
# PROCESS  (analyze + enhance + optional restore in one step)
# ══════════════════════════════════════════════════════════════════════


@cli.command()
@click.argument("image", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), default=None,
              help="Output directory.")
@click.option("--restore-slide",
              type=click.Choice(PROFILE_CHOICES, case_sensitive=False),
              default=None,
              help="Also restore slide using given profile.")
def process(image: str, output: str | None, restore_slide: str | None):
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
    PictureAnalyzer, SmartEnhancer, SlideRestoration, MetadataManager, _ = _get_legacy_modules()

    image_path = Path(image)
    output_dir = output or "output"
    Path(output_dir).mkdir(exist_ok=True)

    analyzed_path = f"{output_dir}/{image_path.stem}_analyzed.jpg"
    enhanced_path = f"{output_dir}/{image_path.stem}_enhanced.jpg"

    # Step 1 — Analyze
    step_total = 3 if restore_slide else 2
    click.echo(f"[1/{step_total}] Analyzing: {image}")
    analyzer = PictureAnalyzer()
    analysis = analyzer.analyze_and_save(str(image_path), analyzed_path, save_json=True)
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
