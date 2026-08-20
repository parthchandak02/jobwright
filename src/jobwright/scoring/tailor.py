"""Resume tailoring: LLM-powered ATS-optimized resume generation per job.

THIS IS THE HEAVIEST REFACTOR. Every piece of personal data -- name, email, phone,
skills, companies, projects, school -- is loaded at runtime from the user's profile.
Zero hardcoded personal information.

The LLM returns structured JSON, code assembles the final text. Header (name, contact)
is always code-injected, never LLM-generated. Each retry starts a fresh conversation
to avoid apologetic spirals.
"""

import json
import logging
import re
import time
from datetime import UTC, datetime

from jobwright import config
from jobwright.config import load_profile
from jobwright.database import get_connection, get_jobs_by_stage
from jobwright.llm import get_client
from jobwright.llm_json import LLMJsonError, parse_json_object
from jobwright.scoring.materials_format import resolve_material_path
from jobwright.scoring.portfolio import get_selected_projects
from jobwright.scoring.validator import (
    BANNED_WORDS,
    validate_json_fields,
)

log = logging.getLogger(__name__)

MAX_ATTEMPTS = 5  # max cross-run retries before giving up

SUCCESS_STATUSES = frozenset({"approved", "approved_with_judge_warning"})
_SUCCESS_STATUSES = SUCCESS_STATUSES


# ── Prompt Builders (profile-driven) ──────────────────────────────────────

def _build_tailor_prompt(profile: dict) -> str:
    """Build the resume tailoring system prompt from the user's profile.

    All skills boundaries, preserved entities, and formatting rules are
    derived from the profile -- nothing is hardcoded.
    """
    boundary = profile.get("skills_boundary", {})
    resume_facts = profile.get("resume_facts", {})

    # Format skills boundary for the prompt
    skills_lines = []
    for category, items in boundary.items():
        if isinstance(items, list) and items:
            label = category.replace("_", " ").title()
            skills_lines.append(f"{label}: {', '.join(items)}")
    skills_block = "\n".join(skills_lines)

    # Preserved entities
    companies = resume_facts.get("preserved_companies", [])
    school = resume_facts.get("preserved_school", "")
    real_metrics = resume_facts.get("real_metrics", [])

    companies_str = ", ".join(companies) if companies else "N/A"
    metrics_str = ", ".join(real_metrics) if real_metrics else "N/A"

    # Include ALL banned words from the validator so the LLM knows exactly
    # what will be rejected — the validator checks for these automatically.
    banned_str = ", ".join(BANNED_WORDS)

    education = profile.get("experience", {})
    education_level = education.get("education_level", "")

    _, examples = config.load_cover_letter_materials(profile)
    examples_block = ""
    if examples:
        joined = config.join_cover_letter_examples(examples)
        examples_block = f"""

## SENT COVER LETTERS (voice and emphasis only):
Amalgamate how this person writes about their work. Do NOT paste letter prose into the resume. Do NOT invent facts from the letters that are not in the base resume.
---
{joined}
---
"""

    return f"""You are a senior technical recruiter rewriting a resume to get this person an interview.{examples_block}

Take the base resume and job description. Return a tailored resume as a JSON object.

## RECRUITER SCAN (6 seconds):
1. Title -- matches what they're hiring?
2. Summary -- 2 sentences proving you've done this work
3. First 3 bullets of most recent role -- verbs and outcomes match?
4. Skills -- must-haves visible immediately?

## SKILLS BOUNDARY (real skills only):
{skills_block}

You MAY add 2-3 closely related tools (Kubernetes if Docker, Terraform if AWS, Redis if PostgreSQL). No unrelated languages/frameworks.

## TAILORING RULES:

TITLE: Match the target role. Keep seniority (Senior/Lead/Staff). Drop company suffixes and team names.

SUMMARY: Rewrite from scratch. Lead with the 1-2 skills that matter most for THIS role. Sound like someone who's done this job.

SKILLS: Reorder each category so the job's must-haves appear first.

Reframe EVERY bullet for this role. Same real work, different angle. Every bullet must be reworded. Never copy verbatim.

PROJECTS: Reorder by relevance. Drop irrelevant projects entirely.

BULLETS: Strong verb + what you built + quantified impact. Vary verbs (Built, Designed, Implemented, Reduced, Automated, Deployed, Operated, Optimized). Most relevant first. Max 4 per section.

## VOICE:
- Write like a real engineer. Short, direct.
- GOOD: "Automated financial reporting with Python + API integrations, cut processing time from 10 hours to 2"
- BAD: "Leveraged cutting-edge AI technologies to drive transformative operational efficiencies"
- BANNED WORDS (using ANY of these = validation failure — do not use them even once):
  {banned_str}
- No em dashes. Use commas, periods, or hyphens.

## HARD RULES:
- Do NOT invent work, companies, degrees, or certifications
- Do NOT change real numbers ({metrics_str})
- Preserved companies: {companies_str} -- names stay as-is
- Preserved school: {school}
- Must fit 1 page.

## OUTPUT: Return ONLY valid JSON. No markdown fences. No commentary. No "here is" preamble.

{{"title":"Role Title","summary":"2-3 tailored sentences.","skills":{{"Languages":"...","Frameworks":"...","DevOps & Infra":"...","Databases":"...","Tools":"..."}},"experience":[{{"header":"Title at Company","subtitle":"Tech | Dates","bullets":["bullet 1","bullet 2","bullet 3","bullet 4"]}}],"projects":[{{"header":"Project Name - Description","subtitle":"Tech | Dates","bullets":["bullet 1","bullet 2"]}}],"education":"{school} | {education_level}"}}"""


