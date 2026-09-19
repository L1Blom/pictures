"""Translation utilities for metadata fields."""

from deep_translator import GoogleTranslator
import logging
import os
import time

logger = logging.getLogger(__name__)

_MAX_RETRIES = 5
_RETRY_BASE_DELAY = 2.0  # seconds; exponential backoff: 2, 4, 8, 16
_MIN_REQUEST_INTERVAL = 0.5  # minimum seconds between network translation calls

# Ollama fallback configuration (used when Google + MyMemory are rate-limited).
# Reads from environment to avoid circular import with config loader.
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
_OLLAMA_MODEL = os.environ.get("OLLAMA_TRANSLATION_MODEL", "ministral-3:3b")

# In-memory cache: (text, target_lang) -> translation.
# Survives across images in the same process, so repeated values like
# "Netherlands", "Goes", "person" are translated once and reused.
_TRANSLATION_CACHE: dict[tuple[str, str], str] = {}

# Timestamp of the last network translation call (monotonic) for throttling.
_last_request_time: float = 0.0


def _throttle() -> None:
    """Ensure at least _MIN_REQUEST_INTERVAL between network translation calls."""
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_REQUEST_INTERVAL:
        time.sleep(_MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.monotonic()


def _translate_with_retry(translator, text: str, target_lang: str) -> str:
    """Translate text using the best available provider.

    Provider priority (when available):
    1. OpenAI gpt-4o-mini — high quality, no rate limits, ~$0.001/1000 fields
    2. Google Translate — free but rate-limited (retries with backoff)
    3. MyMemory — free but also rate-limited
    4. Local Ollama — free, no rate limits, lower quality

    Results are cached so repeated values across images are translated once.
    """
    cache_key = (text, target_lang)
    if cache_key in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[cache_key]

    # ── Primary: OpenAI (if API key available) ──────────────────────
    # Skip Google entirely — it's rate-limited and OpenAI is better quality.
    result = _translate_with_openai(text, target_lang)
    if result:
        _TRANSLATION_CACHE[cache_key] = result
        return result

    # ── Fallback: Google Translate with retries ─────────────────────
    for attempt in range(_MAX_RETRIES):
        try:
            _throttle()
            result = translator.translate(text)
            if result and result.strip():
                _TRANSLATION_CACHE[cache_key] = result
                return result
            logger.debug(
                "Google translation returned empty (attempt %d/%d)",
                attempt + 1, _MAX_RETRIES,
            )
        except Exception as e:
            logger.debug(
                "Google translation attempt %d/%d failed: %s",
                attempt + 1, _MAX_RETRIES, e,
            )
        if attempt < _MAX_RETRIES - 1:
            delay = _RETRY_BASE_DELAY * (2 ** attempt)
            time.sleep(delay)

    # ── Fallback: MyMemory translator ───────────────────────────────
    try:
        from deep_translator import MyMemoryTranslator

        _throttle()
        fallback = MyMemoryTranslator(source="en", target=target_lang)
        result = fallback.translate(text)
        if result and result.strip():
            logger.debug("MyMemory translation succeeded for text")
            _TRANSLATION_CACHE[cache_key] = result
            return result
    except Exception as e:
        logger.debug("MyMemory translation also failed: %s", e)

    # ── Last resort: Local Ollama model ─────────────────────────────
    result = _translate_with_ollama(text, target_lang)
    if result:
        _TRANSLATION_CACHE[cache_key] = result
        return result

    # All attempts failed — raise to let caller keep original
    raise RuntimeError("No translation was found using the current translator")


def _translate_with_openai(text: str, target_lang: str) -> str | None:
    """Translate text using OpenAI's API (gpt-4o-mini).

    High-quality translation with no rate limits. Costs ~$0.001 per 1000 fields.
    Reads the API key from OPENAI_APIKEY env var (same as the analyzer).
    """
    import os

    api_key = os.getenv("OPENAI_APIKEY", "")
    if not api_key:
        return None

    lang_names = {
        "nl": "Dutch",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
    }
    lang_name = lang_names.get(target_lang, target_lang)

    prompt = (
        f"Translate the following English text to {lang_name}. "
        f"Return ONLY the translation, no explanations, no quotes.\n\n"
        f"{text}"
    )

    try:
        from openai import OpenAI

        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
            temperature=0.3,
        )
        result = response.choices[0].message.content.strip()
        if result and result != text:
            logger.debug("OpenAI translation succeeded for text")
            return result
    except Exception as e:
        logger.debug("OpenAI translation fallback failed: %s", e)

    return None


def _translate_with_ollama(text: str, target_lang: str) -> str | None:
    """Translate text using a local Ollama model as a last-resort fallback.

    This avoids rate-limiting issues with Google Translate / MyMemory.
    Uses a simple prompt: the model is asked to translate and return ONLY
    the translation, no commentary.
    """
    lang_names = {
        "nl": "Dutch",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
    }
    lang_name = lang_names.get(target_lang, target_lang)

    prompt = (
        f"Translate the following English text to {lang_name}. "
        f"Return ONLY the translation, no explanations, no quotes.\n\n"
        f"{text}"
    )

    try:
        import ollama

        client = ollama.Client(host=_OLLAMA_HOST, timeout=120)
        response = client.chat(
            model=_OLLAMA_MODEL,
            messages=[{"role": "user", "content": prompt}],
            options={"num_ctx": 2048, "temperature": 0.3},
            keep_alive=0,  # don't keep this model loaded (pipeline uses its own)
        )
        result = response["message"]["content"].strip()
        if result and result != text:
            logger.debug("Ollama translation succeeded for text")
            return result
    except Exception as e:
        logger.debug("Ollama translation fallback failed: %s", e)

    return None


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
                translated[key] = _translate_with_retry(translator, value, target_lang)
            elif isinstance(value, list):
                # Translate list of strings
                translated[key] = [
                    _translate_with_retry(translator, item, target_lang) if isinstance(item, str) else item
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
        translator = GoogleTranslator(source="en", target=target_lang)
        # These are proper nouns/location names - translate if they're descriptions
        for field in ["country", "region", "city_or_area"]:
            if field in loc and isinstance(loc[field], str) and loc[field]:
                try:
                    # Only translate if it looks like a description (not a proper noun)
                    if any(char.islower() for char in loc[field]) and len(loc[field]) > 20:
                        loc[field] = _translate_with_retry(translator, loc[field], target_lang)
                except Exception:
                    pass  # Keep original on error
        result["location_detection"] = loc
    
    return result
