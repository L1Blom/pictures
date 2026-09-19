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
    if isinstance(in_t, (int, float)) and isinstance(out_t, (int, float)):
        parts.append(f"{in_t}→{out_t} tok")
    if isinstance(out_t, (int, float)) and out_t and isinstance(ev_ns, (int, float)) and ev_ns:
        parts.append(f"{out_t / (ev_ns / 1e9):.1f} tok/s")
    return f"  ({', '.join(parts)})" if parts else ""

from ..core.models import AnalysisContext, AnalysisResult, ImageData
from ..core.exceptions import AnalysisError
from ..config.settings import Settings
from .steps import build_steps
from .geo_step import GeocodingStep

logger = logging.getLogger(__name__)


def _merge_results(base: AnalysisResult, overlay: AnalysisResult) -> AnalysisResult:
    """Field-wise merge of two ``AnalysisResult`` objects.

    Used after a parallel wave: each step read from the same snapshot, so
    their outputs must be combined rather than replacing one with another.
    For each field, the overlay's value wins when it is non-empty/truthy;
    otherwise the base value is kept.  ``raw_response`` dicts are deep-merged.
    """
    import pydantic

    updates: dict = {}
    for field_name in AnalysisResult.model_fields:
        if field_name in ("analyzed_at", "source_path", "description_context"):
            # Never overwrite these from a parallel step — they are set by the
            # pipeline / caller, not by individual steps.
            continue
        base_val = getattr(base, field_name)
        overlay_val = getattr(overlay, field_name)
        if field_name == "raw_response":
            merged_raw = dict(base_val) if isinstance(base_val, dict) else {}
            if isinstance(overlay_val, dict):
                for k, v in overlay_val.items():
                    if k in merged_raw and isinstance(merged_raw[k], dict) and isinstance(v, dict):
                        # Deep merge: only update with non-empty values
                        for sk, sv in v.items():
                            if sv or sk not in merged_raw[k]:
                                merged_raw[k][sk] = sv
                    elif v or k not in merged_raw:
                        merged_raw[k] = v
            updates[field_name] = merged_raw
        elif isinstance(overlay_val, list) and overlay_val:
            updates[field_name] = overlay_val
        elif isinstance(overlay_val, str) and overlay_val:
            updates[field_name] = overlay_val
        elif overlay_val is not None and not isinstance(overlay_val, (list, str, dict)):
            updates[field_name] = overlay_val
        elif isinstance(overlay_val, dict) and overlay_val:
            updates[field_name] = overlay_val
    return base.model_copy(update=updates)