def _build_judge_prompt(profile: dict) -> str:
    """Build the LLM judge prompt from the user's profile."""
    boundary = profile.get("skills_boundary", {})
    resume_facts = profile.get("resume_facts", {})

    # Flatten allowed skills for the judge
    all_skills: list[str] = []
    for items in boundary.values():
        if isinstance(items, list):
            all_skills.extend(items)
    skills_str = ", ".join(all_skills) if all_skills else "N/A"

    real_metrics = resume_facts.get("real_metrics", [])
    metrics_str = ", ".join(real_metrics) if real_metrics else "N/A"

    return f"""You are a resume quality judge. A tailoring engine rewrote a resume to target a specific job. Your job is to catch LIES, not style changes.

You must answer with EXACTLY this format:
VERDICT: PASS or FAIL
ISSUES: (list any problems, or "none")

## CONTEXT -- what the tailoring engine was instructed to do (all of this is ALLOWED):
- Change the title to match the target role
- Rewrite the summary from scratch for the target job
- Reorder bullets and projects to put the most relevant first
- Reframe bullets to use the job's language
- Drop low-relevance bullets and replace with more relevant ones from other sections
- Reorder the skills section to put job-relevant skills first
- Change tone and wording extensively

## WHAT IS FABRICATION (FAIL for these):
1. Adding tools, languages, or frameworks to TECHNICAL SKILLS that aren't in the original. The allowed skills are ONLY: {skills_str}
2. Inventing NEW metrics or numbers not in the original. The real metrics are: {metrics_str}
3. Inventing work that has no basis in any original bullet (completely new achievements).
4. Adding companies, roles, or degrees that don't exist.
5. Changing real numbers (inflating 80% to 95%, 500 nodes to 1000 nodes).

## WHAT IS NOT FABRICATION (do NOT fail for these):
- Rewording any bullet, even heavily, as long as the underlying work is real
- Combining two original bullets into one
- Splitting one original bullet into two
- Describing the same work with different emphasis
- Dropping bullets entirely
- Reordering anything
- Changing the title or summary completely

## TOLERANCE RULE:
The goal is to get interviews, not to be a perfect fact-checker. Allow up to 3 minor stretches per resume:
- Adding a closely related tool the candidate could realistically know is a MINOR STRETCH, not fabrication.
- Reframing a metric with slightly different wording is a MINOR STRETCH.
- Adding any LEARNABLE skill given their existing stack is a MINOR STRETCH.
- Only FAIL if there are MAJOR lies: completely invented projects, fake companies, fake degrees, wildly inflated numbers, or skills from a completely different domain.

Be strict about major lies. Be lenient about minor stretches and learnable skills. Do not fail for style, tone, or restructuring."""


