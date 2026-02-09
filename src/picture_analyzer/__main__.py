"""Entry point for `python -m picture_analyzer`.

Delegates to the existing CLI while the Click migration is in progress.
After Phase 5, this will call the Click-based CLI directly.
"""
import sys
from pathlib import Path


def main() -> None:
    """Run the picture-analyzer CLI."""
    # During migration: delegate to legacy CLI
    # Add project root to path so legacy imports (cli, cli_commands,
    # picture_analyzer shim, config, etc.) resolve correctly.
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # The root-level picture_analyzer.py shim may already be cached as
    # this package.  We need to ensure the legacy modules can import
    # the shim version.  Easiest: just exec the cli module directly.
    import importlib.util
    cli_path = project_root / "cli.py"
    if cli_path.exists():
        spec = importlib.util.spec_from_file_location("cli", cli_path)
        cli_mod = importlib.util.module_from_spec(spec)
        # Pre-load the picture_analyzer shim so cli_commands finds PictureAnalyzer
        pa_shim_path = project_root / "picture_analyzer.py"
        if pa_shim_path.exists():
            pa_spec = importlib.util.spec_from_file_location(
                "picture_analyzer_shim", pa_shim_path
            )
            pa_mod = importlib.util.module_from_spec(pa_spec)
            sys.modules["picture_analyzer_shim"] = pa_mod
            pa_spec.loader.exec_module(pa_mod)
            # Make legacy `from picture_analyzer import ...` resolve to shim
            # by injecting PictureAnalyzer into our own package namespace
            from picture_analyzer_legacy import PictureAnalyzer
            import picture_analyzer as pkg
            pkg.PictureAnalyzer = PictureAnalyzer  # type: ignore[attr-defined]

        spec.loader.exec_module(cli_mod)
        cli_mod.main()
    else:
        print("Error: Legacy CLI not found. Run from the project directory.")
        sys.exit(1)


if __name__ == "__main__":
    main()
