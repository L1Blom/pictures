"""AnalysisPipeline — sequences steps and accumulates AnalysisResult.

Usage::

    from picture_analyzer.pipeline import build_pipeline

    pipeline = build_pipeline(settings)
    result = pipeline.run(image_data, context)
"""
from __future__ import annotations

import logging
import sys
import time
from datetime import datetime

_RETRY_WAIT = 30  # seconds to wait before retrying on timeout
_TIMEOUT_NAMES = ("ReadTimeout", "ConnectTimeout", "TimeoutException", "Timeout")


def _print(msg: str) -> None:
    """Print pipeline progress to stderr (visible in terminal, not in captured stdout)."""
    print(msg, file=sys.stderr, flush=True)


def _format_tok_stats(step) -> str:
    """Return a token/speed summary string from the last analyzer call on a step, or ''."""
    analyzer = getattr(step, "_analyzer", None)
    stats = getattr(analyzer, "_last_call_stats", None)
    if not stats:
        return ""
    in_t = stats.get("prompt_tokens")
    out_t = stats.get("output_tokens")
    ev_ns = stats.get("eval_duration_ns")
    parts = []
    if in_t is not None and out_t is not None:
        parts.append(f"{in_t}→{out_t} tok")
    if out_t and ev_ns:
        parts.append(f"{out_t / (ev_ns / 1e9):.1f} tok/s")
    return f"  ({', '.join(parts)})" if parts else ""

from ..core.models import AnalysisContext, AnalysisResult, ImageData
from ..config.settings import Settings
from .steps import build_steps
from .geo_step import GeocodingStep

logger = logging.getLogger(__name__)


class AnalysisPipeline:
    """Runs a sequence of :class:`AnalysisStep` objects in order.

    Each step receives the accumulated ``AnalysisResult`` from the
    previous step and returns an updated copy.  Steps that are disabled
    or whose context flag is off return the partial result unchanged.
    """

    def __init__(self, steps: list) -> None:
        self._steps = steps

    def run(self, image: ImageData, context: AnalysisContext) -> AnalysisResult:
        """Execute all steps, accumulating a single ``AnalysisResult``.

        Args:
            image: Image to analyse (base64 encoding handled by each step).
            context: Flags and language settings for the analysis.

        Returns:
            Merged ``AnalysisResult`` with all available fields populated.
        """
        partial = AnalysisResult(analyzed_at=datetime.now())
        total_start = time.perf_counter()
        for step in self._steps:
            step_name = getattr(step, "name", repr(step))
            logger.debug("Pipeline: running step '%s'", step_name)
            _print(f"  → [{step_name}] starting at {time.strftime('%H:%M:%S')}")
            t0 = time.perf_counter()
            try:
                partial = step.run(image, context, partial)
                elapsed = time.perf_counter() - t0
                logger.info("Pipeline: step '%s' completed in %.3fs", step_name, elapsed)
                _print(f"  ✓ [{step_name}] done in {elapsed:.1f}s{_format_tok_stats(step)}")
            except Exception as exc:
                elapsed = time.perf_counter() - t0
                is_timeout = any(
                    name in type(exc).__name__
                    for name in _TIMEOUT_NAMES
                )
                if is_timeout:
                    _print(f"  ⚠ [{step_name}] timed out after {elapsed:.0f}s — waiting {_RETRY_WAIT}s then retrying")
                    logger.warning(
                        "Pipeline: step '%s' timed out after %.3fs — waiting %ds then retrying once",
                        step_name, elapsed, _RETRY_WAIT,
                    )
                    time.sleep(_RETRY_WAIT)
                    try:
                        t0 = time.perf_counter()
                        partial = step.run(image, context, partial)
                        elapsed = time.perf_counter() - t0
                        logger.info("Pipeline: step '%s' completed on retry in %.3fs", step_name, elapsed)
                        _print(f"  ✓ [{step_name}] done on retry in {elapsed:.1f}s{_format_tok_stats(step)}")
                        continue
                    except Exception:
                        elapsed = time.perf_counter() - t0
                        _print(f"  ✗ [{step_name}] failed on retry after {elapsed:.0f}s — skipping")
                        logger.exception(
                            "Pipeline: step '%s' failed on retry after %.3fs — skipping",
                            step_name, elapsed,
                        )
                else:
                    _print(f"  ✗ [{step_name}] error after {elapsed:.1f}s — skipping")
                    logger.exception(
                        "Pipeline: step '%s' raised an exception after %.3fs — skipping",
                        step_name,
                        elapsed,
                    )
        total_elapsed = time.perf_counter() - total_start
        _print(f"  Pipeline total: {total_elapsed:.1f}s")
        # Carry description_text through so callers can embed it in EXIF
        if context.description_text and partial.description_context is None:
            partial = partial.model_copy(update={"description_context": context.description_text})
        return partial


def build_pipeline(settings: Settings) -> AnalysisPipeline:
    """Construct a ready-to-use :class:`AnalysisPipeline` from *settings*.

    The canonical step order is:
    1. MetadataStep
    2. LocationStep
    3. EnhancementStep
    4. SlideProfileStep
    5. GeocodingStep  (no LLM)

    Args:
        settings: Root settings instance.

    Returns:
        Configured :class:`AnalysisPipeline`.
    """
    steps = build_steps(settings)
    steps.append(GeocodingStep(settings))
    return AnalysisPipeline(steps)
