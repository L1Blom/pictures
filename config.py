"""
Configuration settings for the picture analysis application
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_APIKEY')
OPENAI_MODEL = 'gpt-4-turbo'

# Analysis Configuration
ANALYSIS_PROMPT = """Analyze this image and provide detailed information in two separate sections:

=== METADATA SECTION (for EXIF embedding) ===
1. **Objects**: List all visible objects and items in the image
2. **Persons**: Identify if there are any people/persons visible and describe them briefly
3. **Weather**: Describe the weather conditions if visible (sunny, cloudy, rainy, etc.)
4. **Mood/Atmosphere**: Describe the mood, atmosphere, or feeling conveyed by the image
5. **Time of Day**: Estimate the time of day based on lighting (morning, afternoon, evening, night, etc.)
6. **Season/Date**: If there are any indicators, estimate the season or date period
7. **Scene Type**: Classify the type of scene (portrait, landscape, macro, wildlife, still-life, action, candid, street, architecture, food, travel, etc.)
8. **Location/Setting**: Identify where this is - indoor/outdoor, urban/rural/nature, specific environment type
9. **Activity/Action**: Describe what's happening or the main activity in the photo (if any)
10. **Photography Style**: Identify the photography style or technique (e.g., portrait photography, landscape photography, macro photography, documentary, fine art, etc.)
11. **Composition Quality**: Rate the composition quality (excellent, good, fair, needs work) and note key compositional elements (rule of thirds, leading lines, symmetry, depth, framing, etc.)

=== ENHANCEMENT RECOMMENDATIONS SECTION ===
12. **Lighting Quality**: Assess brightness (underexposed/normal/overexposed), shadow detail, highlight clipping
13. **Color Analysis**: Dominant colors, color temperature (warm/cool/neutral), saturation level (dull/normal/vibrant)
14. **Sharpness & Clarity**: Overall sharpness assessment, any blur, noise level, clarity issues
15. **Contrast Level**: Current contrast (low/normal/high), suggested adjustment percentage
16. **Composition Issues**: Any visible defects, artifacts, or areas needing attention
17. **Recommended Enhancements**: Specific suggestions like "increase brightness by 20%", "add contrast", "reduce noise", "warm up colors", etc.

=== SLIDE RESTORATION PROFILES (if this appears to be a scanned slide/dia positive) ===
18. **Suggested Profiles**: List the most suitable slide restoration profiles with confidence scores (0-100%).
    Available profiles: faded (very faded with lost color/contrast), color_cast (generic color casts), red_cast (red/magenta aging), yellow_cast (yellow/warm aging), aged (moderate aging), well_preserved (minimal aging).
    Format: [{"profile": "profile_name", "confidence": 85}, {"profile": "profile_name", "confidence": 60}]
    Only include this section if the image appears to be a scanned slide or vintage photograph. If uncertain or not a slide, set to empty array: []

Format your response as a structured JSON object with three top-level keys:
- "metadata": {objects, persons, weather, mood, time_of_day, season_date, scene_type, location_setting, activity, photography_style, composition_quality}
- "enhancement": {lighting_quality, color_analysis, sharpness_clarity, contrast_level, composition_issues, recommended_enhancements}
- "slide_profiles": [] (array of profile recommendations with confidence scores, empty if not a slide)
"""

# EXIF Configuration
# Only metadata is stored in EXIF tags
EXIF_TAG_MAPPING = {
    'objects': 'ImageDescription',
    'persons': 'Copyright',
    'weather': 'UserComment',
    'mood': 'ImageHistory',
    'time_of_day': 'DateTime',
    'season_date': 'DateTimeDigitized',
    'scene_type': 'SceneCaptureType',
    'location_setting': 'GPSInfo',
    'activity': 'ImageDescription',
    'photography_style': 'Software',
    'composition_quality': 'Comment',
}

# Supported image formats
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic'}

# Output Configuration
OUTPUT_DIR = 'output'
TEMP_DIR = 'tmp'

# Validation
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_APIKEY not found in environment variables. Please set it in .env file")
