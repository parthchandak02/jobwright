"""Cover letter generation: LLM-powered, profile-driven, with validation.

Generates concise, engineering-voice cover letters tailored to specific job
postings. All personal data (name, skills, achievements) comes from the user's
profile at runtime. No hardcoded personal information.
"""

import logging
import re
import time
from datetime import datetime, timezone

from jobwright.config import load_profile
import jobwright.config as config
from jobwright.database import get_connection
from jobwright.llm import get_client
from jobwright.scoring.portfolio import get_selected_projects
from jobwright.scoring.validator import (
    BANNED_WORDS,
    LLM_LEAK_PHRASES,
    sanitize_text,
    validate_cover_letter,
)

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5  # max cross-run retries before giving up


# ── Prompt Builder (profile-driven) ──────────────────────────────────────

def _build_cover_letter_prompt(profile: dict, template: str = "", examples: list[str] | None = None) -> str:
    """Build the cover letter system prompt from the user's profile.

    All personal data, skills, and sign-off name come from the profile.
    When template/examples are provided, steer away from resume copy-paste.
    """
    personal = profile.get("personal", {})
    boundary = profile.get("skills_boundary", {})
    resume_facts = profile.get("resume_facts", {})
    mode = profile.get("cover_letter_mode", "default")

    # Preferred name for the sign-off (falls back to full name)
    sign_off_name = personal.get("preferred_name") or personal.get("full_name", "")

    # Flatten all allowed skills
    all_skills: list[str] = []
    for items in boundary.values():
        if isinstance(items, list):
            all_skills.extend(items)
    skills_str = ", ".join(all_skills) if all_skills else "the tools listed in the resume"

    # Real metrics from resume_facts
    real_metrics = resume_facts.get("real_metrics", [])
    preserved_projects = resume_facts.get("preserved_projects", [])

    # Build achievement examples for the prompt
    projects_hint = ""
    if preserved_projects:
        projects_hint = f"\nKnown projects to reference: {', '.join(preserved_projects)}"

    metrics_hint = ""
    if real_metrics:
        metrics_hint = f"\nReal metrics to use: {', '.join(real_metrics)}"

    # Build the full banned list from the validator so the prompt stays in sync
    # with what will actually be rejected — the validator checks all of these.
    all_banned = ", ".join(f'"{w}"' for w in BANNED_WORDS)
    leak_banned = ", ".join(f'"{p}"' for p in LLM_LEAK_PHRASES)

    voice_line = (
        "Write like a seasoned strategy/impact operator emailing someone they respect. Not formal, not casual."
        if mode == "template"
        else "Write like a real engineer emailing someone they respect. Not formal, not casual."
    )

    template_block = ""
    if template:
        template_block = f"""

COVER LETTER TEMPLATE (follow this structure and tone; adapt placeholders per job):
---
{template[:4000]}
---"""

    examples_block = ""
    if examples:
        joined = config.join_cover_letter_examples(examples)
        examples_block = f"""

EXAMPLE LETTERS THE CANDIDATE HAS ACTUALLY SENT (amalgamate this voice and structure; use NEW stories, do NOT copy them verbatim):
---
{joined}
---"""

    resume_rule = ""
    if mode == "template" or examples:
        resume_rule = """
RESUME RULE: The resume is background only. Cover letter must add NEW angles and examples.
Do NOT restate resume bullets. Pick different stories or framing than the resume."""

    return f"""Write a cover letter for {sign_off_name}. The goal is to get an interview.{template_block}{examples_block}{resume_rule}

STRUCTURE: 3 short paragraphs. Under 250 words. Every sentence must earn its place.

PARAGRAPH 1 (2-3 sentences): Open with a specific thing YOU built that solves THEIR problem. Not "I'm excited about this role." Not "This role aligns with my experience." Start with the work.

PARAGRAPH 2 (3-4 sentences): Pick 2 achievements from the resume that are MOST relevant to THIS job. Use numbers. Frame as solving their problem, not listing your accomplishments.{projects_hint}{metrics_hint}

PARAGRAPH 3 (1-2 sentences): One specific thing about the company from the job description (a product, a technical challenge, a team structure). Then close. "Happy to walk through any of this in more detail." or "Let's discuss." Nothing else.

BANNED WORDS AND PHRASES (automated validator rejects ANY of these — do not use even once):
{all_banned}

ALSO BANNED (meta-commentary the validator catches):
{leak_banned}

BANNED PUNCTUATION: No em dashes (—) or en dashes (–). Use commas or periods.

VOICE:
- {voice_line} Just direct.
- NEVER narrate or explain what you're doing. BAD: "This demonstrates my commitment to X." GOOD: Just state the fact and move on.
- NEVER hedge. BAD: "might address some of your challenges." GOOD: "solves the same problem your team is facing."
- Every sentence should contain either a number, a tool name, or a specific outcome. If it doesn't, cut it.
- Read it out loud. If it sounds like a robot wrote it, rewrite it.

FABRICATION = INSTANT REJECTION:
The candidate's real tools are ONLY: {skills_str}.
Do NOT mention ANY tool not in this list. If the job asks for tools not listed, talk about the work you did, not the tools.

Sign off: just "{sign_off_name}"

Output ONLY the letter text. No subject lines. No "Here is the cover letter:" preamble. No notes after the sign-off.
Start DIRECTLY with "Dear Hiring Manager," and end with the name."""


