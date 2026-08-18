"""Apply orchestration: acquire jobs, spawn agent sessions, track results.

This is the main entry point for the apply pipeline. It pulls jobs from
the database, launches Chrome + Cursor/Claude agent for each one, parses the
result, and updates the database. Supports parallel workers via --workers.
"""

import atexit
import json
import logging
import os
import platform
import re
import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rich.console import Console
from rich.live import Live

from jobwright import config
from jobwright.database import get_connection
from jobwright.apply.providers import WorkerContext, get_provider
from jobwright.apply import prompt as prompt_mod
from jobwright.apply.chrome import (
    launch_chrome, cleanup_worker, kill_all_chrome,
    reset_worker_dir, cleanup_on_exit, BASE_CDP_PORT,
)
from jobwright.apply.dashboard import (
    init_worker, update_state, add_event, get_state,
    render_full, get_totals,
)

logger = logging.getLogger(__name__)

# Blocked sites loaded from config/sites.yaml
def _load_manifest_urls() -> list[str] | None:
    """Load optional URL allowlist from JOBWRIGHT_APPLY_MANIFEST env path."""
    manifest_path = os.environ.get("JOBWRIGHT_APPLY_MANIFEST")
    if not manifest_path:
        return None
    path = Path(manifest_path)
    if not path.exists():
        return None
    urls = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return urls if urls else None


_STALE_LOCK_MINUTES = 60


def _build_ats_context(job: dict) -> str:
    """Fetch ATS-specific schema hints (Greenhouse boards-api) for the apply prompt."""
    apply_url = job.get("application_url") or job.get("url") or ""
    secondary_url = job.get("url") or ""

    from jobwright.apply.ats import (
        detect_ats,
        fetch_greenhouse_schema,
        parse_greenhouse_url,
        summarize_schema_for_prompt,
        validate_schema_against_profile,
    )

    ats = detect_ats(apply_url) or detect_ats(secondary_url)
    if ats != "greenhouse":
        if ats:
            return f"== ATS DETECTED: {ats} (use browser; no schema API wired yet) =="
        return ""

    parsed = parse_greenhouse_url(apply_url) or parse_greenhouse_url(secondary_url)
    if not parsed:
        return "== ATS: greenhouse (could not parse board/job id from URL) =="

    board_token, job_id = parsed
    try:
        schema = fetch_greenhouse_schema(board_token, job_id)
        profile = config.load_profile()
        for warning in validate_schema_against_profile(schema, profile):
            logger.warning("Schema validation: %s", warning)
        return summarize_schema_for_prompt(schema)
    except Exception as e:
        logger.warning("Greenhouse schema fetch failed: %s", e)
        return "== ATS: greenhouse (schema fetch failed - discover form in browser) =="


def _load_blocked():
    from jobwright.config import load_blocked_sites
    return load_blocked_sites()


def _load_apply_blocked():
    from jobwright.config import load_apply_blocked
    return load_apply_blocked()


def _ready_jobs_query(
    min_score: int,
    max_attempts: int,
    *,
    include_apply_blocked: bool = False,
) -> tuple[str, list]:
    """SQL WHERE clause + params for ready jobs.

    Discovery-blocked sites/patterns are always excluded. When
    include_apply_blocked=True (apply acquire queue), also exclude
    apply_blocked (LinkedIn). Digest/connect use include_apply_blocked=False
    so LinkedIn materials surface in the brief.
    """
    from jobwright.database import ANTI_CLOBBER_SQL, MANUAL_SOURCE_EXCLUSION_SQL

    blocked_sites, blocked_patterns = _load_blocked()
    if include_apply_blocked:
        apply_sites, apply_patterns = _load_apply_blocked()
        blocked_sites = set(blocked_sites) | set(apply_sites)
        blocked_patterns = list(blocked_patterns) + list(apply_patterns)

    params: list = [max_attempts, min_score]
    site_clause = ""
    if blocked_sites:
        placeholders = ",".join("?" * len(blocked_sites))
        site_clause = f"AND site NOT IN ({placeholders})"
        params.extend(sorted(blocked_sites))
    url_clauses = ""
    if blocked_patterns:
        url_clauses = " ".join("AND url NOT LIKE ?" for _ in blocked_patterns)
        params.extend(blocked_patterns)
    where = (
        "tailored_resume_path IS NOT NULL"
        " AND applied_at IS NULL"
        " AND (apply_status IS NULL OR apply_status = 'failed')"
        " AND (apply_attempts IS NULL OR apply_attempts < ?)"
        " AND fit_score >= ?"
        f" {site_clause} {url_clauses}"
        f"{ANTI_CLOBBER_SQL}{MANUAL_SOURCE_EXCLUSION_SQL}"
    )
    return where, params


