"""Job fit scoring: LLM-powered evaluation of candidate-job match quality.

Scores jobs on a 1-10 scale by comparing the user's resume against each
job description. All personal data is loaded at runtime from the user's
profile and resume file.

Default path is batched (resume once + N short JDs per call). Sequential
fallback is used when SCORE_BATCH_SIZE=1 or a batch parse fails.

A new concurrent single-shot path (JOBWRIGHT_SCORE_WORKERS>0, default 20) is the
primary scoring path: one job per LLM call, full 6000-char description,
temperature 0, structured JSON output, profile prompt built once and reused as
a byte-identical prefix (prompt-cache friendly). Set JOBWRIGHT_SCORE_WORKERS=0
to keep the legacy batch+sequential path. Optional Jev fast-path hybrid
(D3, fastpath.py) runs first when the user config enables jev_hybrid.
"""

import concurrent.futures
import logging
import os
import random
import time
from datetime import datetime, timezone

import httpx

from jobwright.config import load_profile
from jobwright.database import get_connection, get_jobs_by_stage
from jobwright.discovery.filters import apply_fit_score_guards
from jobwright.llm import get_client
from jobwright.llm_json import LLMJsonError, chat_json_object, get_list_field, parse_json_object

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


def _load_applied_examples(conn, limit: int = 8) -> list[dict]:
    """Recent jobs the user actually applied to — the strongest positive signal."""
    rows = conn.execute(
        """
        SELECT title, company, site, fit_score
        FROM jobs
        WHERE applied_at IS NOT NULL
        ORDER BY applied_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def _load_score_calibration(conn) -> str:
    """Load recent human score corrections + applied jobs as few-shot calibration."""
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
    applied = _load_applied_examples(conn)
    if applied:
        lines.append(
            "\n\nJOBS THE USER APPLIED TO (strong positive signal — similar roles "
            "should score high):"
        )
        for i, d in enumerate(applied, 1):
            title = d.get("title") or "Unknown role"
            company = d.get("company") or d.get("site") or "Unknown"
            lines.append(f"{i}. {title} @ {company}")
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


# ── Concurrent single-shot path (D2) ──────────────────────────────────────

DEFAULT_SCORE_WORKERS = 20
# The schema-path request bypasses LLMClient's internal 5-retry ladder, so the
# outer loop is the only retry: 3 attempts with backoff absorbs 429 bursts and
# the rare json_schema 400 degrade without dropping jobs to skipped.
SCORE_SINGLE_ATTEMPTS = 3
# 60 was too small: the model writes reasoning before "score", truncating the
# JSON mid-object ("No valid JSON object found"). 300 fits score + 2-3 sentence
# reasoning with headroom.
SINGLE_MAX_TOKENS = 300

# OpenRouter/Fireworks json_schema response object: integer score 1-10 + reasoning.
SCORE_JSON_SCHEMA = {
    "name": "job_fit_score",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "score": {"type": "integer", "minimum": 1, "maximum": 10},
            "reasoning": {"type": "string"},
        },
        "required": ["score", "reasoning"],
        "additionalProperties": False,
    },
}


def _score_workers() -> int:
    """JOBWRIGHT_SCORE_WORKERS: 0 = legacy batch+sequential, >0 = concurrent single-shot."""
    raw = os.environ.get("JOBWRIGHT_SCORE_WORKERS", str(DEFAULT_SCORE_WORKERS)).strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return DEFAULT_SCORE_WORKERS


def _backoff_jitter(attempt: int, rng: random.Random) -> float:
    """Exponential backoff (base 1s, doubles per attempt) + uniform jitter."""
    base = 1.0 * (2 ** (attempt - 1))
    return base + rng.uniform(0.0, 0.5 * base)


def _is_retryable(exc: Exception) -> bool:
    """429/timeouts and parse failures are retried; config errors are not."""
    return isinstance(
        exc,
        (LLMJsonError, httpx.HTTPStatusError, httpx.TimeoutException, httpx.TransportError),
    )


def _try_schema_chat(client, messages: list[dict], *, max_tokens: int, temperature: float) -> str | None:
    """Best-effort json_schema structured output for OpenAI-compat providers.

    Degrades to ``None`` (caller falls back to json_object / prompt+parse) when
    the active client is not the real LLMClient, the provider rejects
    json_schema (400/404/422), or the request fails to send. 429/5xx are
    propagated so the scorer's retry loop handles them.
    """
    if not (
        hasattr(client, "base_url")
        and hasattr(client, "model")
        and hasattr(client, "_client")
        and not getattr(client, "_is_gemini", False)
    ):
        return None

    headers = {"Content-Type": "application/json"}
    if getattr(client, "api_key", ""):
        headers["Authorization"] = f"Bearer {client.api_key}"
    payload = {
        "model": client.model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_schema", "json_schema": SCORE_JSON_SCHEMA},
    }
    try:
        resp = client._client.post(
            f"{client.base_url}/chat/completions", json=payload, headers=headers
        )
    except Exception as exc:  # noqa: BLE001 - degrade on send failure
        log.warning("json_schema request failed (%s); degrading to json_object", exc)
        return None
    if resp.status_code in (400, 404, 422):
        log.info("Provider rejected json_schema (HTTP %s); degrading to json_object", resp.status_code)
        return None
    resp.raise_for_status()  # 429/5xx propagate to the retry loop
    data = resp.json()
    choice = (data.get("choices") or [{}])[0]
    content = (choice.get("message") or {}).get("content")
    if not (content or "").strip():
        raise LLMJsonError("Empty structured LLM response")
    return content


def _chat_single(client, messages: list[dict], *, max_tokens: int = SINGLE_MAX_TOKENS, temperature: float = 0.0) -> str:
    """One scoring call: prefer json_schema, then json_object, then prompt+parse.

    Returns the assistant message text.
    """
    schema_text = _try_schema_chat(
        client, messages, max_tokens=max_tokens, temperature=temperature
    )
    if schema_text is not None:
        return schema_text
    return client.chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True)


def score_job_single(
    resume_text: str,
    job: dict,
    *,
    system_prompt: str,
    search_cfg: dict | None = None,
    client: "object | None" = None,
) -> dict | None:
    """Score one job with the full 6000-char description in a single LLM call.

    Uses temperature 0 and a small token budget. Retries per-call on
    429/timeouts/parse errors (exponential backoff + jitter, 2 attempts), then
    returns None so the stage skips-with-warning instead of crashing.
    """
    user_msg = (
        f"RESUME:\n{resume_text}\n\n---\n\nJOB POSTING:\n"
        f"{_job_block(job, desc_chars=_SINGLE_DESC_CHARS)}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]
    rng = random.Random()
    for attempt in range(1, SCORE_SINGLE_ATTEMPTS + 1):
        try:
            client = client or get_client()
            raw = _chat_single(client, messages)
            data = parse_json_object(raw, json_mode=False)
            return apply_fit_score_guards(job, _parse_score_response(data), search_cfg)
        except Exception as exc:  # noqa: BLE001 - handled below (skip vs retry)
            if not _is_retryable(exc) or attempt >= SCORE_SINGLE_ATTEMPTS:
                log.warning(
                    "Single-shot score failed for '%s' (attempt %d/%d): %s",
                    job.get("title", "?"), attempt, SCORE_SINGLE_ATTEMPTS, exc,
                )
                return None
            wait = _backoff_jitter(attempt, rng)
            log.warning(
                "Scoring retry (%d/%d) for '%s' after %.2fs: %s",
                attempt, SCORE_SINGLE_ATTEMPTS, job.get("title", "?"), wait, exc,
            )
            time.sleep(wait)
    return None


def score_jobs_single_shot(
    resume_text: str,
    jobs: list[dict],
    profile: dict | None = None,
    calibration: str = "",
    search_cfg: dict | None = None,
    workers: int | None = None,
) -> tuple[list[dict], int]:
    """Concurrent single-shot scoring of many jobs.

    Builds the profile/system prefix ONCE and reuses the same string object
    across every call (byte-identical, prompt-cache friendly). Returns
    (results_with_url, errors).
    """
    n_workers = max(1, workers if workers is not None else _score_workers())
    system_prompt = _build_score_prompt(profile, calibration) + SINGLE_SCORE_TAIL
    # Build the LLMClient once HERE (main thread). get_client() is a lazy
    # singleton with mutable state (_use_native_gemini) and reset_client()
    # closes it; calling it from 20 threads concurrently caused the flaky
    # TransportError/parse skips. Workers reuse this shared instance (httpx
    # Client is thread-safe for concurrent requests).
    shared_client = get_client()

    def _score_one(job: dict) -> dict | None:
        return score_job_single(
            resume_text, job, system_prompt=system_prompt, search_cfg=search_cfg,
            client=shared_client,
        )

    results: list[dict] = []
    errors = 0
    if n_workers == 1 or len(jobs) <= 1:
        iterator = (_score_one(j) for j in jobs)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as executor:
            iterator = executor.map(_score_one, jobs)
    for job, result in zip(jobs, iterator):
        if result is None:
            errors += 1
        else:
            result["url"] = job["url"]
            results.append(result)
    return results, errors


def _jev_verdict(job: dict, jev: dict | None, verdict: str, search_cfg: dict | None = None) -> dict:
    """Build a scored-job dict that records a Jev fast-accept/fast-reject verdict.

    Routed through apply_fit_score_guards like every deepseek-scored job so the
    exclude_title ceiling / social-impact caps / location caps still apply.
    """
    try:
        score = int((jev or {}).get("jev_score"))
    except (TypeError, ValueError):
        score = 1
    score = max(1, min(10, score))
    conf = float((jev or {}).get("jev_confidence") or 0.0)
    raw = {
        "url": job["url"],
        "score": score,
        "keywords": "",
        "reasoning": f"Jev fastpath {verdict} (jev_score={score}, conf={conf:.2f})",
    }
    return apply_fit_score_guards(job, raw, search_cfg)


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

    workers = _score_workers()
    log.info("Scoring %d jobs (workers=%d)...", len(jobs), workers)

    # D3 hook: Jev fast-path (shadow|on) runs FIRST at the start of this stage.
    from jobwright.scoring import fastpath

    errors = 0
    results: list[dict] = []
    llm_jobs = jobs

    jev_mode = fastpath.get_jev_hybrid(profile)
    if jev_mode in ("shadow", "on") and jobs:
        jev_by_url = {
            r["url"]: r for r in fastpath.score_fastpath(jobs, profile or {}, conn) if r.get("url")
        }
        if jev_mode == "on":
            llm_jobs = []
            for job in jobs:
                jev = jev_by_url.get(job["url"])
                route = jev.get("jev_route") if jev else None
                if route == "fast_accept":
                    results.append(_jev_verdict(job, jev, "accept", search_cfg))
                    log.info("Jev fast-accept (deepseek skipped): %s", job.get("title", "?"))
                elif route == "fast_reject":
                    results.append(_jev_verdict(job, jev, "reject", search_cfg))
                    log.info("Jev fast-reject (deepseek skipped): %s", job.get("title", "?"))
                else:
                    llm_jobs.append(job)
            log.info(
                "Jev '%s' routed %d via fastpath; escalating %d to deepseek",
                jev_mode, len(results), len(llm_jobs),
            )

    t0 = time.time()
    done = len(results)
    if workers > 0:
        llm_scored, llm_errors = score_jobs_single_shot(
            resume_text, llm_jobs, profile=profile, calibration=calibration,
            search_cfg=search_cfg, workers=workers,
        )
        results.extend(llm_scored)
        errors += llm_errors
        done += len(llm_scored)
        for item in llm_scored:
            log.info("[%d/%d] score=%d  %s", done, len(jobs), item["score"], (item.get("url") or "")[-50:])
    else:
        # Legacy batch+sequential path (SCORE_BATCH_SIZE / JOBWRIGHT_SCORE_WORKERS=0).
        batch_size = _batch_size()
        chunks: list[list[dict]] = (
            [llm_jobs[i : i + batch_size] for i in range(0, len(llm_jobs), batch_size)]
            if batch_size > 1
            else [[j] for j in llm_jobs]
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