# ── JSON Extraction ───────────────────────────────────────────────────────

def extract_json(raw: str) -> dict:
    """Parse JSON object from an LLM response (json_mode or legacy text)."""
    try:
        return parse_json_object(raw, json_mode=True)
    except LLMJsonError:
        return parse_json_object(raw, json_mode=False)


# ── Resume Assembly (profile-driven header) ──────────────────────────────

def assemble_resume_text(data: dict, profile: dict) -> str:
    """Convert JSON resume data to markdown (alias for assemble_resume_markdown)."""
    from jobwright.scoring.materials_format import assemble_resume_markdown

    return assemble_resume_markdown(data, profile)


# ── LLM Judge ────────────────────────────────────────────────────────────

def judge_tailored_resume(
    original_text: str, tailored_text: str, job_title: str, profile: dict
) -> dict:
    """LLM judge layer: catches subtle fabrication that programmatic checks miss.

    Args:
        original_text: Base resume text.
        tailored_text: Tailored resume text.
        job_title: Target job title.
        profile: User profile for building the judge prompt.

    Returns:
        {"passed": bool, "verdict": str, "issues": str, "raw": str}
    """
    judge_prompt = _build_judge_prompt(profile)

    messages = [
        {"role": "system", "content": judge_prompt},
        {"role": "user", "content": (
            f"JOB TITLE: {job_title}\n\n"
            f"ORIGINAL RESUME:\n{original_text}\n\n---\n\n"
            f"TAILORED RESUME:\n{tailored_text}\n\n"
            "Judge this tailored resume:"
        )},
    ]

    client = get_client()
    response = client.chat(messages, max_tokens=512, temperature=0.1)

    passed = "VERDICT: PASS" in response.upper()
    issues = "none"
    if "ISSUES:" in response.upper():
        issues_idx = response.upper().index("ISSUES:")
        issues = response[issues_idx + 7:].strip()

    return {
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "issues": issues,
        "raw": response,
    }


# ── Core Tailoring ───────────────────────────────────────────────────────

