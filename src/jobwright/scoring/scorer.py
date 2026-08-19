"""Job fit scoring: LLM-powered evaluation of candidate-job match quality.

Scores jobs on a 1-10 scale by comparing the user's resume against each
job description. All personal data is loaded at runtime from the user's
profile and resume file.

Default path is batched (resume once + N short JDs per call). Sequential
fallback is used when SCORE_BATCH_SIZE=1 or a batch parse fails.
"""

import logging
import os
import time
from datetime import datetime, timezone

from jobwright.config import load_profile
from jobwright.database import get_connection, get_jobs_by_stage
from jobwright.discovery.filters import apply_fit_score_guards
from jobwright.llm import get_client
from jobwright.llm_json import LLMJsonError, chat_json_object, get_list_field

log = logging.getLogger(__name__)

# ponytail: ~10 jobs/call is the ceiling — one giant JSON of all jobs truncates.
_DEFAULT_BATCH_SIZE = 10
_BATCH_DESC_CHARS = 800
_SINGLE_DESC_CHARS = 6000


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
- When the target role includes social impact, CSR, philanthropy, or community investment: score 9-10 only for program, foundation, grantmaking, CSR/corporate purpose, community investment, or impact-fund roles. Score generic tech business operations, GTM partnerships, clinical/home-health ops, and Chief of Staff at companies with no social-impact mission at most 4.
- Prefer consulting, partnerships, and program leadership when those skills show up IN an impact/CSR/foundation role. Do not treat transferable ops skills as enough for a high score.
- Penalize roles that are primarily technical (software engineering, data science, deep ESG/climate science, heavy finance/IB) when the guidance says to avoid them.
- Be realistic about experience level vs. job requirements (years of experience, seniority).
- If salary is listed and clearly below the candidate's floor, score lower (max 4)."""

SINGLE_SCORE_TAIL = """
Return ONLY a JSON object with this exact shape:
{"score": <integer 1-10>, "keywords": "<comma-separated ATS keywords>", "reasoning": "<2-3 sentences>"}"""

BATCH_SCORE_TAIL = """
You will receive ONE resume and several numbered jobs. Score every job against
the same resume using the criteria above. Compare jobs in the batch so similar
roles get similar scores.

Return ONLY a JSON object:
{"scores": [{"id": <job number>, "score": <integer 1-10>, "keywords": "<comma-separated ATS keywords>", "reasoning": "<1-2 sentences>"}]}
Include one object per job id. Do not omit jobs."""


def _build_score_prompt(profile: dict | None, calibration: str = "") -> str:
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

    prompt = (
        SCORE_PROMPT_BASE
        + "\n\nCANDIDATE TARGET-ROLE GUIDANCE:\n"
        + "\n".join(guidance_lines)
    )
    if calibration:
        prompt += calibration
    return prompt


_MAX_CALIBRATION_EXAMPLES = 12


def _load_score_calibration(conn) -> str:
    """Load recent human score corrections as few-shot calibration for the LLM."""
    rows = conn.execute(
        """
        SELECT title, company, site, fit_score, user_fit_score, user_score_rationale
        FROM jobs
        WHERE user_fit_score IS NOT NULL
          AND user_score_rationale IS NOT NULL
          AND trim(user_score_rationale) != ''
        ORDER BY user_score_at DESC
        LIMIT ?
        """,
        (_MAX_CALIBRATION_EXAMPLES,),
    ).fetchall()
    if not rows:
        return ""
    lines = [
        "\n\nHUMAN SCORE CALIBRATION (learn from these corrections; align future scores):"
    ]
    for i, row in enumerate(rows, 1):
        d = dict(row)
        title = d.get("title") or "Unknown role"
        company = d.get("company") or d.get("site") or "Unknown"
        ai = d.get("fit_score")
        user = d.get("user_fit_score")
        rationale = (d.get("user_score_rationale") or "").strip()[:400]
        ai_part = f"AI scored {ai}" if ai is not None else "AI unscored"
        lines.append(
            f"{i}. {title} @ {company} — {ai_part}, human corrected to {user}. "
            f"Rationale: {rationale}"
        )
    return "\n".join(lines)