# ── Helpers ──────────────────────────────────────────────────────────────

def _strip_preamble(text: str) -> str:
    """Remove LLM preamble before 'Dear Hiring Manager,' if present.

    Gemini and other models sometimes output "Here is the cover letter:" or
    similar meta-commentary before the actual letter text. Strip everything
    before the first occurrence of "Dear" so the validator's start-check passes.
    """
    dear_idx = text.lower().find("dear")
    if dear_idx > 0:
        return text[dear_idx:]
    return text


# ── Core Generation ──────────────────────────────────────────────────────

def generate_cover_letter(
    resume_text: str, job: dict, profile: dict,
    max_retries: int = 3, validation_mode: str = "normal",
    extra_instructions: str | None = None,
) -> str:
    """Generate a cover letter with fresh context on each retry + auto-sanitize.

    Same design as tailor_resume: fresh conversation per attempt, issues noted
    in the prompt, no conversation history stacking.

    Args:
        resume_text:      The candidate's resume text (base or tailored).
        job:              Job dict with title, site, location, full_description.
        profile:          User profile dict.
        max_retries:      Maximum retry attempts.
        validation_mode:  "strict", "normal", or "lenient".

    Returns:
        The cover letter text (best attempt even if validation failed).
    """
    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job['site']}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n\n"
        f"DESCRIPTION:\n{(job.get('full_description') or '')[:6000]}"
    )

    selected_projects = get_selected_projects(profile, job)
    if selected_projects:
        names = ", ".join(p.get("name", p.get("id", "")) for p in selected_projects)
        job_text += f"\n\nREFERENCE THESE PORTFOLIO PROJECTS BY NAME: {names}"

    avoid_notes: list[str] = []
    letter = ""
    client = get_client()
    template_text, example_texts = config.load_cover_letter_materials(profile)
    if extra_instructions is not None:
        from jobwright.scoring.tailor_instructions import build_dashboard_cover_prompt

        log.info("Using dashboard cover instructions (%d chars)", len(extra_instructions))
        log.info("Cover instructions:\n%s", extra_instructions[:4000])
        cl_prompt_base = build_dashboard_cover_prompt(
            profile,
            template=template_text,
            examples=example_texts or None,
            user_instructions=extra_instructions,
        )
    else:
        cl_prompt_base = _build_cover_letter_prompt(
            profile, template=template_text, examples=example_texts or None,
        )

    for attempt in range(max_retries + 1):
        log.info(
            "LLM cover letter attempt %d/%d for %s @ %s",
            attempt + 1,
            max_retries + 1,
            job.get("title"),
            job.get("site"),
        )
        # Fresh conversation every attempt
        prompt = cl_prompt_base
        if avoid_notes:
            prompt += "\n\n## AVOID THESE ISSUES:\n" + "\n".join(
                f"- {n}" for n in avoid_notes[-5:]
            )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": (
                f"RESUME:\n{resume_text}\n\n---\n\n"
                f"TARGET JOB:\n{job_text}\n\n"
                "Write the cover letter:"
            )},
        ]

        # Reasoning models (gpt-oss) spend hidden tokens before emitting the
        # letter; a tight budget yields finish_reason=length with empty content.
        letter = client.chat(messages, max_tokens=4096, temperature=0.7)
        letter = sanitize_text(letter)  # auto-fix em dashes, smart quotes
        letter = _strip_preamble(letter)  # remove any "Here is the letter:" prefix

        validation = validate_cover_letter(letter, mode=validation_mode)
        if validation["passed"]:
            log.info("Cover letter validated (%d chars)", len(letter))
            return letter

        avoid_notes.extend(validation["errors"])
        log.info(
            "Cover letter attempt %d/%d failed validation: %s",
            attempt + 1, max_retries + 1, validation["errors"],
        )

    return letter  # last attempt even if failed


def _job_file_prefix(job: dict) -> str:
    safe_title = re.sub(r"[^\w\s-]", "", job.get("title") or "untitled")[:50].strip().replace(" ", "_")
    safe_site = re.sub(r"[^\w\s-]", "", job.get("site") or "manual")[:20].strip().replace(" ", "_")
    return f"{safe_site}_{safe_title}"


def _persist_cover_result(conn, job: dict, letter: str) -> dict:
    """Save cover letter files and update DB (single job)."""
    from jobwright.database import maybe_agent_advance_to_prepare
    from jobwright.scoring.materials_format import format_cover_letter_markdown

    letter = format_cover_letter_markdown(letter)
    prefix = _job_file_prefix(job)
    cl_path = config.COVER_LETTER_DIR / f"{prefix}_CL.md"
    cl_path.write_text(letter, encoding="utf-8")

    pdf_path = None
    try:
        from jobwright.scoring.pdf import convert_to_pdf
        pdf_path = str(convert_to_pdf(cl_path))
    except Exception:
        log.debug("PDF generation failed for %s", cl_path, exc_info=True)

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE jobs SET cover_letter_path=?, cover_letter_at=?, "
        "cover_attempts=COALESCE(cover_attempts,0)+1 WHERE url=?",
        (str(cl_path), now, job["url"]),
    )
    maybe_agent_advance_to_prepare(job["url"], conn=conn)
    conn.commit()

    return {
        "url": job["url"],
        "path": str(cl_path),
        "pdf_path": pdf_path,
        "title": job["title"],
        "site": job["site"],
    }


