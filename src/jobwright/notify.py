"""Simplified WhatsApp daily-notify for newly prepared jobs.

Sends one plain-text message per run listing prepare-stage jobs that have not
been notified yet, with a deep link per job. Each job is marked so it is never
re-sent. Delivery uses the same ``hermes send`` invocation as the digest script.

Two formats:
  * default — "N new jobs ready to review:" (legacy "newly prepared" list)
  * human-gate (``human_gate=true``) — review-first: top-N jobs by fit score
    with deep links, plus a note that materials are generated after approval.

The notify list is capped to the user's ``brief_top_n`` (default 0 = uncapped).
After each send a ``brief_items`` snapshot is recorded in the
scoreboard so precision (% advanced) can be tracked per brief.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess

from jobwright.briefstats import ensure_brief_items, record_brief_items
from jobwright.config import get_active_user_id
from jobwright.database import (
    get_unnotified_prepare_jobs,
    job_id_for_url,
    mark_whatsapp_notified,
)
from jobwright.followups import format_followups
from jobwright.users import get_brief_top_n, get_human_gate, get_user


def _notify_threshold() -> int:
    """Per-user notify threshold from match_criteria (default 7)."""
    from jobwright.config import load_profile
    from jobwright.scoring.criteria import load_criteria

    try:
        return load_criteria(load_profile()).notify_threshold
    except FileNotFoundError:
        return 7


def _max_age_days() -> int:
    try:
        return int(os.environ.get("JOBWRIGHT_BRIEF_MAX_AGE_DAYS", "7"))
    except ValueError:
        return 7


def _identity(job: dict) -> str:
    from jobwright.discovery.dedupe import normalize_company, normalize_title

    return f"{normalize_company(job.get('company'))}|{normalize_title(job.get('title'))}"


def _recently_notified_identities(conn, days: int = 60) -> set[str]:
    rows = conn.execute(
        "SELECT title, company FROM jobs WHERE whatsapp_notified_at >= datetime('now', ?)",
        (f"-{days} days",),
    ).fetchall()
    return {_identity({"title": r[0], "company": r[1]}) for r in rows}


def _dedupe_for_notify(conn, jobs: list[dict]) -> list[dict]:
    """Drop reposts of jobs already sent recently, and duplicates within this list."""
    seen = _recently_notified_identities(conn)
    out = []
    for job in jobs:
        ident = _identity(job)
        if ident.strip("|") and ident in seen:
            continue
        seen.add(ident)
        out.append(job)
    return out


def get_unnotified_gated_jobs(conn=None, max_age_days: int | None = None, threshold: int | None = None):
    """Review-first candidate pool (human_gate=true).

    Gated pipelines stop at backlog (materials wait for approval), so the
    brief selects high-scoring unnotified BACKLOG jobs instead of prepare
    jobs. Falls back to prepare jobs for anything the dashboard moved on.

    Freshness guard (Sep 19): only jobs discovered within ``max_age_days``
    (default 7, override with JOBWRIGHT_BRIEF_MAX_AGE_DAYS) are eligible, so a
    dead scoring run never re-surfaces stale jobs as fresh finds.
    """
    from jobwright.database import get_connection

    if conn is None:
        conn = get_connection()
    conn.row_factory = sqlite3.Row
    if max_age_days is None:
        max_age_days = _max_age_days()
    if threshold is None:
        threshold = _notify_threshold()
    rows = conn.execute(
        "SELECT * FROM jobs "
        "WHERE funnel_stage = 'backlog' AND COALESCE(user_fit_score, fit_score) >= ? "
        "AND whatsapp_notified_at IS NULL "
        "AND discovered_at >= datetime('now', ?) "
        "ORDER BY COALESCE(user_fit_score, fit_score) DESC NULLS LAST, "
        "COALESCE(score_confidence, 0) DESC, discovered_at DESC",
        (int(threshold), f"-{int(max_age_days)} days"),
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        out.append({
            "url": d.get("url"),
            "title": d.get("title") or "Untitled role",
            "company": d.get("company") or "Unknown",
            "location": d.get("location") or "Location n/a",
            "fit_score": d.get("user_fit_score") or d.get("fit_score"),
            "job_id": d.get("job_id"),
        })
    if out:
        return out
    return get_unnotified_prepare_jobs(conn)


def count_worth_a_look(conn=None, max_age_days: int | None = None, threshold: int | None = None) -> int:
    """Fresh backlog jobs just under the notify bar with no hard dealbreaker."""
    from jobwright.database import get_connection

    conn = conn or get_connection()
    threshold = threshold if threshold is not None else _notify_threshold()
    max_age_days = max_age_days if max_age_days is not None else _max_age_days()
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE funnel_stage = 'backlog' AND whatsapp_notified_at IS NULL "
            "AND COALESCE(user_fit_score, fit_score) BETWEEN ? AND ? "
            "AND discovered_at >= datetime('now', ?) "
            "AND (score_gates IS NULL OR score_gates NOT LIKE '%\"dealbreakers\": [\"%')",
            (int(threshold) - 2, int(threshold) - 1, f"-{int(max_age_days)} days"),
        ).fetchone()[0]
    )


DEFAULT_BASE_URL = "https://jobwright.parthchandak.info"
MAX_FOLLOWUPS = 3


def public_base_url() -> str:
    return os.environ.get("JOBWRIGHT_PUBLIC_BASE_URL", DEFAULT_BASE_URL)


def followup_appendix(conn=None, limit: int = MAX_FOLLOWUPS) -> list[dict]:
    """Due follow-ups for the end of a message; never breaks the notice."""
    from jobwright.followups import due_followups

    try:
        return due_followups(conn, limit=limit)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("follow-up lookup failed")
        return []


def build_notification(jobs: list[dict], base_url: str) -> str:
    """Build a plain-text WhatsApp message (no markdown, hyphens only)."""
    base_url = base_url.rstrip("/")
    count = len(jobs)
    header = f"{count} new job{'s' if count != 1 else ''} ready to review:"
    lines = [header]
    for job in jobs:
        url = job.get("url") or ""
        job_id = job_id_for_url(url)
        title = job.get("title") or "Untitled role"
        company = job.get("company") or "Unknown"
        location = job.get("location") or "Location n/a"
        score = job.get("fit_score")
        score_text = str(score) if score is not None else "n/a"
        lines.append("")
        lines.append(f"\u2022 {title} @ {company}")
        lines.append(f"  {location} \u00b7 score {score_text}")
        lines.append(f"  {base_url}/jobs/{job_id}")
    return "\n".join(lines)


def build_review_notification(jobs: list[dict], base_url: str) -> str:
    """Build the human-gate review-first message (top-N by fit score).

    Same WhatsApp formatting (plain text, hyphens only) as the default list,
    but framed as jobs for the user to review before any materials exist.
    """
    base_url = base_url.rstrip("/")
    count = len(jobs)
    header = f"{count} new job{'s' if count != 1 else ''} for your review:"
    lines = [header]
    for job in jobs:
        url = job.get("url") or ""
        job_id = job_id_for_url(url)
        title = job.get("title") or "Untitled role"
        company = job.get("company") or "Unknown"
        location = job.get("location") or "Location n/a"
        score = job.get("fit_score")
        score_text = str(score) if score is not None else "n/a"
        lines.append("")
        lines.append(f"\u2022 {title} @ {company}")
        lines.append(f"  {location} \u00b7 score {score_text}")
        lines.append(f"  {base_url}/jobs/{job_id}")
    lines.append("")
    lines.append(
        "Tailored resume + cover letter are generated after you approve a job. "
        "Open the link to review it and start preparing."
    )
    return "\n".join(lines)


HERMES_SEND_TIMEOUT = 90


def send_via_hermes(message: str, target: str) -> None:
    """Deliver a message to a WhatsApp target via the hermes CLI (bounded)."""
    from jobwright.hermes_cron import hermes_dry_run

    if hermes_dry_run():
        import logging

        logging.getLogger(__name__).warning("HERMES DRY RUN: would send to %s:\n%s", target, message)
        return
    try:
        result = subprocess.run(
            ["hermes", "send", "--to", target, "--quiet", message],
            capture_output=True,
            text=True,
            check=False,
            timeout=HERMES_SEND_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"hermes send timed out after {HERMES_SEND_TIMEOUT}s") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("hermes CLI not found on PATH") from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"hermes send failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def run_notify(dry_run: bool = False) -> dict:
    """Notify the active user of newly prepared jobs via WhatsApp.

    Respects the user's ``human_gate`` (review-first format) and
    ``brief_top_n`` (cap on the notify list; 0 = uncapped). Before sending, a
    brief_items snapshot is recorded for the scoreboard. Skips silently (no
    send) when there are no new prepare jobs. When not a dry run, sends the
    message then marks only the jobs that were actually shown so they are not
    re-sent.

    Raises:
        ValueError: The active user has no whatsapp_target configured.
    """
    from jobwright.database import get_connection

    ensure_brief_items()
    conn = get_connection()
    active = get_active_user_id()
    human_gate = get_human_gate(active)
    threshold = _notify_threshold()
    jobs = (get_unnotified_gated_jobs(threshold=threshold) if human_gate else get_unnotified_prepare_jobs())
    jobs = _dedupe_for_notify(conn, jobs)
    if not jobs:
        reason = (
            f"no new matches scored {threshold}+ in the last {_max_age_days()} days"
            if human_gate else "no newly prepared jobs"
        )
        return {"sent": 0, "skipped": True, "reason": reason, "jobs": [], "threshold": threshold}

    base_url = public_base_url()

    top_n = get_brief_top_n(active)
    shown = jobs if top_n == 0 else jobs[:top_n]
    capped = top_n > 0 and len(jobs) > top_n
    shown_urls = [job["url"] for job in shown]

    if human_gate:
        message = build_review_notification(shown, base_url)
    else:
        message = build_notification(shown, base_url)
    worth = count_worth_a_look(conn, threshold=threshold) if human_gate else 0
    if worth:
        message += (
            f"\n\n+ {worth} more worth a look (just under your bar): "
            f"{base_url.rstrip('/')}/?view=list&worth=1"
        )
    followups = followup_appendix(conn)
    if followups:
        message += "\n\n" + format_followups(followups, base_url)

    job_summaries = [
        {
            "job_id": job_id_for_url(job.get("url") or ""),
            "title": job.get("title"),
            "company": job.get("company"),
        }
        for job in shown
    ]

    if dry_run:
        return {
            "sent": 0,
            "skipped": False,
            "dry_run": True,
            "message": message,
            "human_gate": human_gate,
            "top_n": top_n,
            "capped": capped,
            "jobs": job_summaries,
            "followups": len(followups),
        }

    user = get_user(active) if active else None
    target = user.whatsapp_target if user else ""
    if not target:
        raise ValueError(
            f"No whatsapp_target configured for active user '{active}'. "
            f"Set one with: jobwright users set {active or '<id>'} --whatsapp <target>"
        )

    # Mark first, then send; roll the mark back if delivery fails. A crash
    # between the two can only lose a notice, never re-send one.
    marked = mark_whatsapp_notified(shown_urls, conn=conn)
    conn.commit()
    try:
        send_via_hermes(message, target)
    except Exception:
        placeholders = ", ".join("?" for _ in shown_urls)
        conn.execute(f"UPDATE jobs SET whatsapp_notified_at = NULL WHERE url IN ({placeholders})", shown_urls)
        conn.commit()
        raise
    # Snapshot after a successful send so items never delivered are not counted
    # as precision data.
    record_brief_items(jobs, shown_urls)
    del marked

    return {
        "sent": len(shown),
        "skipped": False,
        "message": message,
        "human_gate": human_gate,
        "top_n": top_n,
        "capped": capped,
        "jobs": job_summaries,
        "followups": len(followups),
    }