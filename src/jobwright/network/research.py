"""Public web research for hiring contacts (Exa). No LinkedIn scraping."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

import httpx

log = logging.getLogger(__name__)

_EXA_URL = "https://api.exa.ai/search"


def _normalize_person_name(title: str) -> str | None:
    """Heuristic: pull a Person Name from a search result title if present."""
    # Patterns like "Jane Doe - VP Engineering at Acme" or "Jane Doe | Acme"
    m = re.match(
        r"^([A-Z][a-z]+(?:\s+[A-Z][a-z.'-]+){0,3})\s*[-|–—:,]",
        title.strip(),
    )
    if m:
        return m.group(1).strip()
    return None


def research_company_contacts(
    company: str,
    role: str = "",
    *,
    max_results: int = 2,
    api_key: str | None = None,
) -> list[dict[str, Any]]:
    """Search the public web for people related to hiring at a company.

    Returns list of {name, role, source_url, note}. Empty if no EXA_API_KEY.
    """
    key = api_key or os.environ.get("EXA_API_KEY") or ""
    if not key.strip():
        log.debug("EXA_API_KEY not set; skipping web research for %s", company)
        return []
    if not company or not company.strip():
        return []

    query_parts = [f"people hiring {role} at {company}".strip() if role else f"team {company}"]
    if role:
        query_parts.append(f"{company} {role} hiring manager")
    query = query_parts[0]

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
    except Exception as e:
        log.warning("Exa search failed for %s: %s", company, e)
        return []

    results = data.get("results") or []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in results:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        snippet = (item.get("text") or item.get("summary") or "")[:200].strip()
        name = _normalize_person_name(title) or ""
        # Skip LinkedIn profile scrapes; prefer public pages
        if "linkedin.com/in/" in url.lower():
            continue
        key_id = (name or title).lower()
        if key_id in seen:
            continue
        seen.add(key_id)
        out.append({
            "name": name or title[:60],
            "role": role or "hiring / team",
            "source_url": url,
            "note": snippet or f"Public web result for {company}",
            "source": "web",
        })
        if len(out) >= max_results:
            break
    return out
