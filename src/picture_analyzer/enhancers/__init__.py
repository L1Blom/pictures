"""Image enhancement: AI-guided enhancers, profile restorers, filters.

Key components:
  - ``FilterPipeline``:         Compose and apply image filters
  - ``RecommendationParser``:   Convert AI text → FilterPipeline
  - ``SlideRestorer``:          Restore scanned slides with typed profiles
  - ``filters``:                Individual ImageFilter implementations
"""
from .pipeline import FilterPipeline, RecommendationParser, enhance_image
from .profiles.slide_restorer import SlideRestorer

__all__ = [
    "FilterPipeline",
    "RecommendationParser",
    "SlideRestorer",
    "enhance_image",
]
