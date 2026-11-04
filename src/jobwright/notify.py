"""Simplified WhatsApp daily-notify for newly prepared jobs.

Sends one plain-text message per run listing prepare-stage jobs that have not
been notified yet, with a deep link per job. Each job is marked so it is never
re-sent. Delivery uses the same ``hermes send`` invocation as the digest script.

Two formats:
  * default — "N new jobs ready to review:" (legacy "newly prepared" list)
  * human-gate (``human_gate=true``) — review-first: top-N jobs by fit score
    with deep links, plus a note that materials are generated after approval.

The notify list is capped to the user's ``brief_top_n`` (default 0 = uncapped).
When the person paused the search (``search_enabled: false``) the scheduled
notify sends no job list, only due follow-ups, and only when that set changed
since the last follow-up-only message (``logs/followup_notice.json``).
After each send a ``brief_items`` snapshot is recorded in the
scoreboard so precision (% advanced) can be tracked per brief.

Never twice: a per-profile notify lock (``.notify.lock``, non-blocking; a
second caller returns "already sending") plus an atomic claim of the rows
(``UPDATE ... WHERE whatsapp_notified_at IS NULL RETURNING url``) mean only
jobs this call claimed are sent, and only those are released if the send
fails. A ``hermes send`` timeout is different: the message may well have gone
out, so the claim is kept (no automatic resend, same day or later), the jobs
are logged in ``logs/notify_uncertain.json`` and the status line reads
``notify_uncertain``; the operator checks the chat and, if nothing arrived,
runs ``jobwright --user <id> ops release-uncertain`` before the next notify.
"""

from __future__ import annotations

import fcntl
import json
import os
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

from jobwright.briefstats import ensure_brief_items, record_brief_items
from jobwright.config import get_active_user_id
from jobwright.database import (
    get_unnotified_prepare_jobs,
    job_id_for_url,
)
from jobwright.followups import format_followups
from jobwright.users import get_brief_top_n, get_human_gate, get_user, is_search_enabled
from jobwright.whatsapp import bold, italic


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
            "location": d.get("location"),
            "fit_score": d.get("user_fit_score") or d.get("fit_score"),
            "job_id": d.get("job_id"),
            "date_posted": d.get("date_posted"),
            "discovered_at": d.get("discovered_at"),
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


def _short_date(d: date) -> str:
    return f"{d:%b} {d.day}"


def _posted_line(job: dict) -> str:
    """Posted date from the board, else the day jobwright found the job (labelled "Found")."""
    posted = (job.get("date_posted") or "")[:10]
    try:
        return f"\U0001f4c5 Posted {_short_date(date.fromisoformat(posted))}"
    except ValueError:
        pass
    found = job.get("discovered_at") or ""
    try:
        return f"\U0001f4c5 Found {_short_date(datetime.fromisoformat(found).astimezone().date())}"
    except ValueError:
        return "\U0001f4c5 Posted date not listed"


def _job_lines(n: int, job: dict, base_url: str) -> list[str]:
    """One numbered job card: bold title, company + match, location, posted date, dashboard link."""
    score = job.get("fit_score")
    company = f"\U0001f3e2 {job.get('company') or 'Unknown company'}"
    if score is not None:
        company += f"  \u00b7  \u2b50 {score}/10 match"
    return [
        "",
        bold(f"{n}. {job.get('title') or 'Untitled role'}"),
        company,
        f"\U0001f4cd {job.get('location') or 'Location not listed'}",
        _posted_line(job),
        f"\U0001f517 {base_url}/jobs/{job_id_for_url(job.get('url') or '')}",
    ]


def _header(count: int, what: str) -> str:
    return "\u2728 " + bold(f"{count} new job{'s' if count != 1 else ''} {what}")


def build_notification(jobs: list[dict], base_url: str) -> str:
    """WhatsApp message (native *bold* / _italic_, one emoji per field) listing prepared jobs."""
    base_url = base_url.rstrip("/")
    lines = [_header(len(jobs), "ready to review")]
    for n, job in enumerate(jobs, 1):
        lines += _job_lines(n, job, base_url)
    return "\n".join(lines)


def build_review_notification(jobs: list[dict], base_url: str) -> str:
    """Build the human-gate review-first message (top-N by fit score).

    Same job cards as the default list, but framed as jobs for the user to
    review before any materials exist.
    """
    base_url = base_url.rstrip("/")
    lines = [_header(len(jobs), "for your review")]
    for n, job in enumerate(jobs, 1):
        lines += _job_lines(n, job, base_url)
    lines.append("")
    lines.append(italic(
        "Tailored resume + cover letter are generated after you approve a job. "
        "Open a link to review it and start preparing."
    ))
    return "\n".join(lines)


