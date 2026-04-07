"""Stepped analysis pipeline for picture_analyzer.

Public API::

    from picture_analyzer.pipeline import build_pipeline, AnalysisPipeline

    pipeline = build_pipeline(settings)
    result   = pipeline.run(image_data, context)
"""
from .pipeline import AnalysisPipeline, build_pipeline  # noqa: F401
from .protocols import AnalysisStep  # noqa: F401