def tailor_resume(
    resume_text: str, job: dict, profile: dict,
    max_retries: int = 3, validation_mode: str = "normal",
    subtle: bool = False,
    extra_instructions: str | None = None,
) -> tuple[str, dict]:
    """Generate a tailored resume via JSON output + fresh context on each retry.

    Key design choices:
    - LLM returns structured JSON, code assembles the text (no header leaks)
    - Each retry starts a FRESH conversation (no apologetic spiral)
    - Issues from previous attempts are noted in the system prompt
    - Em dashes and smart quotes are auto-fixed, not rejected

    Args:
        resume_text:      Base resume text.
        job:              Job dict with title, site, location, full_description.
        profile:          User profile dict.
        max_retries:      Maximum retry attempts.
        validation_mode:  "strict", "normal", or "lenient".
                          strict  -- banned words trigger retries; judge must pass
                          normal  -- banned words = warnings only; judge can fail on last retry
                          lenient -- banned words ignored; LLM judge skipped

    Returns:
        (tailored_text, report) where report contains validation details.
    """
    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job['site']}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n\n"
        f"DESCRIPTION:\n{(job.get('full_description') or '')[:6000]}"
    )

    selected_projects = get_selected_projects(profile, job)
    if selected_projects:
        proj_lines = []
        for p in selected_projects:
            proj_lines.append(
                f"- {p.get('name', p.get('id', ''))}: {', '.join(p.get('stack', []))}\n"
                + "\n".join(f"  * {b}" for b in p.get("bullets", [])[:4])
            )
        job_text += "\n\nPRIORITY PORTFOLIO PROJECTS (emphasize these in PROJECTS section):\n" + "\n".join(proj_lines)

    report: dict = {
        "attempts": 0, "validator": None, "judge": None,
        "status": "pending", "validation_mode": validation_mode,
    }
    avoid_notes: list[str] = []
    tailored = ""
    client = get_client()
    if subtle or extra_instructions:
        from jobwright.scoring.tailor_instructions import (
            DEFAULT_RESUME_INSTRUCTIONS,
            build_dashboard_resume_prompt,
        )

        instructions = (extra_instructions or DEFAULT_RESUME_INSTRUCTIONS).strip()
        log.info("Using dashboard resume instructions (%d chars)", len(instructions))
        log.info("Resume instructions:\n%s", instructions[:4000])
        tailor_prompt_base = build_dashboard_resume_prompt(profile, instructions)
    else:
        tailor_prompt_base = _build_tailor_prompt(profile)

    for attempt in range(max_retries + 1):
        report["attempts"] = attempt + 1
        log.info(
            "LLM tailor attempt %d/%d for %s @ %s (subtle=%s)",
            attempt + 1,
            max_retries + 1,
            job.get("title"),
            job.get("site"),
            subtle,
        )

        # Fresh conversation every attempt
        prompt = tailor_prompt_base
        if avoid_notes:
            prompt += "\n\n## AVOID THESE ISSUES (from previous attempt):\n" + "\n".join(
                f"- {n}" for n in avoid_notes[-5:]
            )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"ORIGINAL RESUME:\n{resume_text}\n\n---\n\nTARGET JOB:\n{job_text}\n\nReturn the JSON:"},
        ]

        raw = client.chat(
            messages, max_tokens=8192, temperature=0.3, json_mode=True,
        )

        # Parse JSON from response
        try:
            data = extract_json(raw)
        except ValueError:
            avoid_notes.append("Output was not valid JSON. Return ONLY a JSON object, nothing else.")
            continue

        # Layer 1: Validate JSON fields
        validation = validate_json_fields(data, profile, mode=validation_mode)
        report["validator"] = validation

        if not validation["passed"]:
            log.info(
                "Validator failed: errors=%s warnings=%s",
                validation.get("errors"),
                validation.get("warnings"),
            )
            # Only retry if there are hard errors (warnings never block)
            avoid_notes.extend(validation["errors"])
            if attempt < max_retries:
                continue
            # Last attempt — assemble whatever we got
            tailored = assemble_resume_text(data, profile)
            report["status"] = (
                "approved_with_judge_warning"
                if validation_mode == "lenient" or subtle
                else "failed_validation"
            )
            if subtle:
                log.warning(
                    "Subtle tailor: saving last attempt despite validator errors: %s",
                    validation.get("errors"),
                )
            return tailored, report

        # Assemble text (header injected by code, em dashes auto-fixed)
        tailored = assemble_resume_text(data, profile)

        # Layer 2: LLM judge (catches subtle fabrication) — skipped in lenient mode
        if validation_mode == "lenient":
            report["judge"] = {"verdict": "SKIPPED", "passed": True, "issues": "none"}
            report["status"] = "approved"
            return tailored, report

        judge = judge_tailored_resume(resume_text, tailored, job.get("title", ""), profile)
        report["judge"] = judge
        log.info(
            "Judge verdict=%s passed=%s issues=%s",
            judge.get("verdict"),
            judge.get("passed"),
            judge.get("issues"),
        )

        if not judge["passed"]:
            avoid_notes.append(f"Judge rejected: {judge['issues']}")
            if attempt < max_retries:
                # In normal mode, only retry on judge failure if there are retries left
                if validation_mode != "lenient":
                    continue
            # Accept best attempt on last retry (all modes) or if lenient
            report["status"] = "approved_with_judge_warning"
            return tailored, report

        # Both passed
        report["status"] = "approved"
        log.info("Tailor approved for %s", job.get("title"))
        return tailored, report

    report["status"] = "exhausted_retries"
    return tailored, report


def _job_file_prefix(job: dict) -> str:
    safe_title = re.sub(r"[^\w\s-]", "", job.get("title") or "untitled")[:50].strip().replace(" ", "_")
    safe_site = re.sub(r"[^\w\s-]", "", job.get("site") or "manual")[:20].strip().replace(" ", "_")
    return f"{safe_site}_{safe_title}"


