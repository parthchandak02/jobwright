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


from jobwright.job_identity import resolve_company  # noqa: E402,F401  (re-export)


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


_WEB_CACHE_DAYS = 14
_REFRESH_DAYS = 14


def _eligible_connect_jobs(conn, min_score: int, limit: int, known: dict[str, Any]) -> list[dict]:
    """Active, well-scored jobs whose contacts are missing or stale.

    Independent of tailoring, so human-gated briefs (no materials yet) still get
    referral suggestions for the jobs they are about to review.
    """
    rows = conn.execute(
        """
        SELECT url, title, site, company, fit_score, user_fit_score, score_reasoning,
               tailored_resume_path, cover_letter_path, tailored_resume_docx_path,
               cover_letter_docx_path, full_description, location
        FROM jobs
        WHERE COALESCE(user_fit_score, fit_score) >= ?
          AND COALESCE(funnel_stage, 'backlog') IN ('backlog', 'prepare', 'applied', 'in_progress')
          AND COALESCE(source, 'discovered') != 'manual'
        ORDER BY COALESCE(user_fit_score, fit_score) DESC, discovered_at DESC
        """,
        (min_score,),
    ).fetchall()
    cutoff = datetime.now().timestamp() - _REFRESH_DAYS * 86400
    out: list[dict] = []
    for row in rows:
        entry = known.get(row["url"]) or {}
        try:
            fresh = datetime.fromisoformat(entry.get("generated_at", "")).timestamp() >= cutoff
        except ValueError:
            fresh = False
        if fresh:
            continue
        out.append(dict(row))
        if len(out) >= limit:
            break
    return out


def _cached_web_contacts(cache: dict[str, Any], company: str, role: str, max_web: int) -> list[dict]:
    key = _norm_company(company)
    hit = cache.get(key)
    if hit:
        try:
            if datetime.now().timestamp() - datetime.fromisoformat(hit["at"]).timestamp() < _WEB_CACHE_DAYS * 86400:
                return hit.get("contacts") or []
        except (KeyError, ValueError):
            pass
    contacts = research_company_contacts(company, role=role, max_results=max_web)
    cache[key] = {"at": datetime.now().isoformat(), "contacts": contacts}
    return contacts


def _atomic_write_json(path: Path, payload: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def run_per_job_connect(
    min_score: int = 7,
    limit: int = 15,
    *,
    max_csv: int = 3,
    max_web: int = 2,
) -> dict:
    """Rank connections for eligible jobs and merge into network/job_contacts_latest.json.

    Existing entries for other jobs are kept (the store grows; it is never
    replaced by just today's handful). Web research is cached per company.
    """
    out_dir = config.NETWORK_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    latest_path = out_dir / "job_contacts_latest.json"
    store = load_job_contacts(latest_path)
    known: dict[str, Any] = store.get("jobs") if isinstance(store.get("jobs"), dict) else {}

    conn = get_connection()
    jobs = _eligible_connect_jobs(conn, min_score, limit, known)
    if not jobs:
        return {"status": "ok", "jobs": 0, "contacts_file": str(latest_path) if latest_path.exists() else None}

    try:
        all_contacts = load_connections_csv()
    except FileNotFoundError:
        log.warning("connections.csv missing; CSV connect skipped")
        all_contacts = []

    cache_path = out_dir / "web_contacts_cache.json"
    web_cache = load_job_contacts(cache_path)
    now = datetime.now().isoformat()
    for job in jobs:
        company = ensure_company_on_job(job)
        matched = filter_contacts_for_company(all_contacts, company) if all_contacts else []
        csv_ranked = rank_contacts_for_job(matched, job, top_n=max_csv) if matched else []
        web = _cached_web_contacts(web_cache, company, job.get("title") or "", max_web) if company else []
        known[job["url"]] = {
            "title": job.get("title"),
            "company": company,
            "fit_score": job.get("user_fit_score") or job.get("fit_score"),
            "csv_contacts": csv_ranked,
            "web_contacts": web,
            "generated_at": now,
        }

    payload = {"generated_at": now, "jobs": known}
    _atomic_write_json(latest_path, payload)
    _atomic_write_json(cache_path, web_cache)
    return {"status": "ok", "jobs": len(jobs), "contacts_file": str(latest_path)}


def load_job_contacts(path: Path | None = None) -> dict[str, Any]:
    """Load latest per-job contacts JSON."""
    path = path or (config.NETWORK_DIR / "job_contacts_latest.json")
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
