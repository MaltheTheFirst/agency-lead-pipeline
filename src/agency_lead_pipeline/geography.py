from __future__ import annotations

import re
import unicodedata


# Broad geographic/business definition of Europe. UK constituent countries and
# common Clutch spelling variants are included explicitly.
EUROPEAN_COUNTRIES = {
    "albania", "andorra", "armenia", "austria", "azerbaijan", "belarus",
    "belgium", "bosnia and herzegovina", "bosnia & herzegovina", "bulgaria",
    "croatia", "cyprus", "czech republic", "czechia", "denmark", "england",
    "estonia", "finland", "france", "georgia", "germany", "greece",
    "hungary", "iceland", "ireland", "italy", "kosovo", "latvia",
    "liechtenstein", "lithuania", "luxembourg", "malta", "moldova",
    "monaco", "montenegro", "netherlands", "north macedonia", "northern ireland",
    "norway", "poland", "portugal", "romania", "russia", "san marino",
    "scotland", "serbia", "slovakia", "slovenia", "spain", "sweden",
    "switzerland", "turkey", "turkiye", "ukraine", "united kingdom",
    "vatican city", "wales",
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", value).strip().lower().strip(".")


def is_european_location(location: str) -> bool:
    """Match European countries in simple or multi-country location values."""
    if not location.strip():
        return False
    normalized = _normalize(location)
    parts = re.split(r"[,;/|]|\band\b", normalized)
    for part in parts:
        country = re.sub(r"\s*\+\d+$", "", part).strip()
        if country in {"uk", "u.k.", "gb", "great britain"}:
            country = "united kingdom"
        if country in EUROPEAN_COUNTRIES:
            return True
    return False

