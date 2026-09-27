"""Weekly WhatsApp summary per user (``jobwright summary``, Sunday cron).

One short message: jobs found, sent, applied, moved forward, closed, the top
three open jobs worth a look and any due follow-ups. Mark-then-send like
notify: ``logs/weekly_summary.json`` is stamped before delivery and restored
if delivery fails, so a crash can only lose a summary, never repeat one.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta

from jobwright import config
from jobwright.database import get_connection, job_id_for_url
from jobwright.followups import format_followups
from jobwright.notify import MAX_FOLLOWUPS, _notify_threshold, followup_appendix, public_base_url, send_via_hermes
from jobwright.users import get_user, list_users

TOP_OPEN = 3
TOP_OPEN_MAX_AGE_DAYS = 30
STATE_FILE = "weekly_summary.json"


def _count(conn: sqlite3.Connection, sql: str, params: tuple) -> int:
    return int(conn.execute(sql, params).fetchone()[0] or 0)


_STILL_AT = {
    "applied": ("applied", "in_progress", "offer"),
    "in_progress": ("in_progress", "offer"),
    "offer": ("offer",),
    "closed": ("closed",),
}


def _moved(conn: sqlite3.Connection, stages: tuple[str, ...], since: str, human_only: bool = False) -> int:
    """Jobs moved into ``stages`` since ``since`` that are still there (or further along)."""
    marks = ", ".join("?" for _ in stages)
    current = sorted({s for st in stages for s in _STILL_AT.get(st, (st,))})
    cur_marks = ", ".join("?" for _ in current)
    actor = " AND h.actor = 'human'" if human_only else ""
    return _count(
        conn,
        f"SELECT COUNT(DISTINCT h.job_url) FROM stage_history h JOIN jobs j ON j.url = h.job_url "
        f"WHERE h.to_stage IN ({marks}) AND h.at >= ?{actor} "
        f"AND COALESCE(j.funnel_stage, 'backlog') IN ({cur_marks})",
        (*stages, since, *current),
    )


def top_open_jobs(conn: sqlite3.Connection, threshold: int, now: datetime, limit: int = TOP_OPEN) -> list[dict]:
    since = (now - timedelta(days=TOP_OPEN_MAX_AGE_DAYS)).isoformat()
    rows = conn.execute(
        "SELECT url, job_id, title, company, COALESCE(user_fit_score, fit_score) AS score FROM jobs "
        "WHERE COALESCE(funnel_stage, 'backlog') IN ('backlog', 'prepare') "
        "AND COALESCE(user_fit_score, fit_score) >= ? AND discovered_at >= ? "
        "ORDER BY score DESC, COALESCE(score_confidence, 0) DESC, discovered_at DESC LIMIT ?",
        (int(threshold), since, limit),
    ).fetchall()
    return [
        {
            "job_id": r["job_id"] or job_id_for_url(r["url"]),
            "title": r["title"] or "Untitled role",
            "company": r["company"] or "Unknown",
            "score": r["score"],
        }
        for r in rows
    ]


def collect(conn: sqlite3.Connection, days: int = 7, now: datetime | None = None) -> dict:
    """Numbers for the last ``days`` days from the active user's DB."""
    now = now or datetime.now(UTC)
    since = (now - timedelta(days=days)).isoformat()
    try:
        threshold = _notify_threshold()
    except Exception:
        threshold = 7
    return {
        "days": days,
        "start": (now - timedelta(days=days)).date().isoformat(),
        "end": now.date().isoformat(),
        "found": _count(conn, "SELECT COUNT(*) FROM jobs WHERE discovered_at >= ?", (since,)),
        "sent": _count(conn, "SELECT COUNT(*) FROM jobs WHERE whatsapp_notified_at >= ?", (since,)),
        "applied": _moved(conn, ("applied",), since),
        "in_progress": _moved(conn, ("in_progress",), since),
        "offer": _moved(conn, ("offer",), since),
        "closed": _moved(conn, ("closed",), since, human_only=True),
        "top": top_open_jobs(conn, threshold, now),
        "followups": followup_appendix(conn, limit=MAX_FOLLOWUPS),
    }


