"""Per-user match criteria: what makes a posting worth this candidate's time.

Stored in profile.json under ``match_criteria`` (editable in the dashboard).
When absent, a generic version is derived from the profile's job_preferences so
every user gets structured dealbreakers without hand-written rules in code.

Shape::

    {
      "summary": "one paragraph in plain words",
      "dealbreakers": [{"id": "fundraising", "label": "...", "description": "..."}],
      "must_haves": ["..."],
      "nice_to_haves": ["..."],
      "locations_ok": ["..."],
      "locations_not_ok": ["..."],
      "seniority": "...",
      "min_salary": 115000,
      "notify_threshold": 7
    }
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

DEFAULT_NOTIFY_THRESHOLD = 7


@dataclass
class Dealbreaker:
    id: str
    label: str
    description: str


@dataclass
class MatchCriteria:
    summary: str = ""
    dealbreakers: list[Dealbreaker] = field(default_factory=list)
    must_haves: list[str] = field(default_factory=list)
    nice_to_haves: list[str] = field(default_factory=list)
    locations_ok: list[str] = field(default_factory=list)
    locations_not_ok: list[str] = field(default_factory=list)
    seniority: str = ""
    min_salary: float | None = None
    notify_threshold: int = DEFAULT_NOTIFY_THRESHOLD
    derived: bool = False

    def dealbreaker_ids(self) -> set[str]:
        return {d.id for d in self.dealbreakers}

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary,
            "dealbreakers": [d.__dict__ for d in self.dealbreakers],
            "must_haves": self.must_haves,
            "nice_to_haves": self.nice_to_haves,
            "locations_ok": self.locations_ok,
            "locations_not_ok": self.locations_not_ok,
            "seniority": self.seniority,
            "min_salary": self.min_salary,
            "notify_threshold": self.notify_threshold,
        }


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:32] or "rule"


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [p.strip() for p in re.split(r"[;\n]", value) if p.strip()]
    return []


def _float_or_none(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "").replace("$", "")) if value not in (None, "") else None
    except ValueError:
        return None


def parse_criteria(raw: dict[str, Any]) -> MatchCriteria:
    deals: list[Dealbreaker] = []
    seen: set[str] = set()
    for item in raw.get("dealbreakers") or []:
        if isinstance(item, str):
            item = {"label": item, "description": item}
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("description") or "").strip()
        if not label:
            continue
        did = _slug(str(item.get("id") or label))
        while did in seen:
            did += "_x"
        seen.add(did)
        deals.append(Dealbreaker(id=did, label=label, description=str(item.get("description") or label).strip()))
    try:
        threshold = int(raw.get("notify_threshold") or DEFAULT_NOTIFY_THRESHOLD)
    except (TypeError, ValueError):
        threshold = DEFAULT_NOTIFY_THRESHOLD
    return MatchCriteria(
        summary=str(raw.get("summary") or "").strip(),
        dealbreakers=deals,
        must_haves=_as_list(raw.get("must_haves")),
        nice_to_haves=_as_list(raw.get("nice_to_haves")),
        locations_ok=_as_list(raw.get("locations_ok")),
        locations_not_ok=_as_list(raw.get("locations_not_ok")),
        seniority=str(raw.get("seniority") or "").strip(),
        min_salary=_float_or_none(raw.get("min_salary")),
        notify_threshold=max(1, min(10, threshold)),
    )


def derive_criteria(profile: dict[str, Any] | None) -> MatchCriteria:
    """Generic criteria from job_preferences when the user has not curated any."""
    profile = profile or {}
    prefs = profile.get("job_preferences") or {}
    exp = profile.get("experience") or {}
    comp = profile.get("compensation") or {}
    deals = [
        {"label": text, "description": text}
        for text in _as_list(prefs.get("avoid_roles")) + _as_list(prefs.get("avoid")) + _as_list(prefs.get("exclude"))
    ]
    must = _as_list(prefs.get("ideal_roles"))
    seek = _as_list(prefs.get("seek")) + _as_list(prefs.get("include")) + _as_list(prefs.get("company_types"))
    summary = str(exp.get("target_role") or profile.get("target_role") or "").strip()
    criteria = parse_criteria(
        {
            "summary": summary,
            "dealbreakers": deals,
            "must_haves": must,
            "nice_to_haves": seek,
            "locations_ok": _as_list(prefs.get("locations")),
            "min_salary": comp.get("salary_range_min") or comp.get("salary_expectation"),
        }
    )
    criteria.derived = True
    return criteria


def load_criteria(profile: dict[str, Any] | None) -> MatchCriteria:
    raw = (profile or {}).get("match_criteria")
    if isinstance(raw, dict) and (raw.get("dealbreakers") or raw.get("summary") or raw.get("must_haves")):
        return parse_criteria(raw)
    return derive_criteria(profile)


def render_criteria(criteria: MatchCriteria) -> str:
    """Prompt block describing the candidate's rules."""
    lines: list[str] = []
    if criteria.summary:
        lines.append(f"WHAT THEY WANT:\n{criteria.summary}")
    if criteria.must_haves:
        lines.append("GOOD-FIT ROLE TYPES:\n" + "\n".join(f"- {m}" for m in criteria.must_haves))
    if criteria.nice_to_haves:
        lines.append("PLUSES:\n" + "\n".join(f"- {m}" for m in criteria.nice_to_haves))
    if criteria.dealbreakers:
        lines.append(
            "DEALBREAKERS (report the id of every one that clearly applies to THIS posting's core duties "
            "or hard requirements; do not flag one for a passing mention):\n"
            + "\n".join(f"- [{d.id}] {d.description}" for d in criteria.dealbreakers)
        )
    if criteria.locations_ok or criteria.locations_not_ok:
        loc = []
        if criteria.locations_ok:
            loc.append("Acceptable: " + "; ".join(criteria.locations_ok))
        if criteria.locations_not_ok:
            loc.append("Not acceptable: " + "; ".join(criteria.locations_not_ok))
        lines.append("LOCATION:\n" + "\n".join(loc))
    if criteria.seniority:
        lines.append(f"SENIORITY:\n{criteria.seniority}")
    if criteria.min_salary:
        lines.append(f"SALARY FLOOR: {int(criteria.min_salary):,} USD/year (only matters when the posting states pay)")
    return "\n\n".join(lines)
