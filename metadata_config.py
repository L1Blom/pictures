"""
Metadata and EXIF configuration
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
