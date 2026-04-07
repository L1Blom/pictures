"""
Prompts for image analysis

.. deprecated::
    Import ``PromptLoader`` from ``picture_analyzer.data`` instead.
    ``ANALYSIS_PROMPT`` is kept for backward compatibility with legacy code
    (``picture_analyzer_legacy.py``, root-level scripts) but is now assembled
    from the split template files under
    ``src/picture_analyzer/data/templates/``.
"""
import warnings as _warnings
from pathlib import Path as _Path
import sys as _sys

_warnings.warn(
    "Importing 'ANALYSIS_PROMPT' from the root 'prompts' module is deprecated and "
    "will be removed in a future version. Use "
    "'from picture_analyzer.data.prompt_loader import PromptLoader' instead.",
    DeprecationWarning,
    stacklevel=2,
)


def _load_analysis_prompt() -> str:
    # Make the installed package importable when running from the repo root
    _src = str(_Path(__file__).resolve().parent / "src")
    if _src not in _sys.path:
        _sys.path.insert(0, _src)
    from picture_analyzer.data.prompt_loader import PromptLoader
    return PromptLoader().combined(language="{language}")

ANALYSIS_PROMPT = _load_analysis_prompt()
