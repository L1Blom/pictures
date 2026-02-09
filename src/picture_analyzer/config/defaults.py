"""Centralized default values for all configuration.

Every hardcoded value from the legacy codebase is collected here so there
is exactly ONE place to look up or change a default.  The Settings model
in ``settings.py`` references these constants as field defaults.
"""
from __future__ import annotations

# ── AI / OpenAI ──────────────────────────────────────────────────────
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_MAX_TOKENS = 4096
DEFAULT_DETAIL_LEVEL = "auto"  # "auto" | "low" | "high"

# ── Image Processing ────────────────────────────────────────────────
DEFAULT_JPEG_QUALITY = 95
DEFAULT_COLOR_TEMP_BASELINE = 6500  # Kelvin (daylight neutral)
DEFAULT_KELVIN_RANGE = (1500, 15000)
DEFAULT_CHANNEL_FACTOR_RANGE = (0.1, 2.5)
DEFAULT_UNSHARP_MASK = {"radius": 2, "percent": 150, "threshold": 3}
DEFAULT_DENOISE_RADIUS = 0.5

# ── Supported Formats ───────────────────────────────────────────────
DEFAULT_SUPPORTED_FORMATS = frozenset({
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp", ".heic",
})

# ── MIME Types ───────────────────────────────────────────────────────
MIME_TYPE_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".webp": "image/webp",
    ".heic": "image/heic",
}

# ── Language ─────────────────────────────────────────────────────────
DEFAULT_METADATA_LANGUAGE = "en"

LANGUAGE_NAMES = {
    "en": "English",
    "nl": "Dutch",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ja": "Japanese",
    "zh": "Chinese",
    "ru": "Russian",
}

# ── Geocoding ────────────────────────────────────────────────────────
DEFAULT_GEO_PROVIDER = "nominatim"
DEFAULT_GEO_CACHE_PATH = ".geocoding_cache.json"
DEFAULT_GEO_CONFIDENCE_THRESHOLD = 80  # 0–100
DEFAULT_GEO_USER_AGENT = "picture-analyzer/2.0"
DEFAULT_GEO_TIMEOUT = 5  # seconds
DEFAULT_GEO_MAX_RESULTS = 1

# Terms that indicate a location is too vague to geocode
DEFAULT_VAGUE_LOCATION_TERMS = frozenset({
    "uncertain", "unknown", "dichtbij", "near", "around", "approximately",
    "stadscentrum", "city center", "centrum", "ergens", "somewhere",
    "onbekend", "onzeker", "het", "de", "een",
})

# ── Metadata ─────────────────────────────────────────────────────────
DEFAULT_WRITE_EXIF = True
DEFAULT_WRITE_XMP = True
DEFAULT_WRITE_GPS = True
DEFAULT_DESCRIPTION_MAX_LENGTH = 16000
DEFAULT_DESCRIPTION_TRUNCATE_AT = 15800
DEFAULT_GPS_VERSION = (2, 3, 0, 0)
DEFAULT_GPS_DATUM = "WGS-84"
DEFAULT_USER_COMMENT_PREFIX = "PICTURE_ANALYSIS:"

# XMP Namespaces
XMP_NAMESPACE = "http://example.com/picture-analysis/1.0/"
XMP_DC_NAMESPACE = "http://purl.org/dc/elements/1.1/"
XMP_RDF_NAMESPACE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
XMP_ADOBE_NAMESPACE = "adobe:ns:meta/"

# ── Output / File Naming ────────────────────────────────────────────
DEFAULT_OUTPUT_DIR = "output"
DEFAULT_TEMP_DIR = "tmp"
DEFAULT_NAMING_PATTERN = "{stem}_analyzed{suffix}"
DEFAULT_ENHANCED_PATTERN = "{stem}_enhanced{suffix}"
DEFAULT_RESTORED_PATTERN = "{stem}_restored_{profile}{suffix}"
DEFAULT_THUMBNAILS_DIR = "thumbnails"
DEFAULT_THUMBNAIL_SIZE = 150
DEFAULT_THUMBNAIL_QUALITY = 85

# ── Batch Processing ────────────────────────────────────────────────
DEFAULT_BATCH_SIZE = 5
DEFAULT_CLEANUP_TEMP = True

# ── Slide Restoration ───────────────────────────────────────────────
DEFAULT_PROFILE_CONFIDENCE_THRESHOLD = 50  # for auto profile selection