def list_ready_jobs(
    min_score: int = 7,
    limit: int = 5,
    max_attempts: int | None = None,
) -> list[dict]:
    """Jobs ready for digest/connect/materials (discovery-blocked excluded).

    LinkedIn (apply_blocked) is included so the brief can show tailored DOCX
    and warm intros; live apply uses a stricter query.
    """
    from jobwright.config import is_manual_ats

    max_attempts = max_attempts or config.DEFAULTS["max_apply_attempts"]
    where, params = _ready_jobs_query(
        min_score, max_attempts, include_apply_blocked=False
    )
    conn = get_connection()
    rows = conn.execute(
        f"""
        SELECT url, title, site, company, application_url, tailored_resume_path,
               tailored_resume_docx_path, fit_score, location, full_description,
               cover_letter_path, cover_letter_docx_path, score_reasoning
        FROM jobs
        WHERE {where}
        ORDER BY fit_score DESC, url
        LIMIT ?
        """,
        params + [max(limit * 3, limit)],
    ).fetchall()

    ready: list[dict] = []
    for row in rows:
        job = dict(row)
        apply_url = job.get("application_url") or job.get("url")
        if is_manual_ats(apply_url):
            continue
        ready.append(job)
        if len(ready) >= limit:
            break
    return ready


# Unicode dashes / hyphens that render poorly in WhatsApp -> ASCII hyphen.
_DASH_CHARS = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"  # ‐ ‑ ‒ – — ― −
_DASH_RE = re.compile(f"[{_DASH_CHARS}]")
_MARKDOWN_RE = re.compile(r"[*_`#]+")
_WS_RE = re.compile(r"\s+")


def _clean_text(text: str | None) -> str:
    """Normalize LLM/scraped text for plain WhatsApp: ASCII dashes, no markdown."""
    if not text:
        return ""
    text = text.replace("\u2026", "...")  # ellipsis glyph -> ASCII
    text = _DASH_RE.sub("-", text)
    text = _MARKDOWN_RE.sub("", text)
    text = _WS_RE.sub(" ", text)
    return text.strip()


_PERSON_TOKEN_RE = re.compile(r"^[A-Z][A-Za-z.'-]*$")
# Words that signal a job-posting title rather than a person's name.
_TITLE_WORDS = {
    "chief", "executive", "director", "manager", "officer", "president",
    "vp", "ceo", "cto", "cfo", "coo", "head", "lead", "senior", "junior",
    "staff", "jobs", "job", "careers", "career", "hiring", "hire", "team",
    "post", "associate", "assistant", "coordinator", "analyst", "specialist",
    "intern", "recruiter", "recruiting", "operations", "growth", "strategy",
    "engineer", "engineering", "developer", "leadership",
}


def _looks_like_person_name(name: str) -> bool:
    """True only for plausible 'First Last' names, not job-posting titles.

    Web research occasionally stores a page title (job repost) as the contact
    name. Real names are 2-4 capitalized tokens with no lowercase connectors
    (of/at/to/by), symbols (|, &), or digits, and no job-title words.
    """
    tokens = name.split()
    if not (2 <= len(tokens) <= 4):
        return False
    if not all(_PERSON_TOKEN_RE.match(t) for t in tokens):
        return False
    return not any(t.lower() in _TITLE_WORDS for t in tokens)


def _truncate(text: str, limit: int) -> str:
    """Truncate on a word boundary with an ASCII ellipsis."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:-") or text[:limit]
    return cut + "..."


def _docx_path(txt_path: str | None, stored: str | None) -> str | None:
    if stored and Path(stored).exists():
        return stored
    if txt_path:
        sibling = Path(txt_path).with_suffix(".docx")
        if sibling.exists():
            return str(sibling)
    return None


def gather_brief_health(pipeline_rc: int | None = None) -> dict:
    """Snapshot DB counts for digest footers and ops visibility."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    scored = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"
    ).fetchone()[0]
    ready = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"
    ).fetchone()[0]
    pending_score = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL AND fit_score IS NULL"
    ).fetchone()[0]
    return {
        "total_jobs": total,
        "scored": scored,
        "ready_materials": ready,
        "pending_score": pending_score,
        "pipeline_rc": pipeline_rc,
    }


