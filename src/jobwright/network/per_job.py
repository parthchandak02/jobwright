"""Per-job connection ranking: CSV 1st-degree + optional web research."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import jobwright.config as config
from jobwright.database import get_connection
from jobwright.llm import get_client
from jobwright.llm_json import LLMJsonError, chat_json_object, get_list_field
from jobwright.network.rank import load_connections_csv
from jobwright.network.research import research_company_contacts

log = logging.getLogger(__name__)


def _norm_company(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    for suffix in (
        " inc", " llc", " ltd", " corp", " corporation", " company", " co",
        " technologies", " technology", " labs", " lab",
    ):
        if s.endswith(suffix):
            s = s[: -len(suffix)].strip()
    return s


def companies_match(a: str, b: str) -> bool:
    """Fuzzy company name match for CSV vs job employer."""
    na, nb = _norm_company(a), _norm_company(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    # Compare without spaces (OpenAI vs Open AI)
    if na.replace(" ", "") == nb.replace(" ", ""):
        return True
    # Token overlap (at least one significant token)
    ta = {t for t in na.split() if len(t) > 2}
    tb = {t for t in nb.split() if len(t) > 2}
    if ta and tb and (ta & tb):
        return True
    return False


def resolve_company(job: dict) -> str:
    """Prefer DB company; fallback heuristics from site / title / description."""
    company = (job.get("company") or "").strip()
    if company:
        return company
    site = (job.get("site") or "").strip()
    # Workday often stores employer in site
    if site and site.lower() not in ("linkedin", "indeed", "glassdoor", "google", "ziprecruiter"):
        return site
    title = job.get("title") or ""
    # "Role at Company" pattern
    m = re.search(r"\bat\s+([A-Z][\w&.\' -]{1,60})$", title.strip())
    if m:
        return m.group(1).strip()
    return site or ""


def filter_contacts_for_company(
    contacts: list[dict[str, str]], company: str
) -> list[dict[str, str]]:
    if not company:
        return []
    return [c for c in contacts if companies_match(c.get("company") or "", company)]


def rank_contacts_for_job(
    contacts: list[dict[str, str]],
    job: dict,
    *,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """LLM-rank CSV contacts for a specific job opening."""
    if not contacts:
        return []
    # Cap prompt size
    subset = contacts[:40]
    company = resolve_company(job)
    lines = []
    for i, c in enumerate(subset):
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        lines.append(
            f"{i}. {name} | {c.get('position') or '?'} @ {c.get('company') or '?'}"
        )
    system = """You rank LinkedIn 1st-degree contacts for how helpful they would be
for THIS specific job application (referral / intro / advice).
Prefer people at the same company, hiring managers, founders, or adjacent teams.
Return ONLY JSON: {"contacts": [{"i": <index>, "score": <1-10>, "why": "<one short sentence>"}]}
Include only scores 6+. Max 5 items."""
    user_msg = (
        f"JOB: {job.get('title') or '?'} @ {company}\n"
        f"FIT SCORE: {job.get('fit_score')}\n"
        f"REASONING: {(job.get('score_reasoning') or '')[:400]}\n\n"
        f"CONTACTS:\n" + "\n".join(lines)
    )

    def _fallback() -> list[dict[str, Any]]:
        return [
            {
                "rank_score": 7,
                "why": "Same/similar company (no LLM rank)",
                "first_name": c.get("first_name", ""),
                "last_name": c.get("last_name", ""),
                "company": c.get("company", ""),
                "position": c.get("position", ""),
                "email": c.get("email", ""),
                "url": c.get("url", ""),
                "source": "csv",
            }
            for c in subset[:top_n]
        ]

    try:
        client = get_client()
        data = chat_json_object(
            client,
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=2048,
            temperature=0.2,
        )
        items = get_list_field(data, "contacts", "ranked", "results", "items")
    except (LLMJsonError, Exception) as e:
        log.warning("Per-job rank failed for %s: %s", job.get("url"), e)
        return _fallback()

    scored: list[dict[str, Any]] = []
    for item in items:
        try:
            i = int(item["i"])
            score = int(item["score"])
        except (KeyError, TypeError, ValueError):
            continue
        if i < 0 or i >= len(subset) or score < 6:
            continue
        c = subset[i]
        scored.append({
            "rank_score": score,
            "why": str(item.get("why") or ""),
            "first_name": c.get("first_name", ""),
            "last_name": c.get("last_name", ""),
            "company": c.get("company", ""),
            "position": c.get("position", ""),
            "email": c.get("email", ""),
            "url": c.get("url", ""),
            "source": "csv",
        })
    scored.sort(key=lambda x: -x["rank_score"])
    return scored[:top_n] if scored else _fallback()


def ensure_company_on_job(job: dict) -> str:
    """Backfill company column when missing."""
    company = resolve_company(job)
    url = job.get("url")
    if url and company and not (job.get("company") or "").strip():
        conn = get_connection()
        conn.execute("UPDATE jobs SET company = ? WHERE url = ?", (company, url))
        conn.commit()
        job["company"] = company
    return company


def run_per_job_connect(
    min_score: int = 5,
    limit: int = 5,
    *,
    max_csv: int = 3,
    max_web: int = 2,
) -> dict:
    """Rank connections per eligible job; write network/job_contacts_<date>.json."""
    from jobwright.apply.launcher import list_ready_jobs

    jobs = list_ready_jobs(min_score=min_score, limit=limit)
    if not jobs:
        return {"status": "ok", "jobs": 0, "contacts_file": None}

    # Enrich SELECT with company / score_reasoning / docx if missing from list_ready_jobs
    conn = get_connection()
    urls = [j["url"] for j in jobs]
    placeholders = ",".join("?" * len(urls))
    rows = conn.execute(
        f"""
        SELECT url, title, site, company, fit_score, score_reasoning,
               tailored_resume_path, cover_letter_path,
               tailored_resume_docx_path, cover_letter_docx_path,
               full_description, location
        FROM jobs WHERE url IN ({placeholders})
        """,
        urls,
    ).fetchall()
    by_url = {r["url"]: dict(r) for r in rows}
    for j in jobs:
        j.update(by_url.get(j["url"], {}))

    try:
        all_contacts = load_connections_csv()
    except FileNotFoundError:
        log.warning("connections.csv missing; CSV connect skipped")
        all_contacts = []

    payload: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "jobs": {},
    }

    for job in jobs:
        company = ensure_company_on_job(job)
        matched = filter_contacts_for_company(all_contacts, company) if all_contacts else []
        csv_ranked = rank_contacts_for_job(matched, job, top_n=max_csv) if matched else []
        web = research_company_contacts(company, role=job.get("title") or "", max_results=max_web)
        payload["jobs"][job["url"]] = {
            "title": job.get("title"),
            "company": company,
            "fit_score": job.get("fit_score"),
            "csv_contacts": csv_ranked,
            "web_contacts": web,
        }

    out_dir = config.NETWORK_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    out_path = out_dir / f"job_contacts_{today}.json"
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    # Latest pointer for digest
    (out_dir / "job_contacts_latest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    return {
        "status": "ok",
        "jobs": len(jobs),
        "contacts_file": str(out_path),
    }


def load_job_contacts(path: Path | None = None) -> dict[str, Any]:
    """Load latest per-job contacts JSON."""
    path = path or (config.NETWORK_DIR / "job_contacts_latest.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
