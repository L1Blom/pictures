"""
Configuration settings for the picture analysis application
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# OpenAI Configuration
OPENAI_API_KEY = os.getenv('OPENAI_APIKEY')
OPENAI_MODEL = 'gpt-4-vision-preview'

# Analysis Configuration
ANALYSIS_PROMPT = """Analyze this image and provide detailed information about the following aspects:

1. **Objects**: List all visible objects and items in the image
2. **Persons**: Identify if there are any people/persons visible and describe them briefly
3. **Weather**: Describe the weather conditions if visible (sunny, cloudy, rainy, etc.)
4. **Mood/Atmosphere**: Describe the mood, atmosphere, or feeling conveyed by the image
5. **Time of Day**: Estimate the time of day based on lighting (morning, afternoon, evening, night, etc.)
6. **Date/Season**: If there are any indicators, estimate the season or date period

Format your response as a structured JSON object with these keys:
objects, persons, weather, mood, time_of_day, date_season, additional_notes
"""

# EXIF Configuration
EXIF_TAG_MAPPING = {
    'objects': 'ImageDescription',
    'persons': 'Copyright',
    'weather': 'UserComment',
    'mood': 'ImageHistory',
    'time_of_day': 'DateTime',
    'date_season': 'DateTimeDigitized',
}

# Supported image formats
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp'}

# Output Configuration
OUTPUT_DIR = 'output'
TEMP_DIR = 'tmp'

# Validation
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_APIKEY not found in environment variables. Please set it in .env file")
