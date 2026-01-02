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

=== ENHANCEMENT RECOMMENDATIONS SECTION ===
7. **Lighting Quality**: Assess brightness (underexposed/normal/overexposed), shadow detail, highlight clipping
8. **Color Analysis**: Dominant colors, color temperature (warm/cool/neutral), saturation level (dull/normal/vibrant)
9. **Sharpness & Clarity**: Overall sharpness assessment, any blur, noise level, clarity issues
10. **Contrast Level**: Current contrast (low/normal/high), suggested adjustment percentage
11. **Composition Issues**: Any visible defects, artifacts, or areas needing attention
12. **Recommended Enhancements**: Specific suggestions like "increase brightness by 20%", "add contrast", "reduce noise", "warm up colors", etc.

Format your response as a structured JSON object with two top-level keys:
- "metadata": {objects, persons, weather, mood, time_of_day, season_date}
- "enhancement": {lighting_quality, color_analysis, sharpness_clarity, contrast_level, composition_issues, recommended_enhancements}
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
}

# Supported image formats
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.heic'}

# Output Configuration
OUTPUT_DIR = 'output'
TEMP_DIR = 'tmp'

# Validation
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_APIKEY not found in environment variables. Please set it in .env file")
