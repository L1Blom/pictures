"""CLI application entry point.

During migration this delegates to the legacy argparse CLI.
Will be replaced with a Click-based CLI in Phase 5.
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    """Entry point for ``picture-analyzer`` command."""
    # Delegate to __main__.py which handles the legacy CLI bridging
    project_root = Path(__file__).resolve().parent.parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from picture_analyzer.__main__ import main as _main
    _main()


if __name__ == "__main__":
    main()