def _digest_footer_lines(
    job_count: int,
    limit: int,
    apply_enabled: bool,
    health: dict | None,
) -> list[str]:
    """User-facing hints and optional pipeline health footer."""
    lines: list[str] = []
    if job_count == 0:
        lines.extend([
            "No matching roles above your score threshold today.",
            "We will search again on the next scheduled run.",
            'Reply "find jobs now" to refresh manually.',
        ])
    elif job_count == 1:
        lines.append(
            "Your editable resume + cover letter are attached below."
        )
        lines.append('(Reply "materials 1" if you need them resent.)')
    else:
        lines.append(
            "Editable resume + cover letter for each job are attached below."
        )
        lines.append('(Reply "materials N", e.g. "materials 2", to resend any job.)')
    if job_count > 0:
        if apply_enabled:
            lines.append(f'Reply *CONFIRM APPLY* to submit up to {limit} jobs (live).')
        else:
            lines.append(
                "Find-only mode: applying is off for this profile. Reply if you want apply enabled."
            )

    if health:
        rc = health.get("pipeline_rc")
        rc_note = ""
        if rc is not None and rc != 0:
            rc_note = f" (pipeline exit {rc}; partial results below)"
        lines.append("")
        lines.append(
            f"Run stats{rc_note}: {health.get('total_jobs', 0)} in DB, "
            f"{health.get('scored', 0)} scored, "
            f"{health.get('ready_materials', 0)} with tailored resume, "
            f"{health.get('pending_score', 0)} still pending score."
        )
    return lines


def write_morning_digest_and_manifest(
    digest_path: Path,
    manifest_path: Path,
    min_score: int = 5,
    limit: int = 5,
    max_attempts: int | None = None,
    apply_enabled: bool = True,
    user_label: str | None = None,
    pipeline_rc: int | None = None,
    health: dict | None = None,
) -> int:
    """Write digest text, URL manifest, and MATERIALS_MANIFEST JSON.

    If apply_enabled is False, omit the CONFIRM APPLY line (find-only mode).
    """
    from jobwright.network.per_job import load_job_contacts

    jobs = list_ready_jobs(min_score=min_score, limit=limit, max_attempts=max_attempts)
    manifest_path.write_text(
        "\n".join(job["url"] for job in jobs) + ("\n" if jobs else ""),
        encoding="utf-8",
    )

    contacts_blob = load_job_contacts()
    contacts_by_url = (contacts_blob.get("jobs") or {}) if contacts_blob else {}

    materials: list[dict] = []
    who = f" ({user_label})" if user_label else ""
    lines = [
        f"=== Daily Brief{who} ===",
        f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M %Z')}",
        "",
        "Matched jobs (reply materials N for editable DOCX):",
        "",
    ]
    for idx, job in enumerate(jobs, start=1):
        company = _clean_text(job.get("company") or job.get("site") or "")
        title = _clean_text(job.get("title") or "")
        desc = _clean_text(job.get("full_description") or title)
        desc = _truncate(desc, 90)
        lines.append(f"{idx}. *{title}* @ {company} (score {job.get('fit_score', '')})")
        if desc:
            lines.append(f"   {desc}")
        lines.append(f"   {job['url']}")

        resume_docx = _docx_path(job.get("tailored_resume_path"), job.get("tailored_resume_docx_path"))
        cover_docx = _docx_path(job.get("cover_letter_path"), job.get("cover_letter_docx_path"))
        if resume_docx or cover_docx:
            lines.append("   Materials: DOCX ready (reply materials %d)" % idx)

        entry = contacts_by_url.get(job["url"]) or {}
        csv_c = entry.get("csv_contacts") or []
        web_c = entry.get("web_contacts") or []
        contact_lines: list[str] = []
        for c in csv_c[:3]:
            name = _clean_text(
                f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
                or c.get("name", "")
            )
            if not name:
                continue
            position = _clean_text(c.get("position") or "")
            why = _clean_text(c.get("why") or "")
            head = f"{name} ({position})" if position else name
            contact_lines.append(f"     - {head}: {why}" if why else f"     - {head}")
        for c in web_c[:2]:
            name = _clean_text(c.get("name") or "")
            url = (c.get("source_url") or "").strip()
            if not name or not url or not _looks_like_person_name(name):
                continue
            role = _clean_text(c.get("role") or "")
            head = f"{name} ({role})" if role else name
            contact_lines.append(f"     - {head}: {url}")
        if contact_lines:
            lines.append("   Connections:")
            lines.extend(contact_lines)
        lines.append("")

        materials.append({
            "index": idx,
            "url": job["url"],
            "title": job.get("title"),
            "company": company,
            "fit_score": job.get("fit_score"),
            "resume_docx": resume_docx,
            "cover_docx": cover_docx,
            "resume_txt": job.get("tailored_resume_path"),
            "cover_txt": job.get("cover_letter_path"),
            "csv_contacts": csv_c,
            "web_contacts": web_c,
        })

    lines.append("")
    lines.extend(_digest_footer_lines(len(jobs), limit, apply_enabled, health))
    digest_path.write_text("\n".join(lines), encoding="utf-8")

    materials_path = digest_path.parent / f"MATERIALS_MANIFEST_{datetime.now().strftime('%Y%m%d')}.json"
    materials_path.write_text(
        json.dumps({"generated_at": datetime.now().isoformat(), "jobs": materials}, indent=2),
        encoding="utf-8",
    )
    # Latest pointer
    (digest_path.parent / "MATERIALS_MANIFEST_latest.json").write_text(
        materials_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return len(jobs)

# How often to poll the DB when the queue is empty (seconds)
POLL_INTERVAL = config.DEFAULTS["poll_interval"]

# Thread-safe shutdown coordination
_stop_event = threading.Event()

# Track active agent processes for skip (Ctrl+C) handling
_agent_provider = None
_agent_lock = threading.Lock()

# Register cleanup on exit
atexit.register(cleanup_on_exit)
if platform.system() != "Windows":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))