def _persist_tailor_result(
    conn, job: dict, tailored: str, report: dict,
) -> dict:
    """Save tailored markdown + sidecar files and update DB (single job)."""
    from jobwright.database import maybe_agent_advance_to_prepare

    prefix = _job_file_prefix(job)
    md_path = config.TAILORED_DIR / f"{prefix}.md"
    md_path.write_text(tailored, encoding="utf-8")
    log.info("Wrote tailored resume %s (status=%s)", md_path, report["status"])

    job_path = config.TAILORED_DIR / f"{prefix}_JOB.txt"
    job_desc = (
        f"Title: {job['title']}\n"
        f"Company: {job['site']}\n"
        f"Location: {job.get('location', 'N/A')}\n"
        f"Score: {job.get('fit_score', 'N/A')}\n"
        f"URL: {job['url']}\n\n"
        f"{job.get('full_description', '')}"
    )
    job_path.write_text(job_desc, encoding="utf-8")

    report_path = config.TAILORED_DIR / f"{prefix}_REPORT.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    pdf_path = None
    if report["status"] in _SUCCESS_STATUSES:
        try:
            from jobwright.scoring.pdf import convert_to_pdf
            pdf_path = str(convert_to_pdf(md_path))
        except Exception:
            log.debug("PDF generation failed for %s", md_path, exc_info=True)

    now = datetime.now(UTC).isoformat()
    conn.execute(
        "UPDATE jobs SET tailored_resume_path=?, tailored_at=?, "
        "tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
        (str(md_path), now, job["url"]),
    )
    maybe_agent_advance_to_prepare(job["url"], conn=conn)
    conn.commit()

    return {
        "url": job["url"],
        "path": str(md_path),
        "pdf_path": pdf_path,
        "title": job["title"],
        "site": job["site"],
        "status": report["status"],
        "attempts": report["attempts"],
    }


def tailor_one_job(
    url: str,
    *,
    subtle: bool = False,
    validation_mode: str = "normal",
    extra_instructions: str | None = None,
    conn=None,
) -> dict:
    """Tailor resume for a single job URL (dashboard action; no min_score gate)."""
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

    log.info(
        "Loading base resume and profile for %s (%s)",
        job.get("title"),
        url,
    )
    profile = load_profile()
    resume_text = load_resume_text()
    log.info("Base resume loaded (%d chars). Starting LLM tailor.", len(resume_text))
    config.TAILORED_DIR.mkdir(parents=True, exist_ok=True)

    tailored, report = tailor_resume(
        resume_text, job, profile,
        validation_mode=validation_mode, subtle=subtle,
        extra_instructions=extra_instructions,
    )
    status = report["status"]
    if status not in _SUCCESS_STATUSES:
        # Dashboard subtle pass: still save the last LLM attempt so the user
        # gets materials instead of a hard fail after validator retries.
        if subtle and (tailored or "").strip():
            log.warning(
                "Subtle tailor status=%s; persisting last attempt anyway",
                status,
            )
            report["status"] = "approved_with_judge_warning"
            return _persist_tailor_result(conn, job, tailored, report)
        conn.execute(
            "UPDATE jobs SET tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
            (url,),
        )
        conn.commit()
        return {
            "url": url,
            "path": None,
            "pdf_path": None,
            "title": job.get("title"),
            "site": job.get("site"),
            "status": status,
            "attempts": report["attempts"],
        }

    return _persist_tailor_result(conn, job, tailored, report)


def _resume_text_for_cover(job: dict) -> str:
    """Prefer tailored resume text for cover; fall back to base resume."""
    from jobwright.resume import load_resume_text

    tailored_path = resolve_material_path(job.get("tailored_resume_path"))
    if tailored_path and tailored_path.is_file():
        return tailored_path.read_text(encoding="utf-8")
    return load_resume_text()


def _export_job_docx(url: str) -> None:
    conn = get_connection()
    job_row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if not job_row:
        log.warning("Job row missing; skipping DOCX")
        return
    from jobwright.scoring.docx_export import convert_job_materials

    docx_result = convert_job_materials(dict(job_row))
    log.info(
        "DOCX resume=%s cover=%s",
        docx_result.get("resume_docx"),
        docx_result.get("cover_docx"),
    )


