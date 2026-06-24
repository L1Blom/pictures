"""Shared ``description.txt`` parsing helpers.

These helpers read structured fields (Albumnaam, Locatie, Datum) from a
``description.txt`` file and normalise them into values the rest of the
application can consume.

They are the single source of truth used by *both* the picture-analyzer
pipeline (``cli/app.py``) and the ``update_location.py`` post-processing
script, so the two code paths always agree on how location/date
information is extracted from a folder's description file.
"""
from __future__ import annotations

import re
from pathlib import Path


def read_description_field(desc_path: Path, *labels: str) -> str | None:
    """Return the first non-empty value for any of the given field labels.

    Matches lines like ``Locatie: Pruggern, Steiermark, Austria`` case- and
    label-insensitively.  ``labels`` may include aliases (e.g. ``"Locatie"``
    and ``"Location"``).
    """
    escaped = "|".join(re.escape(label) for label in labels)
    pattern = r"(?im)^(?:" + escaped + r")\s*:\s*(.+)$"
    text = desc_path.read_text(encoding="utf-8")
    match = re.search(pattern, text)
    if match:
        value = match.group(1).strip()
        return value if value else None
    return None


def extract_album_name(desc_path: Path) -> str | None:
    """Return the ``Albumnaam``/``Album name`` value, or None."""
    return read_description_field(desc_path, "Albumnaam", "Album name")


def extract_location(desc_path: Path) -> str | None:
    """Return the ``Locatie``/``Location`` value, or None."""
    return read_description_field(desc_path, "Locatie", "Location")


def extract_date(desc_path: Path) -> str | None:
    """Return the raw ``Datum``/``Date`` value (e.g. 'Juni 1984'), or None."""
    return read_description_field(desc_path, "Datum", "Date")


_MONTH_MAP = {
    "januari": 1, "februari": 2, "maart": 3, "april": 4, "mei": 5, "juni": 6,
    "juli": 7, "augustus": 8, "september": 9, "oktober": 10,
    "november": 11, "december": 12,
    "january": 1, "february": 2, "march": 3, "may": 5, "june": 6, "july": 7,
    "august": 8, "october": 10,
}


def parse_date(date_str: str) -> str | None:
    """Parse a date string into ``YYYY-MM-DD``. Supports:

    - 'Juni 1984' → '1984-06-01'
    - 'juni 1984' → '1984-06-01'
    - '1984' → '1984-01-01'
    - '1984-06' → '1984-06-01'
    - '1984-06-01' → '1984-06-01'
    - '03-01-1991' → '1991-01-03'
    - '29 september 1970' → '1970-09-29'
    - '20 maart 1998' → '1998-03-20'
    - '13 mei 1991' → '1991-05-13'
    - '6 september 1985' → '1985-09-06'
    """
    date_str = date_str.strip().lower()

    # Try to match "DD-MM-YYYY" (e.g., "03-01-1991")
    match = re.match(r"^(\d{2})-(\d{2})-(\d{4})$", date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month}-{day}"

    # Try to match "YYYY-MM-DD" (e.g., "1991-01-03")
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", date_str)
    if match:
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"

    # Try to match patterns like "29 september 1970" or "20 maart 1998"
    match = re.match(r"^(\d{1,2})\s+([a-z]+)\s+(\d{4})$", date_str)
    if match:
        day, month_name, year = match.groups()
        month = _MONTH_MAP.get(month_name)
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"

    # Try to match patterns like "Juni 1984" or "juni 1984"
    match = re.match(r"^([a-z]+)\s+(\d{4})$", date_str)
    if match:
        month_name, year = match.groups()
        month = _MONTH_MAP.get(month_name)
        if month:
            return f"{year}-{month:02d}-01"

    # Try to match "YYYY" (year only)
    match = re.match(r"^(\d{4})$", date_str)
    if match:
        year = match.group(1)
        return f"{year}-01-01"

    # Try to match "YYYY-MM" (year and month)
    match = re.match(r"^(\d{4})-(\d{2})$", date_str)
    if match:
        year, month = match.groups()
        return f"{year}-{month}-01"

    return None


def parse_location_parts(location_str: str) -> dict:
    """Split a 'city, region, country' string into location_detection fields.

    A ``/``-separated value is treated as a country-only list (e.g.
    'Nederland / België').  Returns a dict with ``country``, ``region``,
    ``city_or_area``, ``confidence`` (100) and ``reasoning``.
    """
    if "/" in location_str:
        country = " / ".join(p.strip() for p in location_str.split("/") if p.strip())
        return {"country": country, "region": "", "city_or_area": "", "confidence": 100,
                "reasoning": "Set from description.txt"}
    parts = [p.strip() for p in location_str.split(",") if p.strip()]
    result = {"country": "", "region": "", "city_or_area": "", "confidence": 100,
              "reasoning": "Set from description.txt"}
    if len(parts) >= 1:
        result["city_or_area"] = parts[0]
    if len(parts) >= 2:
        result["region"] = parts[1]
    if len(parts) >= 3:
        result["country"] = parts[2]
    return result
