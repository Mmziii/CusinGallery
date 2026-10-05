"""
Iran provinces & main cities (Part R3).

The data lives in data/iran_locations.json: all 31 provinces, each with
its main cities, plus `aliases` mapping legacy/English spellings to the
Persian names. The file is deliberately EXTENDABLE -- adding a province,
city or alias there immediately updates the storefront selects and the
server validation below.

Validation policy (simplest option that never blocks a customer):
  * the province must be one of the known 31 (aliases like "Tehran" are
    accepted and normalised, keeping old addresses editable);
  * if the given city matches a KNOWN city (or alias), it must belong to
    the given province (catches mismatched selects);
  * any other city text is accepted -- the "other city" free-text path.
"""
import json
from functools import lru_cache
from pathlib import Path

DATA_FILE = Path(__file__).parent / "data" / "iran_locations.json"


@lru_cache(maxsize=1)
def _load_file():
    with open(DATA_FILE, encoding="utf-8") as fh:
        return json.load(fh)


def load_locations():
    return _load_file()["provinces"]


def province_names():
    return [province["name"] for province in load_locations()]


def cities_for(province):
    for entry in load_locations():
        if entry["name"] == province:
            return entry["cities"]
    return []


@lru_cache(maxsize=1)
def _known_city_map():
    mapping = {}
    for entry in load_locations():
        for city in entry["cities"]:
            mapping.setdefault(city, entry["name"])
    return mapping


def normalize_province(value):
    value = (value or "").strip()
    if value in province_names():
        return value
    return _load_file()["aliases"]["provinces"].get(value.lower(), value)


def normalize_city(value):
    value = (value or "").strip()
    if value in _known_city_map():
        return value
    return _load_file()["aliases"]["cities"].get(value.lower(), value)


def validate_province_city(province, city):
    """Returns an error string, or None when the pair is acceptable."""
    province = normalize_province(province)
    city = normalize_city(city)
    if province not in province_names():
        return "استان انتخاب‌شده معتبر نیست."
    owner = _known_city_map().get(city)
    if owner is not None and owner != province:
        return "شهر انتخاب‌شده متعلق به استان انتخاب‌شده نیست."
    return None
