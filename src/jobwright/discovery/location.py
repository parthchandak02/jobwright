"""Shared location accept/reject filtering for discovery sources."""

from __future__ import annotations

import re

# Remote markers accepted after reject patterns pass.
_REMOTE_MARKERS = ("remote", "anywhere", "work from home", "wfh", "distributed")

# Non-US places that often ride along with a Remote marker. Word-boundary matched
# so "uk" does not hit "Ukraine"; "(?<!new )" keeps "New Mexico" (US state).
# Used only when remote_scope is US (remote_any=False).
_INTL_REMOTE_PLACE = re.compile(
    r"(?<!new )"
    r"\b(?:"
    r"emea|apac|latam|europe(?:\s+only)?|european\s+union|eu|"
    r"united\s+kingdom|u\.k\.?|uk|britain|england|scotland|wales|"
    r"india(?:\s+only)?|canada(?:\s+only)?|"
    r"germany|france|spain|italy|netherlands|ireland|portugal|belgium|"
    r"sweden|norway|denmark|finland|switzerland|austria|poland|"
    r"australia|new\s+zealand|singapore|japan|china|brazil|"
    r"mexico(?:\s+city)?|philippines|indonesia|malaysia|thailand|vietnam|taiwan|"
    r"korea|pakistan|bangladesh|nigeria|kenya|egypt|turkey|"
    r"argentina|chile|colombia|peru|israel|uae|dubai|"
    r"london|berlin|munich|frankfurt|amsterdam|dublin|"
    r"manchester|sydney|melbourne|toronto|vancouver|montreal|calgary|"
    r"bangalore|bengaluru|hyderabad|mumbai|delhi|manila|"
    r"worldwide\s+except|outside\s+the\s+(?:us|usa|united\s+states)|"
    r"non[\s-]?us"
    r")\b",
    re.I,
)


def pattern_matches(loc: str, pattern: str) -> bool:
    """Match a location pattern against a lowercased location string.

    Short alphanumeric tokens (<= 3 chars, e.g. "US", "SF", "CA") are matched on
    word boundaries so "US" does not match "Australia" and "CA" does not match
    "Calgary". Longer or punctuated patterns (", CA", "San Francisco") use plain
    substring matching.
    """
    p = pattern.lower().strip()
    if not p:
        return False
    if len(p) <= 3 and p.isalnum():
        return re.search(rf"\b{re.escape(p)}\b", loc) is not None
    return p in loc


def remote_scope(search_cfg: dict | None) -> str | None:
    """"us" or "any" for the profile's remote search entry; None when remote is off.

    Remote entries without a scope mean US only.
    """
    for loc in (search_cfg or {}).get("locations") or []:
        if isinstance(loc, dict) and loc.get("remote"):
            return "any" if loc.get("remote_scope") == "any" else "us"
    return None


def location_ok(
    location: str | None, accept: list[str], reject: list[str], *, remote_any: bool = False,
) -> bool:
    """Check if a job location passes the user's location filter.

    Remote jobs are accepted after reject patterns pass (avoids "Calgary Remote").
    Foreign city/country remotes (London, UK, Berlin, EMEA, ...) are rejected
    even when marked remote, unless the user takes remote jobs from any country
    (``remote_any``). Bare or US-tagged remotes stay. Non-remote jobs must match
    an accept pattern.
    """
    if not location:
        return True  # unknown location -- keep it, let scorer decide

    loc = location.lower()

    for r in reject:
        if pattern_matches(loc, r):
            return False

    if any(marker in loc for marker in _REMOTE_MARKERS):
        if not remote_any and _INTL_REMOTE_PLACE.search(loc):
            return False
        return True

    for a in accept:
        if pattern_matches(loc, a):
            return True

    return False
