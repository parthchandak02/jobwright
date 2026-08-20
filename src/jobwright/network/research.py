"""Public web research for hiring contacts (Exa)."""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

_EXA_URL = "https://api.exa.ai/search"

_TITLE_TOKENS = {
    "acting", "analyst", "associate", "chief", "college", "community",
    "consultant", "coordinator", "director", "engineer", "foundation",
    "global", "head", "hiring", "intern", "job", "lead", "legal",
    "manager", "network", "officer", "principal", "program", "programme",
    "recruiter", "senior", "specialist", "vice",
}

_JOB_HOST_MARKERS = (
    "myworkdayjobs.com",
    "workdayjobs.com",
    "greenhouse.io",
    "lever.co",
    "ashbyhq.com",
    "icims.com",
    "smartrecruiters.com",
    "jobvite.com",
    "glassdoor.com",
    "ziprecruiter.com",
    "indeed.com",
    "linkedin.com/jobs",
)


def looks_like_person_name(name: str) -> bool:
    """True when the string looks like a person's name, not a job title."""
    parts = [p.strip(".,") for p in (name or "").split() if p.strip(".,")]
    if len(parts) < 2 or len(parts) > 4:
        return False
    if not all(re.match(r"^[A-Z][A-Za-z.'-]*$", p) for p in parts):
        return False
    tokens = [p.lower() for p in parts]
    return not all(t in _TITLE_TOKENS for t in tokens)


def is_job_posting_url(url: str) -> bool:
    raw = (url or "").strip().lower()
    if not raw:
        return False
    parsed = urlparse(raw)
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    blob = f"{host}{path}"
    if "linkedin.com" in host and "/in/" in path:
        return False
    return any(marker in blob or marker in raw for marker in _JOB_HOST_MARKERS)


def _normalize_person_name(title: str) -> str | None:
    """Heuristic: pull a Person Name from a search result title if present."""
    m = re.match(
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z.'-]+){0,3})\s*[-|–—:,]",
        (title or "").strip(),
    )
    if not m:
        return None
    name = m.group(1).strip()
    return name if looks_like_person_name(name) else None


def present_contact(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize a stored contact for the dashboard. Drop job-posting junk."""
    first = str(raw.get("first_name") or "").strip()
    last = str(raw.get("last_name") or "").strip()
    name = str(raw.get("name") or "").strip()
    display = name or f"{first} {last}".strip()
    url = str(raw.get("url") or raw.get("source_url") or "").strip()
    if is_job_posting_url(url):
        return None
    if first and last:
        out = dict(raw)
        out["url"] = url
        if not out.get("why") and raw.get("note"):
            out["why"] = raw["note"]
        return out
    if not looks_like_person_name(display):
        return None
    out = dict(raw)
    out["name"] = display
    out["url"] = url
    if not out.get("why") and raw.get("note"):
        out["why"] = raw["note"]
    role = str(raw.get("role") or "").strip()
    if role and role != display and not out.get("position"):
        out["position"] = role
    return out


def research_company_contacts(
    company: str,
    role: str = "",
    *,
    max_results: int = 2,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Search the public web for people related to hiring at a company.

    Returns list of {name, role, url, why, source, company}. Empty if no EXA_API_KEY.
    """
    key = api_key or os.environ.get("EXA_API_KEY") or ""
    if not key.strip():
        log.debug("EXA_API_KEY not set; skipping web research for %s", company)
        return []
    if not company or not company.strip():
        return []

    query = f"people hiring {role} at {company}".strip() if role else f"team {company}"

    try:
        resp = httpx.post(
            _EXA_URL,
            headers={"x-api-key": key, "Content-Type": "application/json"},
            json={
                "query": query,
                "num_results": max(max_results * 3, 6),
                "type": "auto",
                "use_autoprompt": True,
            },
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, OSError, ValueError) as e:
        log.warning("Exa search failed for %s: %s", company, e)
        return []

    results = data.get("results") or []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        snippet = (item.get("text") or item.get("summary") or "")[:200].strip()
        name = _normalize_person_name(title)
        if not name:
            continue
        if is_job_posting_url(url):
            continue
        key_id = name.lower()
        if key_id in seen:
            continue
        seen.add(key_id)
        remainder = ""
        cut = re.split(r"\s*[-|–—:,]\s*", title, maxsplit=1)
        if len(cut) == 2:
            remainder = cut[1].strip()
        presented = present_contact({
            "name": name,
            "role": remainder or "hiring / team",
            "source_url": url,
            "note": snippet or f"Public web result for {company}",
            "source": "web",
            "company": company,
        })
        if not presented:
            continue
        out.append(presented)
        if len(out) >= max_results:
            break
    return out