# ---------------------------------------------------------------------------
# MCP config
# ---------------------------------------------------------------------------

def _make_mcp_config(cdp_port: int) -> dict:
    """Build MCP config dict for a specific CDP port."""
    return {
        "mcpServers": {
            "playwright": {
                "command": "npx",
                "args": [
                    "@playwright/mcp@latest",
                    f"--cdp-endpoint=http://localhost:{cdp_port}",
                    f"--viewport-size={config.DEFAULTS['viewport']}",
                ],
            },
            "gmail": {
                "command": "npx",
                "args": ["-y", "@gongrzhe/server-gmail-autoauth-mcp"],
            },
        }
    }


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def acquire_job(target_url: str | None = None, min_score: int = 7,
                worker_id: int = 0) -> dict | None:
    """Atomically acquire the next job to apply to.

    Args:
        target_url: Apply to a specific URL instead of picking from queue.
        min_score: Minimum fit_score threshold.
        worker_id: Worker claiming this job (for tracking).

    Returns:
        Job dict or None if the queue is empty.
    """
    conn = get_connection()
    try:
        conn.execute("BEGIN IMMEDIATE")

        stale_cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=_STALE_LOCK_MINUTES)
        ).isoformat()
        conn.execute("""
            UPDATE jobs SET apply_status = NULL, agent_id = NULL,
                           apply_error = 'stale_lock_reclaimed'
            WHERE apply_status = 'in_progress'
              AND (last_attempted_at IS NULL OR last_attempted_at < ?)
        """, (stale_cutoff,))

        if target_url:
            like = f"%{target_url.split('?')[0].rstrip('/')}%"
            row = conn.execute("""
                SELECT url, title, site, application_url, tailored_resume_path,
                       fit_score, location, full_description, cover_letter_path
                FROM jobs
                WHERE (url = ? OR application_url = ? OR application_url LIKE ? OR url LIKE ?)
                  AND tailored_resume_path IS NOT NULL
                  AND applied_at IS NULL
                  AND (apply_status IS NULL OR apply_status NOT IN ('in_progress', 'applied'))
                LIMIT 1
            """, (target_url, target_url, like, like)).fetchone()
            if row:
                from jobwright.config import (
                    is_apply_blocked_job,
                    is_discovery_blocked_job,
                )
                if is_discovery_blocked_job(row["site"], row["url"]) or is_apply_blocked_job(
                    row["site"], row["url"]
                ):
                    conn.rollback()
                    logger.warning(
                        "Refusing apply for blocked site/url: site=%s url=%s",
                        row["site"],
                        (row["url"] or "")[:80],
                    )
                    return None
        else:
            manifest_env = os.environ.get("JOBWRIGHT_APPLY_MANIFEST")
            manifest_urls = _load_manifest_urls() if manifest_env else None
            if manifest_env and not manifest_urls:
                conn.rollback()
                logger.warning("Manifest required but empty or missing: %s", manifest_env)
                return None

            where, params = _ready_jobs_query(
                min_score,
                config.DEFAULTS["max_apply_attempts"],
                include_apply_blocked=True,
            )
            manifest_clause = ""
            if manifest_urls:
                placeholders = ",".join("?" * len(manifest_urls))
                manifest_clause = (
                    f" AND (url IN ({placeholders}) OR application_url IN ({placeholders}))"
                )
                params = list(params)
                params.extend(manifest_urls)
                params.extend(manifest_urls)
            row = conn.execute(f"""
                SELECT url, title, site, application_url, tailored_resume_path,
                       fit_score, location, full_description, cover_letter_path
                FROM jobs
                WHERE {where}
                  {manifest_clause}
                ORDER BY fit_score DESC, url
                LIMIT 1
            """, params).fetchone()

        if not row:
            conn.rollback()
            return None

        # Skip manual ATS sites (unsolvable CAPTCHAs)
        from jobwright.config import is_manual_ats
        apply_url = row["application_url"] or row["url"]
        if is_manual_ats(apply_url):
            conn.execute(
                "UPDATE jobs SET apply_status = 'manual', apply_error = 'manual ATS' WHERE url = ?",
                (row["url"],),
            )
            conn.commit()
            logger.info("Skipping manual ATS: %s", row["url"][:80])
            return None

        now = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            UPDATE jobs SET apply_status = 'in_progress',
                           agent_id = ?,
                           last_attempted_at = ?
            WHERE url = ?
        """, (f"worker-{worker_id}", now, row["url"]))
        conn.commit()

        return dict(row)
    except Exception:
        conn.rollback()
        raise


def mark_result(url: str, status: str, error: str | None = None,
                permanent: bool = False, duration_ms: int | None = None,
                task_id: str | None = None) -> None:
    """Update a job's apply status in the database."""
    from jobwright.database import advance_funnel

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    if status == "applied":
        conn.execute("""
            UPDATE jobs SET apply_status = 'applied', applied_at = ?,
                           apply_error = NULL, agent_id = NULL,
                           apply_duration_ms = ?, apply_task_id = ?
            WHERE url = ?
        """, (now, duration_ms, task_id, url))
        # Agent apply may set Applied only when explicitly triggered; actor=agent
        # is allowed for the applied lane via human-initiated apply console.
        # Use system actor so we don't hit the agent handoff cap.
        advance_funnel(url, "applied", "system", note="agent apply", conn=conn)
    else:
        attempts = 99 if permanent else "COALESCE(apply_attempts, 0) + 1"
        conn.execute(f"""
            UPDATE jobs SET apply_status = ?, apply_error = ?,
                           apply_attempts = {attempts}, agent_id = NULL,
                           apply_duration_ms = ?, apply_task_id = ?
            WHERE url = ?
        """, (status, error or "unknown", duration_ms, task_id, url))
    conn.commit()