def worth_a_look_line(worth: int, base_url: str) -> str:
    return (f"\U0001f440 {bold(f'+{worth} more worth a look')} (just under your bar)\n"
            f"\U0001f517 {base_url.rstrip('/')}/?view=list&worth=1")


HERMES_SEND_TIMEOUT = 90


class SendUncertain(RuntimeError):
    """The send may or may not have been delivered (hermes timed out)."""


class NotifyBusy(RuntimeError):
    """Another notify for this profile holds the lock."""


@contextmanager
def notify_lock():
    """Per-profile, non-blocking: a concurrent notify raises NotifyBusy instead of waiting."""
    import jobwright.config as config

    path = Path(config.APP_DIR) / ".notify.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = path.open("a+")
    try:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise NotifyBusy("already sending (another notify holds the lock)") from exc
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()} at={datetime.now(timezone.utc).isoformat()}")
        fh.flush()
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        fh.close()


_HAS_RETURNING = sqlite3.sqlite_version_info >= (3, 35, 0)


def claim_for_notify(conn: sqlite3.Connection, urls: list[str], stamp: str) -> list[str]:
    """Atomically stamp the still-unnotified rows among ``urls``; returns the urls this call claimed."""
    if not urls:
        return []
    placeholders = ", ".join("?" for _ in urls)
    sql = (f"UPDATE jobs SET whatsapp_notified_at = ? "
           f"WHERE url IN ({placeholders}) AND whatsapp_notified_at IS NULL")
    if conn.in_transaction:
        conn.commit()
    if _HAS_RETURNING:
        claimed = [r[0] for r in conn.execute(sql + " RETURNING url", [stamp, *urls]).fetchall()]
        conn.commit()
    else:  # SQLite < 3.35: claim inside a write transaction
        conn.execute("BEGIN IMMEDIATE")
        try:
            claimed = [r[0] for r in conn.execute(
                f"SELECT url FROM jobs WHERE url IN ({placeholders}) AND whatsapp_notified_at IS NULL", urls)]
            if claimed:
                conn.execute(sql, [stamp, *claimed])
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    order = {u: i for i, u in enumerate(urls)}
    return sorted(claimed, key=order.__getitem__)


def release_claim(conn: sqlite3.Connection, urls: list[str], stamp: str) -> None:
    """Undo only this call's claim (rows still carrying its exact stamp)."""
    if not urls:
        return
    placeholders = ", ".join("?" for _ in urls)
    conn.execute(
        f"UPDATE jobs SET whatsapp_notified_at = NULL WHERE url IN ({placeholders}) AND whatsapp_notified_at = ?",
        [*urls, stamp],
    )
    conn.commit()


UNCERTAIN_FILE = "notify_uncertain.json"


def _uncertain_path() -> Path:
    import jobwright.config as config

    return Path(config.LOG_DIR) / UNCERTAIN_FILE


