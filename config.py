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

=== ENHANCEMENT RECOMMENDATIONS SECTION (DETAILED & QUANTIFIABLE) ===
12. **Lighting Quality Assessment**: 
    - Current state: underexposed/properly exposed/overexposed
    - Specific measurements: estimated EV adjustment needed (-1.5 to +1.5)
    - Shadow detail: crushed/normal/blown out
    - Specific recommendation: e.g., "increase brightness by 25-30%", "reduce highlights by 15%"

13. **Color & White Balance Analysis**:
    - Dominant colors and their intensity
    - Color temperature assessment: warm (K), neutral (K), cool (K) - estimate Kelvin temperature
    - Detected color casts: none/slight warm/strong warm/slight cool/strong cool
    - Saturation level: desaturated (recommend +40-50%)/normal/oversaturated (recommend -20-30%)
    - Specific correction: e.g., "shift color temperature 500K cooler", "reduce red channel by 10%", "boost cyan in shadows"

14. **Sharpness, Clarity & Noise**:
    - Overall sharpness: soft/slightly soft/sharp/oversharpened
    - Specific areas with blur (if any): specify location and severity
    - Noise assessment: none/minimal/moderate/high - recommend noise reduction if needed
    - Clarity recommendation: e.g., "apply unsharp mask (radius=1.5, amount=80%)", "boost local contrast by 20%"
    - Specific recommendation: e.g., "increase sharpness by 30%", "apply moderate noise reduction"

15. **Contrast Enhancement**:
    - Current contrast level: very low/low/normal/high/very high
    - Recommended adjustment: specific percentage e.g., "increase contrast by 25%"
    - Shadow/midtone/highlight adjustments if needed: e.g., "brighten shadows by 15%, boost highlights by 10%"
    - Local contrast enhancement: recommend unsharp mask or clarity boost with specific values

16. **Composition & Technical Issues**:
    - Any visible defects: dust spots, scratches, artifacts, distortion
    - Vignetting: none/slight/moderate/strong - recommend correction %
    - Chromatic aberration: none/slight/present - recommend correction approach
    - Straightness: perfectly level/slightly tilted/noticeably tilted
    - Specific fixes needed: e.g., "remove 2-3 dust spots", "correct 2-degree tilt"

17. **Recommended Enhancements** (prioritized list with specific parameters):
    - Format each as: "ACTION: specific parameter (value)" 
    - Examples: 
      * "BRIGHTNESS: increase by 25%"
      * "CONTRAST: boost by 20%"
      * "SATURATION: increase by 15%"
      * "COLOR_TEMPERATURE: warm by 500K"
      * "SHARPNESS: increase by 30%"
      * "NOISE_REDUCTION: apply moderate filter"
      * "UNSHARP_MASK: radius=1.5px, strength=80%, threshold=0"
      * "SHADOWS: brighten by 15%"
      * "HIGHLIGHTS: reduce by 10%"
      * "VIBRANCE: increase by 25%"
      * "CLARITY: boost by 20%"
    - List in order of priority/impact

18. **Overall Enhancement Priority**:
    - Which issue is most critical to fix first
    - Estimated improvement percentage if all recommendations applied
    - Preservation notes: aspects that should NOT be changed to maintain character

=== SLIDE RESTORATION PROFILES (if this appears to be a scanned slide/dia positive) ===
19. **Suggested Profiles**: List the most suitable slide restoration profiles with confidence scores (0-100%).
    Available profiles: faded (very faded with lost color/contrast), color_cast (generic color casts), red_cast (red/magenta aging), yellow_cast (yellow/warm aging), aged (moderate aging), well_preserved (minimal aging).
    Format: [{"profile": "profile_name", "confidence": 85}, {"profile": "profile_name", "confidence": 60}]
    Only include this section if the image appears to be a scanned slide or vintage photograph. If uncertain or not a slide, set to empty array: []

Format your response as a structured JSON object with three top-level keys:
- "metadata": {objects, persons, weather, mood, time_of_day, season_date, scene_type, location_setting, activity, photography_style, composition_quality}
- "enhancement": {lighting_quality, color_analysis, sharpness_clarity, contrast_level, composition_issues, recommended_enhancements, overall_priority}
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
OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'output')
TEMP_DIR = os.getenv('TEMP_DIR', 'tmp')

# Gallery/Thumbnail Configuration
THUMBNAILS_DIR = os.getenv('THUMBNAILS_DIR', 'thumbnails')  # Subdirectory name for thumbnails
THUMBNAIL_SIZE = int(os.getenv('THUMBNAIL_SIZE', '150'))  # Size of thumbnails in pixels
THUMBNAIL_QUALITY = int(os.getenv('THUMBNAIL_QUALITY', '85'))  # JPEG quality for thumbnails (1-100)

# Processing Configuration
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '5'))  # Number of images to process in parallel
TEMP_DIR_CLEANUP = os.getenv('TEMP_DIR_CLEANUP', 'true').lower() == 'true'  # Auto-cleanup temp files

# Validation
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_APIKEY not found in environment variables. Please set it in .env file")
