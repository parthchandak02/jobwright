"""Target company list builder (LLM + optional seed companies)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

import applypilot.config as config
from applypilot.config import load_profile, load_search_config
from applypilot.llm import get_client

log = logging.getLogger(__name__)


def _guidance(profile: dict) -> str:
    exp = profile.get("experience") or {}
    prefs = profile.get("job_preferences") or {}
    personal = profile.get("personal") or {}
    lines = []
    if exp.get("target_role"):
        lines.append(f"Target role: {exp['target_role']}")
    if prefs.get("ideal_roles") or prefs.get("seek"):
        lines.append(f"Seek roles: {prefs.get('ideal_roles') or prefs.get('seek')}")
    if prefs.get("company_types"):
        lines.append(f"Company types: {prefs['company_types']}")
    if prefs.get("avoid_roles") or prefs.get("avoid"):
        lines.append(f"Avoid: {prefs.get('avoid_roles') or prefs.get('avoid')}")
    loc = f"{personal.get('city', '')} {personal.get('province_state', '')}".strip()
    if loc:
        lines.append(f"Location preference: {loc}")
    comp = profile.get("compensation") or {}
    if comp.get("salary_expectation"):
        lines.append(
            f"Salary floor: {comp['salary_expectation']} {comp.get('salary_currency', 'USD')}"
        )
    if not lines:
        lines.append(
            "Prefer Bay Area startups needing Chief of Staff / strategy / partnerships; "
            "impact VCs (platform roles); CSR / employee engagement; foundations."
        )
    return "\n".join(lines)


def _parse_companies_json(text: str) -> list[dict]:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        start, end = text.find("["), text.rfind("]")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
    except json.JSONDecodeError:
        log.warning("Failed to parse target companies JSON")
    return []


def build_target_list(
    profile: dict,
    resume_text: str = "",
    limit: int = 30,
    seed_companies: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Ask the LLM for a ranked target company list."""
    client = get_client()
    seeds = seed_companies or []
    # Also pull from searches.yaml target_companies if present
    try:
        cfg = load_search_config()
        seeds = list(seeds) + list(cfg.get("target_companies") or [])
    except Exception:
        pass
    seeds = sorted({s.strip() for s in seeds if s and str(s).strip()})

    system = """You are a career strategist building a target company list.
Return ONLY a JSON array of objects:
[{"name": "...", "category": "startup|impact_vc|csr|foundation|other",
  "why": "one sentence fit", "priority": 1-10, "roles_to_watch": ["Chief of Staff", "..."]}]

Rules:
- Focus on Bay Area / remote-friendly orgs when location suggests it.
- Prioritize startups that hire Chief of Staff / strategy / partnerships;
  impact / platform VC roles that do NOT need deep finance experience;
  CSR / employee engagement (not deep climate science or ESG investing);
  family / large foundations (program / partnerships).
- Exclude pure engineering shops and roles requiring heavy technical depth.
- Include a mix: ~40% startups, ~25% VCs/platform, ~20% CSR/corp, ~15% foundations.
- priority 10 = strongest fit."""

    user_msg = (
        f"CANDIDATE GUIDANCE:\n{_guidance(profile)}\n\n"
        f"RESUME SNIPPET:\n{(resume_text or '')[:3500]}\n\n"
        f"SEED COMPANIES TO CONSIDER (may include or expand):\n"
        f"{', '.join(seeds) if seeds else '(none — invent a strong list)'}\n\n"
        f"Return up to {limit} companies."
    )
    raw = client.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
        max_tokens=4096,
        temperature=0.4,
    )
    companies = _parse_companies_json(raw)
    # Normalize + sort
    out: list[dict[str, Any]] = []
    for c in companies:
        name = str(c.get("name") or "").strip()
        if not name:
            continue
        try:
            priority = int(c.get("priority") or 5)
        except (TypeError, ValueError):
            priority = 5
        out.append({
            "name": name,
            "category": str(c.get("category") or "other"),
            "why": str(c.get("why") or ""),
            "priority": max(1, min(10, priority)),
            "roles_to_watch": c.get("roles_to_watch") or [],
        })
    out.sort(key=lambda x: -x["priority"])
    return out[:limit]


def format_targets_digest(companies: list[dict], user_label: str = "") -> str:
    who = f" ({user_label})" if user_label else ""
    lines = [
        f"=== Target companies{who} ===",
        f"Date: {datetime.now().strftime('%Y-%m-%d')}",
        "",
    ]
    for i, c in enumerate(companies, 1):
        roles = ", ".join(c.get("roles_to_watch") or []) or "strategy / CoS / partnerships"
        lines.append(
            f"{i}. *{c['name']}* [{c.get('category', '')}] (priority {c.get('priority', '')})"
        )
        if c.get("why"):
            lines.append(f"   {c['why']}")
        lines.append(f"   Watch for: {roles}")
        lines.append("")
    lines.append(
        "Tip: add accepted names under searches.yaml → target_companies "
        "to bias future discovery queries."
    )
    return "\n".join(lines)


def save_targets(companies: list[dict], path: Path | None = None) -> Path:
    path = path or config.TARGETS_PATH
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "companies": companies,
    }
    path.write_text(
        yaml.safe_dump(payload, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return path


def merge_targets_into_searches(companies: list[dict], max_names: int = 40) -> None:
    """Optionally write company names into searches.yaml target_companies list."""
    path = config.SEARCH_CONFIG_PATH
    if not path.exists():
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    names = [c["name"] for c in companies[:max_names] if c.get("name")]
    existing = list(data.get("target_companies") or [])
    merged = []
    seen = set()
    for n in existing + names:
        key = n.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(n)
    data["target_companies"] = merged
    path.write_text(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def run_targets(
    limit: int = 30,
    merge_into_searches: bool = False,
) -> dict:
    """Build + persist target company list for the active user."""
    profile = load_profile()
    resume = ""
    if config.RESUME_PATH.exists():
        resume = config.RESUME_PATH.read_text(encoding="utf-8")
    companies = build_target_list(profile, resume_text=resume, limit=limit)
    yaml_path = save_targets(companies)
    label = (profile.get("personal") or {}).get("preferred_name") or ""
    digest = format_targets_digest(companies, user_label=label)
    txt_path = config.APP_DIR / "target_companies.txt"
    txt_path.write_text(digest, encoding="utf-8")
    if merge_into_searches:
        merge_targets_into_searches(companies)
    return {
        "count": len(companies),
        "yaml_path": str(yaml_path),
        "txt_path": str(txt_path),
        "digest": digest,
        "companies": companies,
    }
