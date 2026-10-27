"""Address sanity check. Census geocoder first, ZIP3 table if it is slow or down."""

from __future__ import annotations

import json
from functools import lru_cache

import httpx

from app.config import ZIP3_PATH, Settings
from app.services.normalization import parse_state, parse_zip

CENSUS_URL = "https://geocoding.geo.census.gov/geocoder/locations/address"


@lru_cache
def zip3_to_state() -> dict[str, str]:
    raw = json.loads(ZIP3_PATH.read_text(encoding="utf-8"))
    lookup: dict[str, str] = {}
    for state, prefixes in raw.items():
        for prefix in prefixes:
            lookup[str(prefix).zfill(3)] = state
    return lookup


def state_for_zip(zip_code: str) -> str | None:
    digits = "".join(char for char in zip_code if char.isdigit())
    if len(digits) < 3:
        return None
    return zip3_to_state().get(digits[:3])


def _census(line1: str, city: str, state: str, zip_code: str, timeout: float) -> dict | None:
    try:
        response = httpx.get(
            CENSUS_URL,
            params={
                "street": line1,
                "city": city,
                "state": state,
                "zip": zip_code[:5],
                "benchmark": "Public_AR_Current",
                "format": "json",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        matches = response.json().get("result", {}).get("addressMatches", [])
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    if not matches:
        return None
    match = matches[0]
    components = match.get("addressComponents") or {}
    return {
        "matched_address": match.get("matchedAddress"),
        "city": components.get("city"),
        "state": components.get("state"),
        "zip": components.get("zip"),
    }


def check_address(
    line1: str,
    city: str,
    state: str,
    zip_code: str,
    settings: Settings,
) -> dict:
    state_parsed = parse_state(state)
    zip_parsed = parse_zip(zip_code)
    if not state_parsed.value:
        return {
            "ok": False,
            "source": "local",
            "say": state_parsed.reason or "I need a two-letter state.",
        }
    if not zip_parsed.value:
        return {
            "ok": False,
            "source": "local",
            "say": zip_parsed.reason or "I need a five-digit ZIP code.",
        }
    state_code = state_parsed.value
    zip_value = zip_parsed.value
    expected = state_for_zip(zip_value)
    if expected and expected != state_code:
        return {
            "ok": False,
            "source": "zip3",
            "zip_state": expected,
            "given_state": state_code,
            "say": f"{zip_value[:5]} is a {expected} ZIP, but the state I have is {state_code}. Which one should I keep?",
        }

    match = _census(line1, city, state_code, zip_value, settings.census_timeout_seconds)
    if match and match.get("matched_address"):
        return {
            "ok": True,
            "verified": True,
            "source": "census",
            "suggestion": match["matched_address"],
            "say": f"The geocoder found {match['matched_address']}. Should I use that?",
        }
    if expected:
        return {
            "ok": True,
            "verified": False,
            "source": "zip3",
            "say": f"The ZIP and {state_code} match. I couldn't confirm the street just now, so please listen for it on the read-back.",
        }
    return {
        "ok": True,
        "verified": False,
        "source": "none",
        "say": "I couldn't verify that ZIP from here. Please confirm the city, state, and ZIP together.",
    }