def cover_one_job(
    url: str,
    *,
    resume_text: str | None = None,
    validation_mode: str = "normal",
    extra_instructions: str | None = None,
    conn=None,
) -> dict:
    """Generate cover letter for a single job URL (dashboard action; no min_score gate)."""
    from jobwright.database import get_connection
    from jobwright.resume import load_resume_text

    owns_conn = conn is None
    if owns_conn:
        conn = get_connection()

    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if row is None:
        raise ValueError("job not found")
    job = dict(row)

    description = (job.get("full_description") or job.get("description") or "").strip()
    if not description:
        raise ValueError("job description required")
    if not job.get("full_description"):
        job["full_description"] = description

    profile = load_profile()
    if resume_text is None:
        resume_text = load_resume_text()
    config.COVER_LETTER_DIR.mkdir(parents=True, exist_ok=True)

    try:
        letter = generate_cover_letter(
            resume_text, job, profile,
            validation_mode=validation_mode,
            extra_instructions=extra_instructions,
        )
        return _persist_cover_result(conn, job, letter)
    except Exception as e:
        conn.execute(
            "UPDATE jobs SET cover_attempts=COALESCE(cover_attempts,0)+1 WHERE url=?",
            (url,),
        )
        conn.commit()
        return {
            "url": url,
            "path": None,
            "pdf_path": None,
            "title": job.get("title"),
            "site": job.get("site"),
            "error": str(e),
        }


# ── Batch Entry Point ────────────────────────────────────────────────────

def run_cover_letters(min_score: int = 7, limit: int = 20,
                      validation_mode: str = "normal") -> dict:
    """Generate cover letters for high-scoring jobs that have tailored resumes.

    Args:
        min_score:       Minimum fit_score threshold.
        limit:           Maximum jobs to process.
        validation_mode: "strict", "normal", or "lenient".

    Returns:
        {"generated": int, "errors": int, "elapsed": float}
    """
    profile = load_profile()
    from jobwright.resume import load_resume_text

    resume_text = load_resume_text()
    conn = get_connection()

    # Fetch jobs that have tailored resumes but no cover letter yet
    from jobwright.database import ANTI_CLOBBER_SQL

    jobs = conn.execute(
        "SELECT * FROM jobs "
        "WHERE fit_score >= ? AND tailored_resume_path IS NOT NULL "
        "AND full_description IS NOT NULL "
        "AND (cover_letter_path IS NULL OR cover_letter_path = '') "
        "AND COALESCE(cover_attempts, 0) < ? "
        f"{ANTI_CLOBBER_SQL} "
        "ORDER BY fit_score DESC LIMIT ?",
        (min_score, MAX_ATTEMPTS, limit),
    ).fetchall()

    if not jobs:
        log.info("No jobs needing cover letters (score >= %d).", min_score)
        return {"generated": 0, "errors": 0, "elapsed": 0.0}

    # Convert rows to dicts
    if jobs and not isinstance(jobs[0], dict):
        columns = jobs[0].keys()
        jobs = [dict(zip(columns, row)) for row in jobs]

    config.COVER_LETTER_DIR.mkdir(parents=True, exist_ok=True)
    log.info(
        "Generating cover letters for %d jobs (score >= %d)...",
        len(jobs), min_score,
    )
    t0 = time.time()
    completed = 0
    results: list[dict] = []
    error_count = 0

    for job in jobs:
        completed += 1
        try:
            letter = generate_cover_letter(resume_text, job, profile,
                                          validation_mode=validation_mode)
            result = _persist_cover_result(conn, job, letter)
        except Exception as e:
            conn.execute(
                "UPDATE jobs SET cover_attempts=COALESCE(cover_attempts,0)+1 WHERE url=?",
                (job["url"],),
            )
            conn.commit()
            result = {
                "url": job["url"], "title": job["title"], "site": job["site"],
                "path": None, "pdf_path": None, "error": str(e),
            }
            error_count += 1
            log.error("%d/%d [ERROR] %s -- %s", completed, len(jobs), job["title"][:40], e)

        results.append(result)
        elapsed = time.time() - t0
        rate = completed / elapsed if elapsed > 0 else 0
        if result.get("path"):
            log.info(
                "%d/%d [OK] | %.1f jobs/min | %s",
                completed, len(jobs), rate * 60, result["title"][:40],
            )

    saved = sum(1 for r in results if r.get("path"))
    elapsed = time.time() - t0
    log.info("Cover letters done in %.1fs: %d generated, %d errors", elapsed, saved, error_count)

    return {
        "generated": saved,
        "errors": error_count,
        "elapsed": elapsed,
    }
