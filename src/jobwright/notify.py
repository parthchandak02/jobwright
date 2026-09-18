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
from jobwright.users import get_brief_top_n, get_human_gate, get_user


def get_unnotified_gated_jobs(conn=None):
    """Review-first candidate pool (human_gate=true).

    Gated pipelines stop at backlog (materials wait for approval), so the
    brief selects high-scoring unnotified BACKLOG jobs instead of prepare
    jobs. Falls back to prepare jobs for anything the dashboard moved on.
    """
    from jobwright.database import get_connection

    if conn is None:
        conn = get_connection()
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM jobs "
        "WHERE funnel_stage = 'backlog' AND fit_score >= 7 "
        "AND whatsapp_notified_at IS NULL "
        "ORDER BY COALESCE(user_fit_score, fit_score) DESC NULLS LAST, discovered_at DESC"
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        out.append({
            "url": d.get("url"),
            "title": d.get("title") or "Untitled role",
            "company": d.get("company") or "Unknown",
            "location": d.get("location") or "Location n/a",
            "fit_score": d.get("fit_score"),
            "job_id": d.get("job_id"),
        })
    if out:
        return out
    return get_unnotified_prepare_jobs(conn)

DEFAULT_BASE_URL = "https://jobwright.parthchandak.info"


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


def send_via_hermes(message: str, target: str) -> None:
    """Deliver a message to a WhatsApp target via the hermes CLI."""
    result = subprocess.run(
        ["hermes", "send", "--to", target, "--quiet", message],
        capture_output=True,
        text=True,
        check=False,
    )
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
    ensure_brief_items()
    active = get_active_user_id()
    human_gate = get_human_gate(active)
    jobs = (get_unnotified_gated_jobs() if human_gate else get_unnotified_prepare_jobs())
    if not jobs:
        return {"sent": 0, "skipped": True, "reason": "no new prepare jobs", "jobs": []}

    base_url = os.environ.get("JOBWRIGHT_PUBLIC_BASE_URL", DEFAULT_BASE_URL)

    top_n = get_brief_top_n(active)
    shown = jobs if top_n == 0 else jobs[:top_n]
    capped = top_n > 0 and len(jobs) > top_n
    shown_urls = [job["url"] for job in shown]

    if human_gate:
        message = build_review_notification(shown, base_url)
    else:
        message = build_notification(shown, base_url)

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
        }

    user = get_user(active) if active else None
    target = user.whatsapp_target if user else ""
    if not target:
        raise ValueError(
            f"No whatsapp_target configured for active user '{active}'. "
            f"Set one with: jobwright users set {active or '<id>'} --whatsapp <target>"
        )

    send_via_hermes(message, target)
    # Snapshot after a successful send so items never delivered are not counted
    # as precision data.
    record_brief_items(jobs, shown_urls)
    mark_whatsapp_notified(shown_urls)

    return {
        "sent": len(shown),
        "skipped": False,
        "message": message,
        "human_gate": human_gate,
        "top_n": top_n,
        "capped": capped,
        "jobs": job_summaries,
    }