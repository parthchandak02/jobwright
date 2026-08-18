"""Simplified WhatsApp daily-notify for newly prepared jobs.

Sends one plain-text message per run listing prepare-stage jobs that have not
been notified yet, with a deep link per job. Each job is marked so it is never
re-sent. Delivery uses the same ``hermes send`` invocation as the digest script.
"""

from __future__ import annotations

import os
import subprocess

from jobwright.config import get_active_user_id
from jobwright.database import (
    get_unnotified_prepare_jobs,
    job_id_for_url,
    mark_whatsapp_notified,
)
from jobwright.users import get_user

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


def send_via_hermes(message: str, target: str) -> None:
    """Deliver a message to a WhatsApp target via the hermes CLI."""
    result = subprocess.run(
        ["hermes", "send", "--to", target, "--quiet", message],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"hermes send failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def run_notify(dry_run: bool = False) -> dict:
    """Notify the active user of newly prepared jobs via WhatsApp.

    Skips silently (no send) when there are no new prepare jobs. When not a
    dry run, sends the message then marks the jobs so they are not re-sent.

    Raises:
        ValueError: The active user has no whatsapp_target configured.
    """
    jobs = get_unnotified_prepare_jobs()
    if not jobs:
        return {"sent": 0, "skipped": True, "reason": "no new prepare jobs", "jobs": []}

    base_url = os.environ.get("JOBWRIGHT_PUBLIC_BASE_URL", DEFAULT_BASE_URL)
    message = build_notification(jobs, base_url)

    job_summaries = [
        {
            "job_id": job_id_for_url(job.get("url") or ""),
            "title": job.get("title"),
            "company": job.get("company"),
        }
        for job in jobs
    ]

    if dry_run:
        return {
            "sent": 0,
            "skipped": False,
            "dry_run": True,
            "message": message,
            "jobs": job_summaries,
        }

    active = get_active_user_id()
    user = get_user(active) if active else None
    target = user.whatsapp_target if user else ""
    if not target:
        raise ValueError(
            f"No whatsapp_target configured for active user '{active}'. "
            f"Set one with: jobwright users set {active or '<id>'} --whatsapp <target>"
        )

    send_via_hermes(message, target)
    mark_whatsapp_notified([job["url"] for job in jobs])

    return {
        "sent": len(jobs),
        "skipped": False,
        "message": message,
        "jobs": job_summaries,
    }