# Back-compat alias for imports/tests
SCORE_PROMPT = SCORE_PROMPT_BASE


def _parse_score_response(data: dict) -> dict:
    """Validate and normalize a scored job JSON object."""
    try:
        score = int(data.get("score", 0))
        score = max(1, min(10, score))
    except (TypeError, ValueError):
        raise LLMJsonError(f"Invalid score field: {data.get('score')!r}")
    keywords = str(data.get("keywords") or "").strip()
    reasoning = str(data.get("reasoning") or "").strip()
    if not reasoning:
        raise LLMJsonError("Missing reasoning field")
    return {"score": score, "keywords": keywords, "reasoning": reasoning}


def _batch_size() -> int:
    raw = os.environ.get("SCORE_BATCH_SIZE", str(_DEFAULT_BATCH_SIZE)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_BATCH_SIZE


def _job_block(job: dict, index: int | None = None, desc_chars: int = _SINGLE_DESC_CHARS) -> str:
    header = f"[{index}] " if index is not None else ""
    return (
        f"{header}TITLE: {job['title']}\n"
        f"COMPANY: {job.get('company') or job.get('site')}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n"
        f"SALARY: {job.get('salary') or 'N/A'}\n"
        f"DESCRIPTION:\n{(job.get('full_description') or '')[:desc_chars]}"
    )


def _map_batch_scores(
    jobs: list[dict],
    data: dict,
    search_cfg: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """Map LLM batch JSON onto jobs. Returns (scored, missing)."""
    items = get_list_field(data, "scores", "jobs")
    by_id: dict[int, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            idx = int(item.get("id") or item.get("index") or 0)
        except (TypeError, ValueError):
            continue
        if idx < 1:
            continue
        by_id[idx] = item

    scored: list[dict] = []
    missing: list[dict] = []
    for i, job in enumerate(jobs, start=1):
        raw = by_id.get(i)
        if raw is None:
            missing.append(job)
            continue
        try:
            parsed = apply_fit_score_guards(job, _parse_score_response(raw), search_cfg)
        except LLMJsonError:
            missing.append(job)
            continue
        parsed["url"] = job["url"]
        scored.append(parsed)
    return scored, missing


def score_jobs_batch(
    resume_text: str,
    jobs: list[dict],
    profile: dict | None = None,
    calibration: str = "",
    search_cfg: dict | None = None,
) -> tuple[list[dict], list[dict]]:
    """Score a small batch of jobs in one LLM call. Missing jobs returned for retry."""
    if not jobs:
        return [], []
    if len(jobs) == 1:
        one = score_job(
            resume_text, jobs[0], profile=profile, calibration=calibration, search_cfg=search_cfg,
        )
        if one is None:
            return [], jobs
        one["url"] = jobs[0]["url"]
        return [one], []

    blocks = [_job_block(job, index=i, desc_chars=_BATCH_DESC_CHARS) for i, job in enumerate(jobs, start=1)]
    messages = [
        {"role": "system", "content": _build_score_prompt(profile, calibration) + BATCH_SCORE_TAIL},
        {
            "role": "user",
            "content": (
                f"RESUME:\n{resume_text}\n\n---\n\nJOBS:\n"
                + "\n\n".join(blocks)
                + "\n\nReturn JSON with a scores array covering ids 1-"
                + str(len(jobs))
                + "."
            ),
        },
    ]
    try:
        client = get_client()
        data = chat_json_object(
            client,
            messages,
            max_tokens=min(400 * len(jobs) + 1024, 8192),
            temperature=0.2,
        )
        return _map_batch_scores(jobs, data, search_cfg)
    except (LLMJsonError, Exception) as e:
        log.warning("Batch score failed (%d jobs): %s — falling back to sequential", len(jobs), e)
        return [], jobs


def score_job(
    resume_text: str,
    job: dict,
    profile: dict | None = None,
    calibration: str = "",
    search_cfg: dict | None = None,
) -> dict | None:
    """Score a single job against the resume.

    Args:
        resume_text: The candidate's full resume text.
        job: Job dict with keys: title, site, location, full_description.
        profile: Optional profile for target-role guidance.

    Returns:
        {"score": int, "keywords": str, "reasoning": str} or None on parse/LLM failure.
    """
    messages = [
        {"role": "system", "content": _build_score_prompt(profile, calibration) + SINGLE_SCORE_TAIL},
        {
            "role": "user",
            "content": f"RESUME:\n{resume_text}\n\n---\n\nJOB POSTING:\n{_job_block(job)}",
        },
    ]

    try:
        client = get_client()
        data = chat_json_object(
            client,
            messages,
            max_tokens=2048,
            temperature=0.2,
            max_parse_retries=2,
        )
        return apply_fit_score_guards(job, _parse_score_response(data), search_cfg)
    except (LLMJsonError, Exception) as e:
        log.error("LLM error scoring job '%s': %s", job.get("title", "?"), e)
        if os.environ.get("GEMINI_API_KEY"):
            try:
                from jobwright.llm import reset_client

                reset_client()
                client = get_client()
                data = chat_json_object(
                    client,
                    messages,
                    max_tokens=2048,
                    temperature=0.2,
                    max_parse_retries=2,
                )
                return apply_fit_score_guards(job, _parse_score_response(data), search_cfg)
            except (LLMJsonError, Exception) as retry_exc:
                log.error(
                    "Score retry failed for '%s': %s",
                    job.get("title", "?"),
                    retry_exc,
                )
        return None


def run_scoring(limit: int = 0, rescore: bool = False) -> dict:
    """Score unscored jobs that have full descriptions.

    Args:
        limit: Maximum number of jobs to score in this run.
        rescore: If True, re-score all jobs (not just unscored ones).

    Returns:
        {"scored": int, "errors": int, "elapsed": float, "distribution": list}
    """
    from jobwright.resume import load_resume_text

    resume_text = load_resume_text()
    try:
        profile = load_profile()
    except FileNotFoundError:
        profile = None
    try:
        from jobwright.config import load_search_config

        search_cfg = load_search_config()
    except Exception:
        search_cfg = {}
    conn = get_connection()
    calibration = _load_score_calibration(conn)

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

    batch_size = _batch_size()
    log.info("Scoring %d jobs (batch_size=%d)...", len(jobs), batch_size)
    t0 = time.time()
    errors = 0
    results: list[dict] = []
    done = 0

    chunks: list[list[dict]] = (
        [jobs[i : i + batch_size] for i in range(0, len(jobs), batch_size)]
        if batch_size > 1
        else [[j] for j in jobs]
    )

    for chunk in chunks:
        scored, leftover = score_jobs_batch(
            resume_text, chunk, profile=profile, calibration=calibration, search_cfg=search_cfg,
        )
        results.extend(scored)
        done += len(scored)
        for item in scored:
            log.info(
                "[%d/%d] score=%d  %s",
                done, len(jobs), item["score"], (item.get("url") or "")[-50:],
            )
        for job in leftover:
            result = score_job(
                resume_text, job, profile=profile, calibration=calibration, search_cfg=search_cfg,
            )
            done += 1
            if result is None:
                errors += 1
                log.warning("[%d/%d] score failed  %s", done, len(jobs), job.get("title", "?")[:60])
                continue
            result["url"] = job["url"]
            results.append(result)
            log.info(
                "[%d/%d] score=%d  %s",
                done, len(jobs), result["score"], job.get("title", "?")[:60],
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
