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

# Language Configuration
# Language for EXIF metadata content (e.g., 'en', 'nl', 'fr', 'de', 'es')
METADATA_LANGUAGE = os.getenv('METADATA_LANGUAGE', 'en')

# GPS Configuration
# Minimum confidence threshold for embedding GPS coordinates in EXIF (0-100)
GPS_CONFIDENCE_THRESHOLD = int(os.getenv('GPS_CONFIDENCE_THRESHOLD', '80'))

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
