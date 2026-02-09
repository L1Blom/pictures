"""Backward-compatibility shim.

Existing code that does ``from picture_analyzer import PictureAnalyzer``
will keep working via this re-export from the renamed legacy module.

This file will be removed once Phase 2 migrates PictureAnalyzer into
the ``picture_analyzer.analyzers`` package.
"""
# Re-export everything from the renamed legacy module so existing
# imports like ``from picture_analyzer import PictureAnalyzer`` continue
# to work.  The actual package is installed at ``src/picture_analyzer/``
# but this root-level shim takes precedence when running from the
# project directory.
from picture_analyzer_legacy import *  # noqa: F401, F403
from picture_analyzer_legacy import PictureAnalyzer  # noqa: F401 — explicit for clarity
