"""picture_analyzer - AI-powered photo analysis, enhancement, and metadata embedding.

Public API::

    from picture_analyzer import __version__
    from picture_analyzer.analyzers import OpenAIAnalyzer
    from picture_analyzer.geo import NominatimGeocoder
    from picture_analyzer.metadata import ExifWriter, XmpWriter
    from picture_analyzer.enhancers import FilterPipeline, RecommendationParser, SlideRestorer
    from picture_analyzer.enhancers.filters import BrightnessFilter, ContrastFilter, ...
    from picture_analyzer.core.models import AnalysisResult, ImageData, AnalysisContext, ...
    from picture_analyzer.core.interfaces import Analyzer, Geocoder, MetadataWriter, ...
    from picture_analyzer.config.settings import get_settings
"""

__version__ = "2.0.0"
__all__ = ["__version__"]