DEFAULT_SLIDE_PROFILES = {
    "faded": {
        "name": "Faded Slide",
        "description": "For slides with significant color fading",
        "saturation": 1.5,
        "contrast": 1.6,
        "brightness": 1.15,
        "sharpness": 1.2,
        "color_balance": {"red": 1.0, "green": 1.05, "blue": 1.15},
        "denoise": True,
        "denoise_radius": 0.5,
    },
    "color_cast": {
        "name": "Color Cast",
        "description": "For slides with general color cast issues",
        "saturation": 1.3,
        "contrast": 1.4,
        "brightness": 1.1,
        "sharpness": 1.15,
        "color_balance": {"red": 1.0, "green": 1.05, "blue": 0.95},
        "denoise": True,
        "denoise_radius": 0.5,
    },
    "red_cast": {
        "name": "Red Cast",
        "description": "For slides with reddish/warm color cast",
        "saturation": 1.25,
        "contrast": 1.35,
        "brightness": 1.1,
        "sharpness": 1.15,
        "color_balance": {"red": 0.85, "green": 1.08, "blue": 1.12},
        "denoise": True,
        "denoise_radius": 0.5,
    },
    "yellow_cast": {
        "name": "Yellow Cast",
        "description": "For slides with yellowish aging cast",
        "saturation": 0.75,
        "contrast": 1.2,
        "brightness": 1.05,
        "sharpness": 1.1,
        "color_balance": {"red": 0.85, "green": 1.0, "blue": 1.25},
        "denoise": True,
        "denoise_radius": 0.5,
    },
    "aged": {
        "name": "Aged",
        "description": "For generally aged slides with mild degradation",
        "saturation": 1.25,
        "contrast": 1.3,
        "brightness": 1.08,
        "sharpness": 1.1,
        "color_balance": {"red": 1.0, "green": 1.02, "blue": 1.05},
        "denoise": True,
        "denoise_radius": 0.5,
    },
    "well_preserved": {
        "name": "Well Preserved",
        "description": "For slides in good condition needing minor touch-up",
        "saturation": 1.1,
        "contrast": 1.15,
        "brightness": 1.05,
        "sharpness": 1.08,
        "color_balance": {"red": 1.0, "green": 1.0, "blue": 1.0},
        "denoise": False,
        "denoise_radius": 0.5,
    },
}

# ── Prompt / Analysis ────────────────────────────────────────────────
DEFAULT_DETECT_SLIDE_PROFILES = True
DEFAULT_RECOMMEND_ENHANCEMENTS = True
DEFAULT_DETECT_LOCATION = True
DEFAULT_DETECT_PEOPLE = True
DEFAULT_DETECT_ERA = True

# Enhancement action keywords recognized in AI responses
ENHANCEMENT_KEYWORDS = frozenset({
    "brightness", "contrast", "saturation", "color_temperature",
    "sharpness", "noise_reduction", "red_channel", "blue_channel",
    "green_channel", "green_saturation", "unsharp_mask", "shadows",
    "highlights", "vibrance", "clarity", "yellow_cast_removal",
    "no_enhancements",
})

# Slide profile names (for prompt generation — auto-synced with profiles)
SLIDE_PROFILE_NAMES = frozenset(DEFAULT_SLIDE_PROFILES.keys())

# ── Web UI ───────────────────────────────────────────────────────────
DEFAULT_WEB_HOST = "127.0.0.1"
DEFAULT_WEB_PORT = 7000
DEFAULT_WEB_DEBUG = True
DEFAULT_WEB_THUMBNAIL_SIZE = 200
DEFAULT_WEB_THUMBNAIL_FORMAT = "PNG"
DEFAULT_WEB_PHOTOS_DIR = "."

# Dutch description template (default; can be overridden per language)
DEFAULT_DESCRIPTION_TEMPLATE = """Albumnaam: 
Locatie: 
Datum: 
Personen: 
Activiteit: 
Weer: 
Opmerkingen: 
Stemming: """

# ── Report ───────────────────────────────────────────────────────────
DEFAULT_REPORT_FORMAT = "markdown"
DEFAULT_REPORT_TEMPLATE = "default"
DEFAULT_REPORT_INCLUDE_THUMBNAILS = True
DEFAULT_REPORT_THUMBNAIL_MAX_SIZE = 300
DEFAULT_REPORT_BASE64_THUMBNAILS = True
DEFAULT_REPORT_FILENAME = "analysis_report.md"
DEFAULT_GALLERY_FILENAME = "gallery.md"

# ── Logging ──────────────────────────────────────────────────────────
DEFAULT_LOG_LEVEL = "INFO"

# ── EXIF Tag Mapping ────────────────────────────────────────────────
# Maps analysis field names to EXIF tag names
# (Used as reference; actual writing uses formatted description approach)
EXIF_TAG_MAPPING = {
    "title": "ImageDescription",
    "description": "ImageDescription",
    "subject": "XPSubject",
    "keywords": "XPKeywords",
    "time_of_day": "DateTime",
    "season_date": "DateTimeDigitized",
    "scene_type": "SceneCaptureType",
    "location_setting": "GPSInfo",
    "people": "XPAuthor",
    "photography_style": "Software",
    "composition_quality": "Comment",
}

# EXIF tags that can cause issues during writing
PROBLEMATIC_EXIF_TAGS = {282, 283, 296, 305, 306}

# ── Luminance / Color Science ────────────────────────────────────────
LUMINANCE_RED = 0.299
LUMINANCE_GREEN = 0.587
LUMINANCE_BLUE = 0.114
