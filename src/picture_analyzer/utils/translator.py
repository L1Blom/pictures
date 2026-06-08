"""Translation utilities for metadata fields."""

from deep_translator import GoogleTranslator
import logging

logger = logging.getLogger(__name__)


def translate_metadata(metadata: dict, target_lang: str = "nl") -> dict:
    """Translate metadata dictionary fields from English to target language.
    
    Args:
        metadata: Dictionary with metadata fields
        target_lang: Target language code (e.g., 'nl' for Dutch, 'es' for Spanish)
    
    Returns:
        Dictionary with translated values
    """
    if target_lang == "en":
        return metadata  # No translation needed
    
    translator = GoogleTranslator(source="en", target=target_lang)
    translated = {}
    
    for key, value in metadata.items():
        if not value:
            translated[key] = value
            continue
            
        try:
            if isinstance(value, str):
                # Translate single string
                translated[key] = translator.translate(value)
            elif isinstance(value, list):
                # Translate list of strings
                translated[key] = [
                    translator.translate(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                # Keep as-is for other types
                translated[key] = value
        except Exception as e:
            logger.warning(f"Translation failed for {key}: {e} — keeping original")
            translated[key] = value
    
    return translated


def translate_analysis_dict(analysis: dict, target_lang: str = "nl") -> dict:
    """Translate metadata fields in an analysis dictionary.
    
    Translates:
    - All metadata field values
    - Location field local names (country, region, city_or_area)
    
    Keeps in English:
    - Enhancement recommendations (technical field)
    - Slide profiles (classification)
    """
    if target_lang == "en":
        return analysis  # No translation needed
    
    result = dict(analysis)
    
    # Translate metadata section
    if "metadata" in result and isinstance(result["metadata"], dict):
        result["metadata"] = translate_metadata(result["metadata"], target_lang)
    
    # Translate location names (country, region, city_or_area)
    # But keep these as location names, not full translations
    if "location_detection" in result and isinstance(result["location_detection"], dict):
        loc = result["location_detection"]
        # These are proper nouns/location names - translate if they're descriptions
        for field in ["country", "region", "city_or_area"]:
            if field in loc and isinstance(loc[field], str) and loc[field]:
                try:
                    translator = GoogleTranslator(source="en", target=target_lang)
                    # Only translate if it looks like a description (not a proper noun)
                    if any(char.islower() for char in loc[field]) and len(loc[field]) > 20:
                        loc[field] = translator.translate(loc[field])
                except Exception:
                    pass  # Keep original on error
        result["location_detection"] = loc
    
    return result