def run_single_job_resume(
    url: str,
    validation_mode: str = "lenient",
    resume_instructions: str | None = None,
) -> int:
    """Tailor resume and export DOCX for one job. Returns process RC."""
    try:
        from jobwright.scoring.tailor_instructions import DEFAULT_RESUME_INSTRUCTIONS

        resume_instructions = (resume_instructions or DEFAULT_RESUME_INSTRUCTIONS).strip()
        log.info("STAGE: tailor")
        log.info("Per-job resume tailor starting for %s", url)
        tailor_result = tailor_one_job(
            url,
            subtle=True,
            validation_mode=validation_mode,
            extra_instructions=resume_instructions,
        )
        status = tailor_result.get("status")
        path = tailor_result.get("path")
        if status not in _SUCCESS_STATUSES or not path:
            log.error("Resume tailoring failed: status=%s", status)
            log.info("done RC=1")
            return 1
        log.info("Stage 'tailor' completed")

        log.info("STAGE: docx")
        _export_job_docx(url)
        log.info("Stage 'docx' completed")
        log.info("done RC=0")
        return 0
    except Exception:
        log.exception("Per-job resume tailor crashed")
        log.info("done RC=1")
        return 1


def run_single_job_cover(
    url: str,
    validation_mode: str = "lenient",
    cover_instructions: str | None = None,
) -> int:
    """Generate cover letter and export DOCX for one job. Returns process RC."""
    from jobwright.scoring.cover_letter import cover_one_job

    try:
        from jobwright.scoring.tailor_instructions import DEFAULT_COVER_INSTRUCTIONS

        cover_instructions = (cover_instructions or DEFAULT_COVER_INSTRUCTIONS).strip()
        conn = get_connection()
        row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
        if row is None:
            log.error("Job not found: %s", url)
            log.info("done RC=1")
            return 1
        job = dict(row)
        resume_text = _resume_text_for_cover(job)

        log.info("STAGE: cover")
        log.info("Per-job cover letter starting for %s", url)
        cover_result = cover_one_job(
            url,
            resume_text=resume_text,
            validation_mode=validation_mode,
            extra_instructions=cover_instructions,
        )
        if not cover_result.get("path"):
            log.error("Cover letter failed: %s", cover_result.get("error") or "unknown")
            log.info("done RC=1")
            return 1
        log.info("Wrote cover letter %s", cover_result["path"])
        log.info("Stage 'cover' completed")

        log.info("STAGE: docx")
        _export_job_docx(url)
        log.info("Stage 'docx' completed")
        log.info("done RC=0")
        return 0
    except Exception:
        log.exception("Per-job cover tailor crashed")
        log.info("done RC=1")
        return 1


def run_single_job_materials(
    url: str,
    validation_mode: str = "lenient",
    resume_instructions: str | None = None,
    cover_instructions: str | None = None,
) -> int:
    """Tailor resume, cover letter, and DOCX for one job. Returns process RC."""
    from pathlib import Path

    from jobwright.scoring.cover_letter import cover_one_job

    try:
        from jobwright.scoring.tailor_instructions import (
            DEFAULT_COVER_INSTRUCTIONS,
            DEFAULT_RESUME_INSTRUCTIONS,
        )

        resume_instructions = (resume_instructions or DEFAULT_RESUME_INSTRUCTIONS).strip()
        cover_instructions = (cover_instructions or DEFAULT_COVER_INSTRUCTIONS).strip()
        log.info("STAGE: tailor")
        log.info("Per-job tailor starting for %s", url)
        tailor_result = tailor_one_job(
            url,
            subtle=True,
            validation_mode=validation_mode,
            extra_instructions=resume_instructions,
        )
        status = tailor_result.get("status")
        path = tailor_result.get("path")
        if status not in _SUCCESS_STATUSES or not path:
            log.error("Resume tailoring failed: status=%s", status)
            log.info("done RC=1")
            return 1
        log.info("Stage 'tailor' completed")

        log.info("STAGE: cover")
        tailored_text = Path(path).read_text(encoding="utf-8")
        cover_result = cover_one_job(
            url,
            resume_text=tailored_text,
            extra_instructions=cover_instructions,
        )
        if not cover_result.get("path"):
            log.error("Cover letter failed: %s", cover_result.get("error") or "unknown")
            log.info("done RC=1")
            return 1
        log.info("Wrote cover letter %s", cover_result["path"])
        log.info("Stage 'cover' completed")

        log.info("STAGE: docx")
        _export_job_docx(url)
        log.info("Stage 'docx' completed")
        log.info("done RC=0")
        return 0
    except Exception:
        log.exception("Per-job tailor crashed")
        log.info("done RC=1")
        return 1