def release_lock(url: str) -> None:
    """Release the in_progress lock without changing status."""
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET apply_status = NULL, agent_id = NULL WHERE url = ? AND apply_status = 'in_progress'",
        (url,),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Utility modes (--gen, --mark-applied, --mark-failed, --reset-failed)
# ---------------------------------------------------------------------------

def gen_prompt(target_url: str, min_score: int = 7,
               model: str = "sonnet", worker_id: int = 0) -> Path | None:
    """Generate a prompt file and print the Claude CLI command for manual debugging.

    Returns:
        Path to the generated prompt file, or None if no job found.
    """
    job = acquire_job(target_url=target_url, min_score=min_score, worker_id=worker_id)
    if not job:
        return None

    # Read resume text
    resume_path = job.get("tailored_resume_path")
    txt_path = Path(resume_path).with_suffix(".txt") if resume_path else None
    resume_text = ""
    if txt_path and txt_path.exists():
        resume_text = txt_path.read_text(encoding="utf-8")

    prompt = prompt_mod.build_prompt(
        job=job,
        tailored_resume=resume_text,
        worker_id=worker_id,
        ats_context=_build_ats_context(job),
    )

    # Release the lock so the job stays available
    release_lock(job["url"])

    # Write prompt file
    config.ensure_dirs()
    site_slug = ((job.get("site") or "unknown"))[:20].replace(" ", "_")
    prompt_file = config.LOG_DIR / f"prompt_{site_slug}_{job['title'][:30].replace(' ', '_')}.txt"
    prompt_file.write_text(prompt, encoding="utf-8")

    # Write MCP config for reference
    port = BASE_CDP_PORT + worker_id
    mcp_path = config.APP_DIR / f".mcp-apply-{worker_id}.json"
    mcp_path.write_text(json.dumps(_make_mcp_config(port)), encoding="utf-8")

    return prompt_file


def mark_job(url: str, status: str, reason: str | None = None) -> None:
    """Manually mark a job's apply status in the database.

    Args:
        url: Job URL to mark.
        status: Either 'applied' or 'failed'.
        reason: Failure reason (only for status='failed').
    """
    from jobwright.database import advance_funnel

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    if status == "applied":
        conn.execute("""
            UPDATE jobs SET apply_status = 'applied', applied_at = ?,
                           apply_error = NULL, agent_id = NULL
            WHERE url = ?
        """, (now, url))
        advance_funnel(
            url, "applied", "human", note="mark-applied",
            applied_manually=True, conn=conn,
        )
    else:
        conn.execute("""
            UPDATE jobs SET apply_status = 'failed', apply_error = ?,
                           apply_attempts = 99, agent_id = NULL
            WHERE url = ?
        """, (reason or "manual", url))
    conn.commit()


