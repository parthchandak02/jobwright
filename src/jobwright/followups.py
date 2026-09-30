"""Follow-up reminders: applied jobs with no stage change for N days.

A job is due when it has sat in Applied for ``followup_days`` (users.yaml,
default 10) since it last changed stage or was last followed up. "Followed up"
stamps ``followed_up_at`` and snoozes via ``follow_up_at``; "No response"
closes the job with close_reason ``no_response``.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from jobwright.database import advance_funnel, get_connection, job_id_for_url

NO_RESPONSE_REASON = "no_response"
NO_RESPONSE_OUTCOME = "ghosted"

LAST_CHANGE_SQL = "(SELECT MAX(h.at) FROM stage_history h WHERE h.job_url = jobs.url)"


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def resolve_days(days: int | None) -> int:
    if days:
        return int(days)
    from jobwright.config import get_active_user_id
    from jobwright.users import get_followup_days

    return get_followup_days(get_active_user_id())


def last_stage_change(conn: sqlite3.Connection, url: str) -> str | None:
    row = conn.execute("SELECT MAX(at) FROM stage_history WHERE job_url = ?", (url,)).fetchone()
    return row[0] if row else None


def followup_state(job: dict, last_change: str | None, days: int, now: datetime | None = None) -> dict | None:
    """Follow-up fields for one job, or None when it is not in Applied."""
    if (job.get("funnel_stage") or "backlog") != "applied":
        return None
    now = now or datetime.now(UTC)
    applied = _parse(last_change) or _parse(job.get("applied_at"))
    if applied is None:
        return None
    base = max(applied, _parse(job.get("followed_up_at")) or applied)
    snoozed_until = _parse(job.get("follow_up_at"))
    due_at = snoozed_until if snoozed_until and snoozed_until > applied else base + timedelta(days=days)
    return {
        "followup_due": now >= due_at,
        "applied_days_ago": max((now - applied).days, 0),
        "followup_due_at": due_at.isoformat(),
    }


def due_followups(
    conn: sqlite3.Connection | None = None,
    days: int | None = None,
    limit: int | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Applied jobs whose follow-up is due, longest-waiting first."""
    conn = conn or get_connection()
    days = resolve_days(days)
    rows = conn.execute(
        f"SELECT *, {LAST_CHANGE_SQL} AS last_stage_at FROM jobs WHERE funnel_stage = 'applied'"
    ).fetchall()
    out = []
    for row in rows:
        d = dict(row)
        state = followup_state(d, d.get("last_stage_at"), days, now)
        if not state or not state["followup_due"]:
            continue
        out.append({
            "url": d["url"],
            "job_id": d.get("job_id") or job_id_for_url(d["url"]),
            "title": d.get("title") or "Untitled role",
            "company": d.get("company") or "Unknown",
            **state,
        })
    out.sort(key=lambda j: j["applied_days_ago"], reverse=True)
    return out[:limit] if limit else out


def record_followed_up(url: str, days: int | None = None, conn: sqlite3.Connection | None = None) -> None:
    """Stamp a follow-up and snooze the reminder for ``days``."""
    conn = conn or get_connection()
    now = datetime.now(UTC)
    conn.execute(
        "UPDATE jobs SET followed_up_at = ?, follow_up_at = ?, board_updated_by = 'human', "
        "board_updated_at = ? WHERE url = ?",
        (now.isoformat(), (now + timedelta(days=resolve_days(days))).isoformat(), now.isoformat(), url),
    )
    conn.commit()


def record_no_response(url: str, conn: sqlite3.Connection | None = None) -> None:
    """Close an applied job that never got a reply."""
    conn = conn or get_connection()
    advance_funnel(url, "closed", "human", note="no response", outcome=NO_RESPONSE_OUTCOME, conn=conn)
    conn.execute("UPDATE jobs SET close_reason = ? WHERE url = ?", (NO_RESPONSE_REASON, url))
    conn.commit()


def format_followups(items: list[dict], base_url: str) -> str:
    """WhatsApp block listing due follow-ups (same card style as the daily list)."""
    from jobwright.whatsapp import bold

    base_url = base_url.rstrip("/")
    lines = ["\u23f0 " + bold("Time to follow up") + " (no reply yet)"]
    for job in items:
        days = job["applied_days_ago"]
        lines.append("")
        lines.append(bold(job["title"]))
        lines.append(f"\U0001f3e2 {job['company']}  \u00b7  applied {days} day{'s' if days != 1 else ''} ago")
        lines.append(f"\U0001f517 {base_url}/jobs/{job['job_id']}")
    return "\n".join(lines)