# ── Batch Entry Point ────────────────────────────────────────────────────

def run_tailoring(min_score: int = 7, limit: int = 20,
                  validation_mode: str = "normal") -> dict:
    """Generate tailored resumes for high-scoring jobs.

    Args:
        min_score:       Minimum fit_score to tailor for.
        limit:           Maximum jobs to process.
        validation_mode: "strict", "normal", or "lenient".

    Returns:
        {"approved": int, "failed": int, "errors": int, "elapsed": float}
    """
    profile = load_profile()
    from jobwright.resume import load_resume_text

    resume_text = load_resume_text()
    conn = get_connection()

    jobs = get_jobs_by_stage(conn=conn, stage="pending_tailor", min_score=min_score, limit=limit)

    if not jobs:
        log.info("No untailored jobs with score >= %d.", min_score)
        return {"approved": 0, "failed": 0, "errors": 0, "elapsed": 0.0}

    config.TAILORED_DIR.mkdir(parents=True, exist_ok=True)
    log.info("Tailoring resumes for %d jobs (score >= %d)...", len(jobs), min_score)
    t0 = time.time()
    completed = 0
    results: list[dict] = []
    stats: dict[str, int] = {"approved": 0, "failed_validation": 0, "failed_judge": 0, "error": 0}

    for job in jobs:
        completed += 1
        try:
            tailored, report = tailor_resume(resume_text, job, profile,
                                             validation_mode=validation_mode)

            status = report["status"]
            if status not in _SUCCESS_STATUSES:
                conn.execute(
                    "UPDATE jobs SET tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
                    (job["url"],),
                )
                conn.commit()
                result = {
                    "url": job["url"], "title": job["title"], "site": job["site"],
                    "status": status, "attempts": report["attempts"],
                    "path": None, "pdf_path": None,
                }
                results.append(result)
                stats[status] = stats.get(status, 0) + 1
                log.info(
                    "%d/%d [%s] attempts=%s | %s",
                    completed, len(jobs), status.upper(),
                    report["attempts"], job["title"][:40],
                )
                continue

            result = _persist_tailor_result(conn, job, tailored, report)
        except Exception as e:
            conn.execute(
                "UPDATE jobs SET tailor_attempts=COALESCE(tailor_attempts,0)+1 WHERE url=?",
                (job["url"],),
            )
            conn.commit()
            result = {
                "url": job["url"], "title": job["title"], "site": job["site"],
                "status": "error", "attempts": 0, "path": None, "pdf_path": None,
            }
            log.error("%d/%d [ERROR] %s -- %s", completed, len(jobs), job["title"][:40], e)

        results.append(result)
        stats[result.get("status", "error")] = stats.get(result.get("status", "error"), 0) + 1

        elapsed = time.time() - t0
        rate = completed / elapsed if elapsed > 0 else 0
        log.info(
            "%d/%d [%s] attempts=%s | %.1f jobs/min | %s",
            completed, len(jobs),
            result["status"].upper(),
            result.get("attempts", "?"),
            rate * 60,
            result["title"][:40],
        )

    elapsed = time.time() - t0
    log.info(
        "Tailoring done in %.1fs: %d approved, %d failed_validation, %d failed_judge, %d errors",
        elapsed,
        stats.get("approved", 0),
        stats.get("failed_validation", 0),
        stats.get("failed_judge", 0),
        stats.get("error", 0),
    )

    return {
        "approved": stats.get("approved", 0),
        "failed": stats.get("failed_validation", 0) + stats.get("failed_judge", 0),
        "errors": stats.get("error", 0),
        "elapsed": elapsed,
    }