def reset_failed() -> int:
    """Reset all failed jobs so they can be retried.

    Returns:
        Number of jobs reset.
    """
    conn = get_connection()
    cursor = conn.execute("""
        UPDATE jobs SET apply_status = NULL, apply_error = NULL,
                       apply_attempts = 0, agent_id = NULL
        WHERE apply_status = 'failed'
          OR (apply_status IS NOT NULL AND apply_status != 'applied'
              AND apply_status != 'in_progress')
    """)
    conn.commit()
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Per-job execution
# ---------------------------------------------------------------------------

def _get_agent_provider():
    global _agent_provider
    if _agent_provider is None:
        _agent_provider = get_provider()
    return _agent_provider


def run_job(job: dict, port: int, worker_id: int = 0,
            model: str = "composer-2.5", dry_run: bool = False) -> tuple[str, int]:
    """Run one apply agent session via configured AgentProvider.

    Returns:
        Tuple of (status_string, duration_ms).
    """
    resume_path = job.get("tailored_resume_path")
    txt_path = Path(resume_path).with_suffix(".txt") if resume_path else None
    resume_text = ""
    if txt_path and txt_path.exists():
        resume_text = txt_path.read_text(encoding="utf-8")

    mcp_config = _make_mcp_config(port)
    worker_dir = reset_worker_dir(worker_id)

    ats_context = _build_ats_context(job)
    try:
        agent_prompt = prompt_mod.build_prompt(
            job=job,
            tailored_resume=resume_text,
            dry_run=dry_run,
            worker_id=worker_id,
            ats_context=ats_context,
        )
    except ValueError as exc:
        logger.error("Prompt build failed: %s", exc)
        return f"failed:{str(exc).replace(' ', '_')[:80]}", 0

    update_state(worker_id, status="applying", job_title=job["title"],
                 company=job.get("site", ""), score=job.get("fit_score", 0),
                 start_time=time.time(), actions=0, last_action="starting")
    add_event(f"[W{worker_id}] Starting: {job['title'][:40]} @ {job.get('site', '')}")

    worker_log = config.LOG_DIR / f"worker-{worker_id}.log"
    ts_header = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_header = (
        f"\n{'=' * 60}\n"
        f"[{ts_header}] {job['title']} @ {job.get('site', '')}\n"
        f"URL: {job.get('application_url') or job['url']}\n"
        f"Score: {job.get('fit_score', 'N/A')}/10\n"
        f"Provider: {config.get_agent_provider()}\n"
        f"{'=' * 60}\n"
    )

    ctx = WorkerContext(
        worker_id=worker_id,
        cdp_port=port,
        workdir=worker_dir,
        dry_run=dry_run,
        model=model,
        timeout_s=config.DEFAULTS["apply_timeout"],
    )

    provider = _get_agent_provider()
    try:
        with open(worker_log, "a", encoding="utf-8") as lf:
            lf.write(log_header)

        result = provider.run_apply(agent_prompt, ctx, mcp_config)
        output = result.raw_output

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_log = config.LOG_DIR / f"agent_{ts}_w{worker_id}_{job.get('site', 'unknown')[:20]}.txt"
        config.write_private_text(job_log, output)

        if result.stats.get("cost_usd"):
            ws = get_state(worker_id)
            prev_cost = ws.total_cost if ws else 0.0
            update_state(worker_id, total_cost=prev_cost + float(result.stats["cost_usd"]))

        status = result.outcome
        elapsed = result.duration_ms // 1000
        add_event(f"[W{worker_id}] {status.upper()} ({elapsed}s): {job['title'][:30]}")
        update_state(worker_id, status=status.split(":")[0],
                     last_action=f"{status} ({elapsed}s)")
        return status, result.duration_ms

    except Exception as e:
        duration_ms = 0
        add_event(f"[W{worker_id}] ERROR: {str(e)[:40]}")
        update_state(worker_id, status="failed", last_action=f"ERROR: {str(e)[:25]}")
        return f"failed:{str(e)[:100]}", duration_ms


# ---------------------------------------------------------------------------
# Permanent failure classification
# ---------------------------------------------------------------------------

PERMANENT_FAILURES: set[str] = {
    "expired", "captcha", "login_issue",
    "not_eligible_location", "not_eligible_salary",
    "already_applied", "account_required",
    "not_a_job_application", "unsafe_permissions",
    "unsafe_verification", "sso_required",
    "site_blocked", "cloudflare_blocked", "blocked_by_cloudflare",
}

PERMANENT_PREFIXES: tuple[str, ...] = ("site_blocked", "cloudflare", "blocked_by")