def _plural(n: int, word: str, plural: str | None = None) -> str:
    return f"{n} {word if n == 1 else (plural or word + 's')}"


def _date_label(iso: str) -> str:
    d = datetime.fromisoformat(iso)
    return f"{d:%b} {d.day}"


def has_news(stats: dict) -> bool:
    keys = ("found", "sent", "applied", "in_progress", "offer", "closed")
    return any(stats.get(k) for k in keys) or bool(stats.get("top") or stats.get("followups"))


def build_summary(stats: dict, base_url: str, name: str = "") -> str:
    """Plain-text WhatsApp message (no markdown)."""
    base_url = base_url.rstrip("/")
    first = (name or "").split()[0] if (name or "").strip() else ""
    greeting = f"Hi {first}, here" if first else "Here"
    lines = [f"{greeting} is your job search week ({_date_label(stats['start'])} to {_date_label(stats['end'])}):", ""]
    rows = [
        (stats["found"], _plural(stats["found"], "new job") + " found"),
        (stats["sent"], _plural(stats["sent"], "job") + " sent to you"),
        (stats["applied"], f"{stats['applied']} applied"),
        (stats["in_progress"], _plural(stats["in_progress"], "job") + " moved to interviews"),
        (stats["offer"], _plural(stats["offer"], "offer")),
        (stats["closed"], f"{stats['closed']} closed"),
    ]
    shown = [text for n, text in rows if n]
    lines.extend(f"• {text}" for text in shown or ["A quiet week, nothing new moved."])
    if stats.get("top"):
        lines.extend(["", "Worth a look:"])
        for job in stats["top"]:
            lines.append(f"• {job['title']} @ {job['company']} · score {job['score']}")
            lines.append(f"  {base_url}/jobs/{job['job_id']}")
    if stats.get("followups"):
        lines.extend(["", format_followups(stats["followups"], base_url)])
    lines.extend(["", f"Your board: {base_url}/"])
    return "\n".join(lines)


def _state_path():
    return config.LOG_DIR / STATE_FILE


def _read_state() -> dict:
    try:
        return json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_state(state: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def run_summary(dry_run: bool = False, days: int = 7, force: bool = False) -> dict:
    """Build and send the weekly summary for the active user."""
    uid = config.get_active_user_id()
    user = get_user(uid) if uid else None
    result: dict = {"user": uid, "sent": False}
    if user and not user.weekly_summary and not dry_run:
        return {**result, "skipped": True, "reason": "opted out"}
    now = datetime.now(UTC)
    previous = _read_state()
    last = previous.get("last_sent_at")
    if last and not force and not dry_run:
        try:
            if now - datetime.fromisoformat(last) < timedelta(days=max(days - 1, 1)):
                return {**result, "skipped": True, "reason": f"already sent {last[:10]}"}
        except ValueError:
            pass

    conn = get_connection()
    stats = collect(conn, days, now)
    if not has_news(stats):
        return {**result, "skipped": True, "reason": "nothing to report", "stats": stats}
    message = build_summary(stats, public_base_url(), user.name if user else "")
    result.update(message=message, stats=stats)
    if dry_run:
        return {**result, "dry_run": True}

    target = user.whatsapp_target if user else ""
    if not target:
        return {**result, "skipped": True, "reason": "no WhatsApp chat set"}
    _write_state({**previous, "last_sent_at": now.isoformat(), "days": days})
    try:
        send_via_hermes(message, target)
    except Exception:
        _write_state(previous)
        raise
    return {**result, "sent": True}


def run_summary_all(
    user_ids: list[str] | None = None, dry_run: bool = False, days: int = 7, force: bool = False,
) -> list[dict]:
    """Run the summary for each profile (default: every user in users.yaml)."""
    from jobwright.database import init_db

    results = []
    for u in list_users():
        if user_ids and u.user_id not in user_ids:
            continue
        with config.user_context(u.user_id):
            if not config.DB_PATH.exists():
                results.append({"user": u.user_id, "sent": False, "skipped": True, "reason": "no database yet"})
                continue
            try:
                init_db()
                results.append(run_summary(dry_run=dry_run, days=days, force=force))
            except Exception as exc:
                results.append({"user": u.user_id, "sent": False, "error": str(exc)})
    return results
