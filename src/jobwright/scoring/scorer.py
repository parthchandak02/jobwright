"""Job fit scoring: LLM-powered evaluation of candidate-job match quality.

Scores jobs on a 1-10 scale by comparing the user's resume against each
job description. All personal data is loaded at runtime from the user's
profile and resume file.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone

from jobwright.config import load_profile
import jobwright.config as config
from jobwright.database import get_connection, get_jobs_by_stage
from jobwright.llm import get_client

log = logging.getLogger(__name__)


# ── Scoring Prompt ────────────────────────────────────────────────────────

SCORE_PROMPT_BASE = """You are a job fit evaluator. Given a candidate's resume, optional target-role guidance, and a job description, score how well the candidate fits the role.

SCORING CRITERIA:
- 9-10: Perfect match. Candidate has direct experience in nearly all required skills and qualifications.
- 7-8: Strong match. Candidate has most required skills, minor gaps easily bridged.
- 5-6: Moderate match. Candidate has some relevant skills but missing key requirements.
- 3-4: Weak match. Significant skill gaps, would need substantial ramp-up.
- 1-2: Poor match. Completely different field or experience level.

IMPORTANT FACTORS:
- Weight skills and experience that match the candidate's TARGET ROLE guidance (below) - not a generic engineering checklist.
- Prefer consulting, entrepreneurship, partnerships, strategy, operations, CSR, and leadership experience when the target role is non-technical.
- Penalize roles that are primarily technical (software engineering, data science, deep ESG/climate science, heavy finance/IB) when the guidance says to avoid them.
- Consider transferable experience and project/program leadership.
- Be realistic about experience level vs. job requirements (years of experience, seniority).
- If salary is listed and clearly below the candidate's floor, score lower (max 4).

RESPOND IN EXACTLY THIS FORMAT (no other text):
SCORE: [1-10]
KEYWORDS: [comma-separated ATS keywords from the job description that match or could match the candidate]
REASONING: [2-3 sentences explaining the score]"""


def _build_score_prompt(profile: dict | None) -> str:
    """Inject profile-driven target role / avoid guidance into the scoring prompt."""
    guidance_lines: list[str] = []
    if profile:
        exp = profile.get("experience") or {}
        target = exp.get("target_role") or profile.get("target_role")
        if target:
            guidance_lines.append(f"- Target role: {target}")
        prefs = profile.get("job_preferences") or {}
        for key in ("ideal_roles", "seek", "include"):
            if prefs.get(key):
                guidance_lines.append(f"- Seek: {prefs[key]}")
        for key in ("avoid_roles", "avoid", "exclude"):
            if prefs.get(key):
                guidance_lines.append(f"- Avoid: {prefs[key]}")
        comp = profile.get("compensation") or {}
        floor = comp.get("salary_expectation") or comp.get("salary_range_min")
        if floor:
            currency = comp.get("salary_currency", "USD")
            guidance_lines.append(f"- Salary floor: {floor} {currency} annual")
        skills = profile.get("skills_boundary") or {}
        if skills:
            flat = []
            for v in skills.values():
                if isinstance(v, list):
                    flat.extend(str(x) for x in v)
                elif v:
                    flat.append(str(v))
            if flat:
                guidance_lines.append(f"- Emphasize: {', '.join(flat[:20])}")

    if not guidance_lines:
        guidance_lines = [
            "- Infer target role from the resume; do not assume software engineering.",
            "- Weight the strongest themes in the resume (consulting, ops, impact, etc.).",
        ]

    return (
        SCORE_PROMPT_BASE
        + "\n\nCANDIDATE TARGET-ROLE GUIDANCE:\n"
        + "\n".join(guidance_lines)
    )


# Back-compat alias for imports/tests
SCORE_PROMPT = SCORE_PROMPT_BASE


def _parse_score_response(response: str) -> dict:
    """Parse the LLM's score response into structured data.

    Args:
        response: Raw LLM response text.

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    score = 0
    keywords = ""
    reasoning = response

    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                score = int(re.search(r"\d+", line).group())
                score = max(1, min(10, score))
            except (AttributeError, ValueError):
                score = 0
        elif line.startswith("KEYWORDS:"):
            keywords = line.replace("KEYWORDS:", "").strip()
        elif line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()

    return {"score": score, "keywords": keywords, "reasoning": reasoning}


