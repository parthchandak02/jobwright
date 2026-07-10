"""Portfolio project selection per job description.

Selects 4-5 most relevant projects from profile.portfolio for each
high-scoring job before tailoring.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone

from applypilot.config import load_profile
from applypilot.database import get_connection, get_jobs_by_stage
from applypilot.llm import get_client

log = logging.getLogger(__name__)

MAX_PROJECTS = 5
MIN_PROJECTS = 4


def _keyword_score(project: dict, description: str) -> int:
    """Simple keyword overlap score for portfolio pre-ranking."""
    desc_lower = description.lower()
    score = 0
    for token in project.get("stack", []):
        if token.lower() in desc_lower:
            score += 2
    for bullet in project.get("bullets", []):
        for word in re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", bullet):
            if word.lower() in desc_lower:
                score += 1
    name = project.get("name", "")
    if name and name.lower() in desc_lower:
        score += 3
    return score


def _build_portfolio_prompt(profile: dict, job: dict, candidates: list[dict]) -> str:
    portfolio_lines = []
    for p in candidates:
        portfolio_lines.append(
            f"- id={p['id']}: {p.get('name', 'Unnamed')} | stack: {', '.join(p.get('stack', []))}\n"
            f"  bullets: {'; '.join(p.get('bullets', [])[:3])}"
        )
    portfolio_block = "\n".join(portfolio_lines)

    return f"""Select the {MIN_PROJECTS}-{MAX_PROJECTS} most relevant portfolio projects for this job.

JOB TITLE: {job.get('title', '')}
JOB DESCRIPTION (excerpt):
{(job.get('full_description') or '')[:4000]}

CANDIDATE PORTFOLIO (choose only from these IDs):
{portfolio_block}

Return ONLY valid JSON:
{{"selected_ids": ["id1", "id2", ...], "reasoning": "one sentence"}}

Rules:
- Pick {MIN_PROJECTS}-{MAX_PROJECTS} projects
- Only use IDs from the list above
- Never invent projects
"""


def select_projects_for_job(profile: dict, job: dict) -> list[str]:
    """Return selected portfolio project IDs for one job."""
    portfolio = profile.get("portfolio", [])
    if not portfolio:
        return []

    description = job.get("full_description") or job.get("description") or ""
    if not description:
        return [p["id"] for p in portfolio[:MAX_PROJECTS] if p.get("id")]

    ranked = sorted(
        portfolio,
        key=lambda p: _keyword_score(p, description),
        reverse=True,
    )
    candidates = ranked[: min(len(ranked), 12)]

    client = get_client()
    prompt = _build_portfolio_prompt(profile, job, candidates)
    try:
        response = client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        text = response.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        data = json.loads(text)
        selected = data.get("selected_ids", [])
        valid_ids = {p["id"] for p in portfolio if p.get("id")}
        return [sid for sid in selected if sid in valid_ids][:MAX_PROJECTS]
    except Exception as e:
        log.warning("Portfolio LLM selection failed for %s: %s", job.get("url"), e)
        return [p["id"] for p in candidates[:MAX_PROJECTS] if p.get("id")]


def run_portfolio_selection(min_score: int = 7, limit: int = 0) -> dict:
    """Select portfolio projects for scored jobs above min_score."""
    profile = load_profile()
    if not profile.get("portfolio"):
        log.info("No portfolio entries in profile.json — skipping portfolio stage")
        return {"status": "skipped", "reason": "no_portfolio"}

    conn = get_connection()
    rows = conn.execute(
        """
        SELECT * FROM jobs
        WHERE fit_score >= ?
          AND full_description IS NOT NULL
          AND portfolio_project_ids IS NULL
          AND LOWER(site) NOT LIKE '%linkedin%'
          AND url NOT LIKE '%linkedin.com%'
        ORDER BY fit_score DESC
        """,
        (min_score,),
    ).fetchall()

    if limit > 0:
        rows = rows[:limit]

    processed = 0
    now = datetime.now(timezone.utc).isoformat()

    for row in rows:
        job = dict(row)
        selected = select_projects_for_job(profile, job)
        if selected:
            conn.execute(
                "UPDATE jobs SET portfolio_project_ids = ? WHERE url = ?",
                (json.dumps(selected), job["url"]),
            )
            processed += 1

    conn.commit()
    log.info("Portfolio selection: %d jobs updated", processed)
    return {"status": "ok", "processed": processed}


def get_selected_projects(profile: dict, job: dict) -> list[dict]:
    """Resolve portfolio project dicts for a job."""
    portfolio = profile.get("portfolio", [])
    if not portfolio:
        return []

    raw = job.get("portfolio_project_ids")
    if not raw:
        return []

    try:
        ids = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return []

    by_id = {p["id"]: p for p in portfolio if p.get("id")}
    return [by_id[i] for i in ids if i in by_id]