def read_uncertain() -> list[dict]:
    try:
        data = json.loads(_uncertain_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def record_uncertain(urls: list[str], stamp: str, error: str) -> None:
    path = _uncertain_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entries = [*read_uncertain(), {"at": stamp, "urls": urls, "error": error[:300]}][-20:]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    tmp.replace(path)


def release_uncertain(conn: sqlite3.Connection | None = None) -> int:
    """Operator confirmed an uncertain send never arrived: unmark those jobs for the next notify."""
    from jobwright.database import get_connection

    conn = conn or get_connection()
    n = 0
    for entry in read_uncertain():
        urls = [str(u) for u in entry.get("urls") or []]
        if not urls:
            continue
        placeholders = ", ".join("?" for _ in urls)
        n += max(conn.execute(
            f"UPDATE jobs SET whatsapp_notified_at = NULL WHERE url IN ({placeholders}) "
            f"AND whatsapp_notified_at = ?", [*urls, entry.get("at")],
        ).rowcount, 0)
    conn.commit()
    _uncertain_path().unlink(missing_ok=True)
    return n


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
        raise SendUncertain(f"hermes send timed out after {HERMES_SEND_TIMEOUT}s (may have been delivered)") from exc
    except FileNotFoundError as exc:
        raise RuntimeError("hermes CLI not found on PATH") from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"hermes send failed (exit {result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


FOLLOWUP_NOTICE_FILE = "followup_notice.json"


def _followup_notice_path():
    from pathlib import Path

    import jobwright.config as config

    return Path(config.LOG_DIR) / FOLLOWUP_NOTICE_FILE


def _last_followup_notice() -> set[str]:
    import json

    try:
        data = json.loads(_followup_notice_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(j) for j in (data.get("job_ids") or [])}


def _write_followup_notice(job_ids: list[str]) -> None:
    import json

    path = _followup_notice_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at": datetime.now().astimezone().isoformat(), "job_ids": job_ids}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


def build_paused_followups_notification(followups: list[dict], base_url: str) -> str:
    """Follow-up-only message for a profile whose new-job search is paused."""
    return (format_followups(followups, base_url) + "\n\n"
            + italic("New job search is paused. Turn it back on in Settings when you are ready."))


def _run_paused_notify(conn, dry_run: bool, active: str | None) -> dict:
    """Search paused: no job list; send due follow-ups only when something new is due."""
    followups = followup_appendix(conn)
    if not followups:
        return {"sent": 0, "skipped": True, "reason": "search paused; no follow-ups due",
                "jobs": [], "paused": True}
    ids = [f["job_id"] for f in followups]
    previous = _last_followup_notice()
    if previous and set(ids) <= previous:
        return {"sent": 0, "skipped": True, "reason": "search paused; follow-ups already sent",
                "jobs": [], "paused": True}
    message = build_paused_followups_notification(followups, public_base_url())
    if dry_run:
        return {"sent": 0, "skipped": False, "dry_run": True, "message": message, "jobs": [],
                "followups": len(followups), "paused": True}
    user = get_user(active) if active else None
    target = user.whatsapp_target if user else ""
    if not target:
        raise ValueError(
            f"No whatsapp_target configured for active user '{active}'. "
            f"Set one with: jobwright users set {active or '<id>'} --whatsapp <target>"
        )
    # Mark first, then send; restore the previous marker if delivery fails.
    _write_followup_notice(ids)
    try:
        send_via_hermes(message, target)
    except SendUncertain:
        raise  # may have arrived: keep the marker so it is not sent again
    except Exception:
        _write_followup_notice(sorted(previous))
        raise
    return {"sent": 0, "skipped": False, "message": message, "jobs": [],
            "followups": len(followups), "paused": True}


def run_notify(dry_run: bool = False, respect_pause: bool = True) -> dict:
    """Notify under the per-profile notify lock (see ``_run_notify``)."""
    from jobwright.hermes_cron import hermes_dry_run

    if dry_run or hermes_dry_run():
        return _run_notify(dry_run=True, respect_pause=respect_pause)
    try:
        with notify_lock():
            return _run_notify(dry_run=False, respect_pause=respect_pause)
    except NotifyBusy as exc:
        return {"sent": 0, "skipped": True, "reason": str(exc), "jobs": [], "busy": True}


def _run_notify(dry_run: bool = False, respect_pause: bool = True) -> dict:
    """Notify the active user of newly prepared jobs via WhatsApp.

    Respects the user's ``human_gate`` (review-first format) and
    ``brief_top_n`` (cap on the notify list; 0 = uncapped). Before sending, a
    brief_items snapshot is recorded for the scoreboard. Skips silently (no
    send) when there are no new prepare jobs. When not a dry run, sends the
    message then marks only the jobs that were actually shown so they are not
    re-sent.

    When the search is paused (and ``respect_pause``; the dashboard's explicit
    Send now passes False) only due follow-ups are sent.

    Raises:
        ValueError: The active user has no whatsapp_target configured.
        SendUncertain: hermes timed out; the claim is kept (see module doc).
    """
    from jobwright.database import get_connection

    ensure_brief_items()
    conn = get_connection()
    active = get_active_user_id()
    if respect_pause and not is_search_enabled(active):
        return _run_paused_notify(conn, dry_run, active)
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
        message += "\n\n" + worth_a_look_line(worth, base_url)
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

    # Claim first, then send. Only rows this call claimed are sent (a racing
    # notify or dashboard Send now cannot double-send), and only those are
    # released if delivery fails. A crash in between loses a notice, never
    # repeats one.
    stamp = datetime.now(timezone.utc).isoformat()
    claimed = claim_for_notify(conn, shown_urls, stamp)
    if not claimed:
        return {"sent": 0, "skipped": True, "reason": "already sent by another notify", "jobs": []}
    if len(claimed) != len(shown_urls):
        keep = set(claimed)
        shown = [job for job in shown if job["url"] in keep]
        shown_urls = claimed
        message = (build_review_notification if human_gate else build_notification)(shown, base_url)
        if worth:
            message += "\n\n" + worth_a_look_line(worth, base_url)
        if followups:
            message += "\n\n" + format_followups(followups, base_url)
        job_summaries = [s for s in job_summaries if s["job_id"] in {job_id_for_url(u) for u in claimed}]
    try:
        send_via_hermes(message, target)
    except SendUncertain as exc:
        record_uncertain(claimed, stamp, str(exc))
        raise
    except Exception:
        release_claim(conn, claimed, stamp)
        raise
    # Snapshot after a successful send so items never delivered are not counted
    # as precision data.
    record_brief_items(jobs, shown_urls)

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