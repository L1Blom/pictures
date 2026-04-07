"""Protocol definitions for the stepped analysis pipeline."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..core.models import AnalysisContext, AnalysisResult, ImageData


@runtime_checkable
class AnalysisStep(Protocol):
    """A single step in the analysis pipeline.

    Each step receives the image, the analysis context, and the
    accumulated ``AnalysisResult`` so far, and returns an updated copy.

    Steps that are disabled (``StepConfig.enabled=False``) or whose
    matching context flag is off should return *partial* unchanged.
    """

    name: str

    def run(
        self,
        image: ImageData,
        context: AnalysisContext,
        partial: AnalysisResult,
    ) -> AnalysisResult: ...