def _is_permanent_failure(result: str) -> bool:
    """Determine if a failure should never be retried."""
    reason = result.split(":", 1)[-1] if ":" in result else result
    return (
        result in PERMANENT_FAILURES
        or reason in PERMANENT_FAILURES
        or any(reason.startswith(p) for p in PERMANENT_PREFIXES)
    )


# ---------------------------------------------------------------------------
# Worker loop
# ---------------------------------------------------------------------------

def worker_loop(worker_id: int = 0, limit: int = 1,
                target_url: str | None = None,
                min_score: int = 7, headless: bool = False,
                model: str = "sonnet", dry_run: bool = False) -> tuple[int, int]:
    """Run jobs sequentially until limit is reached or queue is empty.

    Args:
        worker_id: Numeric worker identifier.
        limit: Max jobs to process (0 = continuous).
        target_url: Apply to a specific URL.
        min_score: Minimum fit_score threshold.
        headless: Run Chrome headless.
        model: Claude model name.
        dry_run: Don't click Submit.

    Returns:
        Tuple of (applied_count, failed_count).
    """
    applied = 0
    failed = 0
    continuous = limit == 0
    jobs_done = 0
    empty_polls = 0
    port = BASE_CDP_PORT + worker_id

    while not _stop_event.is_set():
        if not continuous and jobs_done >= limit:
            break

        update_state(worker_id, status="idle", job_title="", company="",
                     last_action="waiting for job", actions=0)

        job = acquire_job(target_url=target_url, min_score=min_score,
                          worker_id=worker_id)
        if not job:
            if not continuous:
                add_event(f"[W{worker_id}] Queue empty")
                update_state(worker_id, status="done", last_action="queue empty")
                break
            empty_polls += 1
            update_state(worker_id, status="idle",
                         last_action=f"polling ({empty_polls})")
            if empty_polls == 1:
                add_event(f"[W{worker_id}] Queue empty, polling every {POLL_INTERVAL}s...")
            # Use Event.wait for interruptible sleep
            if _stop_event.wait(timeout=POLL_INTERVAL):
                break  # Stop was requested during wait
            continue

        empty_polls = 0

        chrome_proc = None
        try:
            add_event(f"[W{worker_id}] Launching Chrome...")
            chrome_proc = launch_chrome(worker_id, port=port, headless=headless)

            result, duration_ms = run_job(job, port=port, worker_id=worker_id,
                                            model=model, dry_run=dry_run)

            if result == "skipped":
                release_lock(job["url"])
                add_event(f"[W{worker_id}] Skipped: {job['title'][:30]}")
                continue
            elif result == "dryrun":
                release_lock(job["url"])
                add_event(f"[W{worker_id}] Dry-run OK: {job['title'][:30]}")
                jobs_done += 1
                continue
            elif result == "applied":
                mark_result(job["url"], "applied", duration_ms=duration_ms)
                applied += 1
                update_state(worker_id, jobs_applied=applied,
                             jobs_done=applied + failed)
            else:
                reason = result.split(":", 1)[-1] if ":" in result else result
                mark_result(job["url"], "failed", reason,
                            permanent=_is_permanent_failure(result),
                            duration_ms=duration_ms)
                failed += 1
                update_state(worker_id, jobs_failed=failed,
                             jobs_done=applied + failed)

        except KeyboardInterrupt:
            release_lock(job["url"])
            if _stop_event.is_set():
                break
            add_event(f"[W{worker_id}] Job skipped (Ctrl+C)")
            continue
        except Exception as e:
            logger.exception("Worker %d launcher error", worker_id)
            add_event(f"[W{worker_id}] Launcher error: {str(e)[:40]}")
            release_lock(job["url"])
            failed += 1
            update_state(worker_id, jobs_failed=failed)
        finally:
            if chrome_proc:
                cleanup_worker(worker_id, chrome_proc)

        jobs_done += 1
        if target_url:
            break

    update_state(worker_id, status="done", last_action="finished")
    return applied, failed


# ---------------------------------------------------------------------------
# Main entry point (called from cli.py)
# ---------------------------------------------------------------------------

