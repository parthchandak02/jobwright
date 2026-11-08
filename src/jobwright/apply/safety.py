"""Safety rails for automatic applications.

Checked by ``apply/runner.py`` before every attempt (and by ``apply auto``
when it picks jobs):

- ``JOBWRIGHT_APPLY_KILL`` (any non-empty value except 0/false/no) stops every
  apply, dry runs included.
- Live submits need ``apply_enabled`` in users.yaml, and the profile must not
  be ``apply_paused`` (set automatically after ``CONSECUTIVE_FAILURE_LIMIT``
  failed or unverified live attempts in a row).
- ``apply_daily_cap`` live submissions per local day (default 2).
- ``apply_min_score`` (default 8) on the effective score (the person's own
  rating wins over the model's).
- No second application for the same ``dedupe_key`` (company + title + place)
  ever, nor more than ``apply_employer_cap`` (default 1) to one employer within
  ``EMPLOYER_WINDOW_DAYS`` days. Counted from ``submissions`` (live outcomes
  applied / unverified) and ``jobs.applied_at`` (including hand-marked).
- LinkedIn and other ``apply_blocked`` sites are never applied to.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from jobwright.database import get_connection

log = logging.getLogger(__name__)

CONSECUTIVE_FAILURE_LIMIT = 2
EMPLOYER_WINDOW_DAYS = 30
# Live outcomes that count as "an application went out" for caps and dedupe.
SUBMITTED_OUTCOMES = ("applied", "unverified")
# Live outcomes that count toward the auto-pause.
FAILURE_OUTCOMES = ("failed", "unverified", "error")


def kill_switch_on() -> bool:
    raw = os.environ.get("JOBWRIGHT_APPLY_KILL", "").strip().lower()
    return bool(raw) and raw not in ("0", "false", "no", "off")


@dataclass
class GateResult:
    ok: bool
    reasons: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:  # pragma: no cover - convenience
        return self.ok


def _user(user_id: str | None):
    from jobwright.users import get_user

    return get_user(user_id) if user_id else None


def _local_day_start_utc() -> str:
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.astimezone(timezone.utc).isoformat()


def live_submissions_today(conn=None) -> int:
    conn = conn or get_connection()
    row = conn.execute(
        f"SELECT COUNT(*) FROM submissions WHERE dry_run = 0 AND outcome IN "
        f"({','.join('?' * len(SUBMITTED_OUTCOMES))}) AND started_at >= ?",
        (*SUBMITTED_OUTCOMES, _local_day_start_utc()),
    ).fetchone()
    return int(row[0])


def employer_key(company: str | None) -> str:
    t = re.sub(r"[^a-z0-9 ]+", " ", (company or "").lower())
    t = re.sub(r"\b(inc|llc|ltd|corp|corporation|co|company|plc|gmbh)\b", " ", t)
    return " ".join(t.split())


def employer_applications(company: str | None, conn=None, days: int = EMPLOYER_WINDOW_DAYS) -> int:
    key = employer_key(company)
    if not key:
        return 0
    conn = conn or get_connection()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    n = 0
    for row in conn.execute(
        f"SELECT company FROM submissions WHERE dry_run = 0 AND outcome IN "
        f"({','.join('?' * len(SUBMITTED_OUTCOMES))}) AND started_at >= ?",
        (*SUBMITTED_OUTCOMES, since),
    ).fetchall():
        if employer_key(row[0]) == key:
            n += 1
    seen_urls = {r[0] for r in conn.execute(
        "SELECT job_url FROM submissions WHERE dry_run = 0 AND outcome IN "
        f"({','.join('?' * len(SUBMITTED_OUTCOMES))})", SUBMITTED_OUTCOMES).fetchall()}
    for row in conn.execute(
        "SELECT url, company FROM jobs WHERE applied_at IS NOT NULL AND applied_at >= ?", (since,)
    ).fetchall():
        if row[0] not in seen_urls and employer_key(row[1]) == key:
            n += 1
    return n


def already_applied_same_posting(job: dict, conn=None) -> bool:
    """Same dedupe_key (company | title | place) applied to before, any time."""
    conn = conn or get_connection()
    key = job.get("dedupe_key")
    url = job.get("url")
    if key:
        row = conn.execute(
            "SELECT 1 FROM jobs WHERE dedupe_key = ? AND url != ? AND applied_at IS NOT NULL LIMIT 1",
            (key, url),
        ).fetchone()
        if row:
            return True
        row = conn.execute(
            "SELECT 1 FROM submissions WHERE dedupe_key = ? AND dry_run = 0 AND outcome IN "
            f"({','.join('?' * len(SUBMITTED_OUTCOMES))}) LIMIT 1",
            (key, *SUBMITTED_OUTCOMES),
        ).fetchone()
        if row:
            return True
    row = conn.execute(
        "SELECT 1 FROM submissions WHERE job_url = ? AND dry_run = 0 AND outcome IN "
        f"({','.join('?' * len(SUBMITTED_OUTCOMES))}) LIMIT 1",
        (url, *SUBMITTED_OUTCOMES),
    ).fetchone()
    return bool(row)


def effective_score(job: dict) -> int | None:
    user_score = job.get("user_fit_score")
    if user_score is not None:
        return int(user_score)
    score = job.get("fit_score")
    return int(score) if score is not None else None


def consecutive_failures(conn=None) -> int:
    conn = conn or get_connection()
    rows = conn.execute(
        "SELECT outcome FROM submissions WHERE dry_run = 0 AND outcome NOT IN "
        "('needs_answer', 'skipped', 'blocked', 'captcha_timeout', 'expired') "
        "ORDER BY id DESC LIMIT 10"
    ).fetchall()
    n = 0
    for (outcome,) in rows:
        if outcome in FAILURE_OUTCOMES:
            n += 1
        else:
            break
    return n


def maybe_auto_pause(user_id: str | None, conn=None) -> bool:
    """Pause the profile after CONSECUTIVE_FAILURE_LIMIT failures in a row."""
    if not user_id:
        return False
    n = consecutive_failures(conn)
    if n < CONSECUTIVE_FAILURE_LIMIT:
        return False
    user = _user(user_id)
    if user is None or user.apply_paused:
        return False
    from jobwright.users import update_user

    reason = f"{n} failed or unverified applications in a row"
    update_user(user_id, apply_paused=True, apply_paused_reason=reason)
    log.warning("Auto-apply paused for %s: %s", user_id, reason)
    return True


def check_profile(user_id: str | None, *, live: bool) -> GateResult:
    """Profile-level gates (kill switch, enabled, paused, daily cap)."""
    reasons: list[str] = []
    if kill_switch_on():
        reasons.append("kill switch JOBWRIGHT_APPLY_KILL is set")
    if live:
        user = _user(user_id)
        if user is None:
            reasons.append("unknown profile")
        else:
            if not user.apply_enabled:
                reasons.append("apply_enabled is false")
            if user.apply_paused:
                reasons.append(f"auto-apply paused: {user.apply_paused_reason or 'paused'}")
            cap = user.apply_daily_cap
            if live_submissions_today() >= cap:
                reasons.append(f"daily cap reached ({cap})")
    return GateResult(not reasons, reasons)


def check_job(job: dict, user_id: str | None, *, live: bool, min_score: int | None = None) -> GateResult:
    """Job-level gates (blocked site, score, dedupe, employer cap)."""
    from jobwright.config import is_apply_blocked_job, is_discovery_blocked_job

    reasons: list[str] = []
    url = job.get("url") or ""
    if is_apply_blocked_job(job.get("site"), url, application_url=job.get("application_url")):
        reasons.append("site is never applied to automatically (LinkedIn / apply_blocked)")
    elif is_discovery_blocked_job(job.get("site"), url):
        reasons.append("site is blocked")
    user = _user(user_id)
    threshold = min_score if min_score is not None else (user.apply_min_score if user else 8)
    score = effective_score(job)
    if score is None or score < threshold:
        reasons.append(f"score {score} is below {threshold}")
    if job.get("applied_at"):
        reasons.append("already marked applied")
    if already_applied_same_posting(job):
        reasons.append("already applied to this posting (same company and title)")
    if live:
        cap = user.apply_employer_cap if user else 1
        if employer_applications(job.get("company")) >= cap:
            reasons.append(f"already applied to {job.get('company') or 'this employer'} "
                           f"in the last {EMPLOYER_WINDOW_DAYS} days")
    return GateResult(not reasons, reasons)