def score_job(resume_text: str, job: dict, profile: dict | None = None) -> dict:
    """Score a single job against the resume.

    Args:
        resume_text: The candidate's full resume text.
        job: Job dict with keys: title, site, location, full_description.
        profile: Optional profile for target-role guidance.

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job['site']}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n"
        f"SALARY: {job.get('salary') or 'N/A'}\n\n"
        f"DESCRIPTION:\n{(job.get('full_description') or '')[:6000]}"
    )

    messages = [
        {"role": "system", "content": _build_score_prompt(profile)},
        {"role": "user", "content": f"RESUME:\n{resume_text}\n\n---\n\nJOB POSTING:\n{job_text}"},
    ]

    try:
        client = get_client()
        response = client.chat(messages, max_tokens=512, temperature=0.2)
        return _parse_score_response(response)
    except Exception as e:
        log.error("LLM error scoring job '%s': %s", job.get("title", "?"), e)
        return {"score": 0, "keywords": "", "reasoning": f"LLM error: {e}"}


def run_scoring(limit: int = 0, rescore: bool = False) -> dict:
    """Score unscored jobs that have full descriptions.

    Args:
        limit: Maximum number of jobs to score in this run.
        rescore: If True, re-score all jobs (not just unscored ones).

    Returns:
        {"scored": int, "errors": int, "elapsed": float, "distribution": list}
    """
    resume_text = config.RESUME_PATH.read_text(encoding="utf-8")
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = None
    conn = get_connection()

    if rescore:
        query = "SELECT * FROM jobs WHERE full_description IS NOT NULL"
        if limit > 0:
            query += f" LIMIT {limit}"
        jobs = conn.execute(query).fetchall()
    else:
        jobs = get_jobs_by_stage(conn=conn, stage="pending_score", limit=limit)

    if not jobs:
        log.info("No unscored jobs with descriptions found.")
        return {"scored": 0, "errors": 0, "elapsed": 0.0, "distribution": []}

    # Convert sqlite3.Row to dicts if needed
    if jobs and not isinstance(jobs[0], dict):
        columns = jobs[0].keys()
        jobs = [dict(zip(columns, row)) for row in jobs]

    log.info("Scoring %d jobs sequentially...", len(jobs))
    t0 = time.time()
    completed = 0
    errors = 0
    results: list[dict] = []

    for job in jobs:
        result = score_job(resume_text, job, profile=profile)
        result["url"] = job["url"]
        completed += 1

        if result["score"] == 0:
            errors += 1

        results.append(result)

        log.info(
            "[%d/%d] score=%d  %s",
            completed, len(jobs), result["score"], job.get("title", "?")[:60],
        )

    # Write scores to DB
    now = datetime.now(timezone.utc).isoformat()
    for r in results:
        conn.execute(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ? WHERE url = ?",
            (r["score"], f"{r['keywords']}\n{r['reasoning']}", now, r["url"]),
        )
    conn.commit()

    elapsed = time.time() - t0
    log.info("Done: %d scored in %.1fs (%.1f jobs/sec)", len(results), elapsed, len(results) / elapsed if elapsed > 0 else 0)

    # Score distribution
    dist = conn.execute("""
        SELECT fit_score, COUNT(*) FROM jobs
        WHERE fit_score IS NOT NULL
        GROUP BY fit_score ORDER BY fit_score DESC
    """).fetchall()
    distribution = [(row[0], row[1]) for row in dist]

    return {
        "scored": len(results),
        "errors": errors,
        "elapsed": elapsed,
        "distribution": distribution,
    }