def main(limit: int = 1, target_url: str | None = None,
         min_score: int = 7, headless: bool = False, model: str = "sonnet",
         dry_run: bool = False, continuous: bool = False,
         poll_interval: int = 60, workers: int = 1) -> None:
    """Launch the apply pipeline.

    Args:
        limit: Max jobs to apply to (0 or with continuous=True means run forever).
        target_url: Apply to a specific URL.
        min_score: Minimum fit_score threshold.
        headless: Run Chrome in headless mode.
        model: Claude model name.
        dry_run: Don't click Submit.
        continuous: Run forever, polling for new jobs.
        poll_interval: Seconds between DB polls when queue is empty.
        workers: Number of parallel workers (default 1).
    """
    global POLL_INTERVAL
    POLL_INTERVAL = poll_interval
    _stop_event.clear()

    config.ensure_dirs()
    console = Console()

    if not dry_run and not target_url:
        apply_dir = Path(os.environ.get("JOBWRIGHT_DIR", config.APP_DIR))
        confirm_file = apply_dir / "APPLY_CONFIRMED"
        if not confirm_file.exists():
            console.print(
                "[red]Live apply blocked:[/red] missing confirmation file "
                f"({confirm_file}). Reply CONFIRM APPLY after the morning digest."
            )
            raise SystemExit(1)
        manifest_env = os.environ.get("JOBWRIGHT_APPLY_MANIFEST")
        if not manifest_env or not Path(manifest_env).exists():
            console.print(
                "[red]Live apply blocked:[/red] JOBWRIGHT_APPLY_MANIFEST must point "
                "to a non-empty manifest file."
            )
            raise SystemExit(1)
        if not Path(manifest_env).read_text(encoding="utf-8").strip():
            console.print("[red]Live apply blocked:[/red] manifest file is empty.")
            raise SystemExit(1)

    if continuous:
        effective_limit = 0
        mode_label = "continuous"
    else:
        effective_limit = limit
        mode_label = f"{limit} jobs"

    # Initialize dashboard for all workers
    for i in range(workers):
        init_worker(i)

    worker_label = f"{workers} worker{'s' if workers > 1 else ''}"
    console.print(f"Launching apply pipeline ({mode_label}, {worker_label}, poll every {POLL_INTERVAL}s)...")
    console.print("[dim]Ctrl+C = skip current job(s) | Ctrl+C x2 = stop[/dim]")

    # Double Ctrl+C handler
    _ctrl_c_count = 0

    def _sigint_handler(sig, frame):
        nonlocal _ctrl_c_count
        _ctrl_c_count += 1
        if _ctrl_c_count == 1:
            console.print("\n[yellow]Skipping current job(s)... (Ctrl+C again to STOP)[/yellow]")
            # Kill all active agent processes to skip current jobs
            provider = _get_agent_provider()
            for wid in range(workers):
                provider.cancel(wid)
        else:
            console.print("\n[red bold]STOPPING[/red bold]")
            _stop_event.set()
            provider = _get_agent_provider()
            for wid in range(workers):
                provider.cancel(wid)
            kill_all_chrome()
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _sigint_handler)

    try:
        with Live(render_full(), console=console, refresh_per_second=2) as live:
            # Daemon thread for display refresh only (no business logic)
            _dashboard_running = True

            def _refresh():
                while _dashboard_running:
                    live.update(render_full())
                    time.sleep(0.5)

            refresh_thread = threading.Thread(target=_refresh, daemon=True)
            refresh_thread.start()

            if workers == 1:
                # Single worker — run directly in main thread
                total_applied, total_failed = worker_loop(
                    worker_id=0,
                    limit=effective_limit,
                    target_url=target_url,
                    min_score=min_score,
                    headless=headless,
                    model=model,
                    dry_run=dry_run,
                )
            else:
                # Multi-worker — distribute limit across workers
                if effective_limit:
                    base = effective_limit // workers
                    extra = effective_limit % workers
                    limits = [base + (1 if i < extra else 0)
                              for i in range(workers)]
                else:
                    limits = [0] * workers  # continuous mode

                with ThreadPoolExecutor(max_workers=workers,
                                        thread_name_prefix="apply-worker") as executor:
                    futures = {
                        executor.submit(
                            worker_loop,
                            worker_id=i,
                            limit=limits[i],
                            target_url=target_url,
                            min_score=min_score,
                            headless=headless,
                            model=model,
                            dry_run=dry_run,
                        ): i
                        for i in range(workers)
                    }

                    results: list[tuple[int, int]] = []
                    for future in as_completed(futures):
                        wid = futures[future]
                        try:
                            results.append(future.result())
                        except Exception:
                            logger.exception("Worker %d crashed", wid)
                            results.append((0, 0))

                total_applied = sum(r[0] for r in results)
                total_failed = sum(r[1] for r in results)

            _dashboard_running = False
            refresh_thread.join(timeout=2)
            live.update(render_full())

        totals = get_totals()
        console.print(
            f"\n[bold]Done: {total_applied} applied, {total_failed} failed "
            f"(${totals['cost']:.3f})[/bold]"
        )
        console.print(f"Logs: {config.LOG_DIR}")

    except KeyboardInterrupt:
        pass
    finally:
        _stop_event.set()
        kill_all_chrome()
