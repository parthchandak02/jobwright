"""Discovery filters: title exclusion and salary floor parsing."""

from __future__ import annotations

import re
from typing import Any

_SALARY_NUM = re.compile(
    r"(?P<currency>\$|USD|CAD|EUR|GBP)?\s*(?P<amount>\d{1,3}(?:,\d{3})+|\d{2,7})\s*(?P<k>[kK])?",
    re.IGNORECASE,
)
_RANGE = re.compile(
    r"(?P<a>\d[\d,]*(?:\.\d+)?)\s*(?P<ak>[kK])?\s*[-–to]+\s*(?P<b>\d[\d,]*(?:\.\d+)?)\s*(?P<bk>[kK])?",
    re.IGNORECASE,
)


def _to_annual(amount: float, raw: str) -> float:
    """Normalize a parsed amount to approximate annual USD."""
    lower = raw.lower()
    if "hour" in lower or "/hr" in lower or "/h" in lower:
        return amount * 2080
    if "month" in lower or "/mo" in lower:
        return amount * 12
    if amount < 1000:
        # Likely thousands shorthand already expanded, or hourly without label
        if "k" in lower:
            return amount  # already scaled
        return amount * 2080
    return amount


def parse_salary_to_annual(salary: str | None) -> float | None:
    """Best-effort parse of a salary string into annual USD float.

    Returns None if unparseable (caller should keep the job).
    For ranges, uses the *maximum* so a 100k-130k posting is kept when floor is 115k.
    """
    if not salary or not str(salary).strip():
        return None
    text = str(salary).strip()
    # Prefer explicit range
    m = _RANGE.search(text.replace(",", ""))
    if m:
        a = float(m.group("a").replace(",", ""))
        b = float(m.group("b").replace(",", ""))
        if (m.group("ak") or m.group("bk") or "k" in text.lower()) and a < 1000 and b < 1000:
            a, b = a * 1000, b * 1000
        return _to_annual(max(a, b), text)

    amounts: list[float] = []
    for m in _SALARY_NUM.finditer(text.replace(",", "")):
        amt = float(m.group("amount").replace(",", ""))
        if m.group("k"):
            amt *= 1000
        amounts.append(_to_annual(amt, text))
    if not amounts:
        return None
    return max(amounts)


# Title/company/JD must mention one of these for CoS (and similar) to score as a match.
_IMPACT_MARKERS = (
    "social impact",
    "corporate social",
    "corporate purpose",
    "philanthrop",
    "nonprofit",
    "non-profit",
    "non profit",
    "community impact",
    "community investment",
    "data for good",
    "for good",
    "grantmaking",
    "grant-making",
    "venture philanthropy",
    "impact invest",
    "cdfi",
    "economic mobility",
    "workforce development",
    "csr",
)


def title_excluded(title: str | None, exclude_titles: list[str] | None) -> bool:
    """True if title matches an exclude pattern with word boundaries.

    Avoids false positives like exclude 'intern' matching 'International'.
    Multi-word patterns still use substring match (e.g. 'software engineer').
    """
    if not title or not exclude_titles:
        return False
    t = title.lower()
    for exc in exclude_titles:
        if not exc:
            continue
        pattern = exc.lower().strip()
        if " " in pattern or len(pattern) >= 8:
            # Multi-word / long phrases: substring is fine
            if pattern in t:
                return True
            continue
        # Short tokens: require word boundary (intern != international)
        if re.search(rf"(?<![a-z]){re.escape(pattern)}(?![a-z])", t):
            return True
    return False


def salary_below_floor(
    salary: str | None,
    min_salary: float | None,
    description: str | None = None,
) -> bool:
    """True if we can parse a salary and it is clearly below min_salary.

    Unknown / unparseable salaries are NOT below floor (keep for scorer).
    For ranges, compare the max so overlapping bands are kept.
    """
    if not min_salary:
        return False
    floor = float(min_salary)
    annual = parse_salary_to_annual(salary)
    if annual is None and description:
        # Light scan of first 2k chars of JD for salary mentions
        annual = parse_salary_to_annual(description[:2000])
    if annual is None:
        return False
    return annual < floor


def passes_discovery_filters(
    *,
    title: str | None,
    salary: str | None,
    description: str | None,
    search_cfg: dict[str, Any],
) -> bool:
    """Apply exclude_titles + min_salary from searches.yaml."""
    if title_excluded(title, search_cfg.get("exclude_titles") or []):
        return False
    min_sal = search_cfg.get("min_salary")
    if min_sal is None:
        defaults = search_cfg.get("defaults") or {}
        min_sal = defaults.get("min_salary")
    return not salary_below_floor(salary, min_sal, description)


def fit_score_ceiling(
    title: str | None,
    company: str | None,
    description: str | None,
    exclude_titles: list[str] | None,
) -> int | None:
    """Hard max fit score, or None if the LLM score should stand.

    Caps roles that are outside the social-impact / CSR / foundation track even
    when the model overrates transferable ops experience.
    """
    if title_excluded(title, exclude_titles):
        return 4
    t = (title or "").lower()
    company_l = (company or "").lower()
    desc = (description or "").strip()
    blob = f"{t} {company_l} {desc[:1500].lower()}"
    if any(n in company_l for n in ("foundation", "nonprofit", "non-profit", "philanthrop")):
        return None
    needs_mission = any(
        p in t for p in ("chief of staff", "business advisor", "business operations")
    )
    if needs_mission and desc and not any(m in blob for m in _IMPACT_MARKERS):
        return 4
    return None


def apply_fit_score_guards(
    job: dict[str, Any],
    parsed: dict[str, Any],
    search_cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lower an LLM fit score when hard avoid patterns match."""
    search_cfg = search_cfg or {}
    ceiling = fit_score_ceiling(
        job.get("title"),
        job.get("company") or job.get("site"),
        job.get("full_description") or job.get("description"),
        (search_cfg or {}).get("exclude_titles"),
    )
    score = int(parsed["score"])
    if ceiling is None or score <= ceiling:
        return parsed
    out = dict(parsed)
    out["score"] = ceiling
    reason = (out.get("reasoning") or "").rstrip()
    out["reasoning"] = (
        f"{reason} [capped at {ceiling}: outside social-impact / CSR / foundation track]"
    )
    return out