class AnalysisPipeline:
    """Runs a sequence of :class:`AnalysisStep` objects, accumulating an AnalysisResult.

    Each step receives the accumulated ``AnalysisResult`` from previous steps
    and returns an updated copy.  Steps that are disabled or whose context
    flag is off return *partial* unchanged.

    When ``parallel_workers > 1``, steps with no unmet dependencies run
    concurrently in a :class:`ThreadPoolExecutor`.  Each step declares its
    dependencies via a ``depends_on`` attribute (a list of step names that
    must complete first).  The scheduler runs steps in waves: at each wave
    every step whose dependencies are all done is eligible.  This is safe
    because the LLM calls are I/O-bound and release the GIL while waiting
    on HTTP responses.
    """

    def __init__(self, steps: list, parallel_workers: int = 1) -> None:
        self._steps = steps
        self._parallel_workers = max(1, parallel_workers)

    def _run_step_once(
        self,
        step,
        image: ImageData,
        context: AnalysisContext,
        partial: AnalysisResult,
    ) -> AnalysisResult:
        """Run *step* once, returning an updated ``AnalysisResult``.

        Handles the timeout-retry-once behaviour.  On a non-timeout error
        (or a timeout that also fails on retry) the exception is allowed
        to propagate to the caller, which treats the step as failed.
        """
        step_name = getattr(step, "name", repr(step))
        t0 = time.perf_counter()
        try:
            result = step.run(image, context, partial)
            elapsed = time.perf_counter() - t0
            logger.info("Pipeline: step '%s' completed in %.3fs", step_name, elapsed)
            _print(f"  ✓ [{step_name}] done in {elapsed:.1f}s{_format_tok_stats(step)}")
            return result
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
                t0 = time.perf_counter()
                try:
                    result = step.run(image, context, partial)
                    elapsed = time.perf_counter() - t0
                    logger.info("Pipeline: step '%s' completed on retry in %.3fs", step_name, elapsed)
                    _print(f"  ✓ [{step_name}] done on retry in {elapsed:.1f}s{_format_tok_stats(step)}")
                    return result
                except Exception as retry_exc:
                    elapsed = time.perf_counter() - t0
                    _print(f"  ✗ [{step_name}] failed on retry after {elapsed:.0f}s — skipping")
                    logger.exception(
                        "Pipeline: step '%s' failed on retry after %.3fs — skipping",
                        step_name, elapsed,
                    )
                    raise AnalysisError(
                        f"Step '{step_name}' timed out and failed on retry"
                    ) from retry_exc
            else:
                _print(f"  ✗ [{step_name}] error after {elapsed:.1f}s — skipping")
                logger.exception(
                    "Pipeline: step '%s' raised an exception after %.3fs — skipping",
                    step_name,
                    elapsed,
                )
                raise AnalysisError(f"Step '{step_name}' failed: {exc}") from exc

    def run(
        self,
        image: ImageData,
        context: AnalysisContext,
        partial: AnalysisResult | None = None,
        only_steps: list[str] | None = None,
    ) -> AnalysisResult:
        """Execute all steps, accumulating a single ``AnalysisResult``.

        Args:
            image: Image to analyse (base64 encoding handled by each step).
            context: Flags and language settings for the analysis.
            partial: Optional existing result to use as starting state.
                     When provided, steps merge into it rather than starting fresh.
                     Pass the output of :func:`~picture_analyzer.pipeline.load_partial_from_json`
                     to re-run only specific steps on an already-analyzed image.
            only_steps: If given, only steps whose ``name`` is in this list are
                        executed.  All other steps are skipped (their partial
                        result passes through unchanged).  Example::

                            pipeline.run(image, ctx, only_steps=["metadata", "slide_profiles"])

        Returns:
            Merged ``AnalysisResult`` with all available fields populated.
        """
        if partial is None:
            partial = AnalysisResult(analyzed_at=datetime.now())
        total_start = time.perf_counter()

        # Build the list of steps to execute, honouring only_steps.
        # only_steps filters which steps run; dependencies are still resolved
        # against the full step set so a step whose dependency is filtered out
        # becomes immediately eligible (the dependency is treated as satisfied).
        only_set = set(only_steps) if only_steps is not None else None
        steps_to_run = []
        for step in self._steps:
            step_name = getattr(step, "name", repr(step))
            if only_set is not None and step_name not in only_set:
                logger.debug("Pipeline: skipping step '%s' (not in only_steps)", step_name)
                continue
            steps_to_run.append(step)

        # Wave-based scheduler: at each wave, run every step whose
        # dependencies have all completed.  Completed = finished (success or
        # failure); a failed dependency still unblocks its dependents (they
        # just won't see its data, matching the old "skip and continue" behaviour).
        completed: set[str] = set()
        remaining = list(steps_to_run)
        # Track each step's result so we can merge in dependency order.
        # A step that fails produces no result entry.
        results: dict[str, AnalysisResult] = {}

        while remaining:
            # Find eligible steps: dependencies satisfied (or not in the
            # execution set at all, e.g. filtered by only_steps).
            eligible = []
            for step in remaining:
                deps_raw = getattr(step, "depends_on", None)
                deps = set(deps_raw) if isinstance(deps_raw, (list, tuple, set, frozenset)) else set()
                if deps <= completed:
                    eligible.append(step)
            if not eligible:
                # Should not happen with a well-formed DAG, but guard against
                # a deadlock by running remaining steps in order.
                eligible = remaining

            # Determine the snapshot of partial each eligible step reads from.
            # All eligible steps in a wave read the SAME accumulated partial
            # (the merge of all previously completed steps).  This mirrors the
            # sequential behaviour where independent steps don't see each
            # other's results within the same wave.
            wave_partial = partial

            if len(eligible) == 1 or self._parallel_workers == 1:
                # Sequential path: each step sees the accumulated partial from
                # the previous step (matches the original behaviour).
                for step in eligible:
                    step_name = getattr(step, "name", repr(step))
                    logger.debug("Pipeline: running step '%s'", step_name)
                    _print(f"  → [{step_name}] starting at {time.strftime('%H:%M:%S')}")
                    try:
                        step_result = self._run_step_once(step, image, context, partial)
                        results[step_name] = step_result
                        partial = step_result
                    except AnalysisError:
                        # Step failed and was logged; skip it (no merge).
                        pass
                    completed.add(step_name)
                    remaining.remove(step)
            else:
                # Parallel wave: run eligible steps concurrently.
                from concurrent.futures import ThreadPoolExecutor, as_completed

                started_names = []
                for step in eligible:
                    step_name = getattr(step, "name", repr(step))
                    logger.debug("Pipeline: running step '%s' (parallel)", step_name)
                    _print(f"  → [{step_name}] starting at {time.strftime('%H:%M:%S')}")
                    started_names.append(step_name)

                with ThreadPoolExecutor(max_workers=self._parallel_workers) as pool:
                    future_to_step = {
                        pool.submit(
                            self._run_step_once, step, image, context, wave_partial
                        ): step
                        for step in eligible
                    }
                    for fut in as_completed(future_to_step):
                        step = future_to_step[fut]
                        step_name = getattr(step, "name", repr(step))
                        try:
                            step_result = fut.result()
                            results[step_name] = step_result
                        except AnalysisError:
                            # Step failed and was logged inside _run_step_once.
                            pass
                        completed.add(step_name)
                        remaining.remove(step)

                # Merge completed wave results into partial.  Each step in a
                # parallel wave read from the same snapshot, so their results
                # must be field-merged (not replaced) to preserve data from
                # every step.  Merge in declaration order for determinism.
                for step in eligible:
                    step_name = getattr(step, "name", repr(step))
                    if step_name in results:
                        partial = _merge_results(partial, results[step_name])

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
    3. SlideProfileStep
    4. EnhancementStep   (depends on slide_profiles)
    5. GeocodingStep      (depends on location; no LLM)

    Args:
        settings: Root settings instance.

    Returns:
        Configured :class:`AnalysisPipeline`.
    """
    steps = build_steps(settings)
    steps.append(GeocodingStep(settings))
    return AnalysisPipeline(steps, parallel_workers=settings.pipeline.parallel_workers)
