"""Daily automatic applications with a veto window (``apply_picks`` table).

Flow (``apply_mode: veto``, the default for the first weeks):

1. ``pick``: after the brief, choose up to ``apply_daily_cap`` jobs scoring at
   least ``apply_min_score`` from the board (Backlog / Prepare, not touched by
   the person, never LinkedIn, never a vetoed or already-picked job, at most one
   per employer), store them as ``planned`` with ``apply_after = now +
   apply_veto_minutes`` and post them to the person's WhatsApp group: "I'll
   apply to these at 9:30 AM unless you reply skip <n> / skip all".
2. ``veto``: "skip 2" / "skip all" (the group's Hermes agent runs
   ``jobwright --user <id> apply veto --number 2`` / ``apply veto all``), the
   dashboard button, or ``POST /api/apply/picks/{id}/veto``. Refused once
   ``apply_after`` has passed.
3. ``due``: applies every planned pick whose ``apply_after`` has passed
   (tailoring materials first if missing), then posts "Applied today" with
   the confirmation screenshots and evidence links.

``apply_mode: auto`` applies right after picking (``apply auto`` = pick + due).
No cron is installed by this module; see docs/agents/auto-apply.md.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from jobwright import config
from jobwright.apply import safety
from jobwright.database import ANTI_CLOBBER_SQL, MANUAL_SOURCE_EXCLUSION_SQL, get_connection

log = logging.getLogger(__name__)

OPEN_PICK_STATUSES = ("planned", "running")
# A job picked once with these statuses is never picked again automatically.
NO_REPICK_STATUSES = ("planned", "running", "vetoed", "applied")


class VetoError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _user(user_id: str | None):
    from jobwright.users import get_user

    return get_user(user_id) if user_id else None


def _dashboard_url() -> str:
    from jobwright.notify import DEFAULT_BASE_URL

    return os.environ.get("JOBWRIGHT_PUBLIC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def _clock(iso: str) -> str:
    dt = datetime.fromisoformat(iso).astimezone()
    return dt.strftime("%-I:%M %p")


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def candidates(user_id: str | None, limit: int, min_score: int | None = None, conn=None) -> list[dict]:
    """Best eligible jobs, at most one per employer, safety gates applied."""
    from jobwright.config import is_manual_ats

    conn = conn or get_connection()
    user = _user(user_id)
    threshold = min_score if min_score is not None else (user.apply_min_score if user else 8)
    rows = conn.execute(
        f"""
        SELECT * FROM jobs
        WHERE applied_at IS NULL
          AND (apply_status IS NULL OR (apply_status = 'failed' AND COALESCE(apply_attempts, 0) < ?))
          AND COALESCE(user_fit_score, fit_score) >= ?
          AND COALESCE(funnel_stage, 'backlog') IN ('backlog', 'prepare')
          AND url NOT IN (SELECT job_url FROM apply_picks WHERE status IN ({','.join('?' * len(NO_REPICK_STATUSES))}))
          {ANTI_CLOBBER_SQL}{MANUAL_SOURCE_EXCLUSION_SQL}
        ORDER BY COALESCE(user_fit_score, fit_score) DESC, fit_score DESC, discovered_at DESC
        LIMIT 200
        """,
        (config.DEFAULTS["max_apply_attempts"], threshold, *NO_REPICK_STATUSES),
    ).fetchall()
    out: list[dict] = []
    employers: set[str] = set()
    for row in rows:
        job = dict(row)
        apply_url = job.get("application_url") or job["url"]
        if is_manual_ats(apply_url):
            continue
        gate = safety.check_job(job, user_id, live=True, min_score=threshold)
        if not gate.ok:
            continue
        emp = safety.employer_key(job.get("company") or job.get("site"))
        if emp and emp in employers:
            continue
        employers.add(emp)
        out.append(job)
        if len(out) >= limit:
            break
    return out


def _planned_today(conn) -> int:
    start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    row = conn.execute(
        "SELECT COUNT(*) FROM apply_picks WHERE status IN ('planned', 'running') AND picked_at >= ?",
        (_iso(start.astimezone(timezone.utc)),),
    ).fetchone()
    return int(row[0])


def pick(user_id: str | None, *, post: bool = True, now: datetime | None = None, conn=None) -> dict:
    """Choose today's picks and (veto mode) post them. Returns {picks, reasons}."""
    conn = conn or get_connection()
    user = _user(user_id)
    gate = safety.check_profile(user_id, live=True)
    if not gate.ok:
        return {"picks": [], "reasons": gate.reasons}
    room = user.apply_daily_cap - safety.live_submissions_today(conn) - _planned_today(conn)
    if room <= 0:
        return {"picks": [], "reasons": ["today's picks are already made"]}
    jobs = candidates(user_id, room, conn=conn)
    if not jobs:
        return {"picks": [], "reasons": [f"no eligible job scores {user.apply_min_score}+ right now"]}
    now = now or _now()
    minutes = 0 if user.apply_mode == "auto" else user.apply_veto_minutes
    apply_after = _iso(now + timedelta(minutes=minutes))
    batch = now.astimezone().strftime("%Y-%m-%d") + f"#{int(now.timestamp())}"
    picks = []
    for n, job in enumerate(jobs, start=1):
        cur = conn.execute(
            "INSERT INTO apply_picks (batch, number, job_url, job_id, title, company, score, picked_at, "
            "apply_after, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'planned')",
            (batch, n, job["url"], job.get("job_id"), job.get("title"), job.get("company") or job.get("site"),
             safety.effective_score(job), _iso(now), apply_after),
        )
        picks.append(get_pick(int(cur.lastrowid), conn))
    conn.commit()
    if post and user.apply_mode == "veto":
        _send(user_id, render_picks_message(picks))
    return {"picks": picks, "reasons": []}


def get_pick(pick_id: int, conn=None) -> dict | None:
    conn = conn or get_connection()
    row = conn.execute("SELECT * FROM apply_picks WHERE id = ?", (pick_id,)).fetchone()
    return dict(row) if row else None


def list_picks(conn=None, status: str | None = None, limit: int = 30) -> list[dict]:
    conn = conn or get_connection()
    if status:
        rows = conn.execute("SELECT * FROM apply_picks WHERE status = ? ORDER BY id DESC LIMIT ?",
                            (status, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM apply_picks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def picks_for_job(job_url: str, conn=None) -> list[dict]:
    conn = conn or get_connection()
    return [dict(r) for r in conn.execute(
        "SELECT * FROM apply_picks WHERE job_url = ? ORDER BY id DESC", (job_url,)).fetchall()]


def render_picks_message(picks: list[dict]) -> str:
    from jobwright.whatsapp import bold, italic

    when = _clock(picks[0]["apply_after"])
    lines = [f"🤖 {bold('Applying for you today')}", f"I'll apply to these at {when} unless you reply:"]
    lines.append(italic("skip <number>") + " or " + italic("skip all"))
    lines.append("")
    base = _dashboard_url()
    for p in picks:
        link = f"{base}/jobs/{p['job_id']}" if p.get("job_id") else ""
        lines.append(f"{p['number']}. {bold(p.get('title') or 'Job')} @ {p.get('company') or ''} "
                     f"({p.get('score')}/10)")
        if link:
            lines.append(f"   {link}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Veto
# ---------------------------------------------------------------------------


def _latest_batch(conn) -> str | None:
    row = conn.execute("SELECT batch FROM apply_picks ORDER BY id DESC LIMIT 1").fetchone()
    return row["batch"] if row else None


def veto(target: str | int, *, by: str = "cli", number: bool = False, now: datetime | None = None,
         conn=None) -> list[dict]:
    """Veto one pick (id, or ``number`` in the latest batch) or ``all`` open picks.

    Refused (VetoError) for a pick that is not planned, or whose apply time
    has already passed.
    """
    conn = conn or get_connection()
    now_s = _iso(now or _now())
    if str(target).strip().lower() == "all":
        rows = conn.execute(
            "SELECT * FROM apply_picks WHERE status = 'planned' AND apply_after > ? ORDER BY id", (now_s,)
        ).fetchall()
        if not rows:
            raise VetoError("Nothing left to skip: no planned application is still waiting.")
    else:
        try:
            ident = int(str(target).strip())
        except ValueError as exc:
            raise VetoError(f"Not a pick: {target!r}") from exc
        if number:
            batch = _latest_batch(conn)
            row = conn.execute("SELECT * FROM apply_picks WHERE batch = ? AND number = ?",
                               (batch, ident)).fetchone() if batch else None
        else:
            row = conn.execute("SELECT * FROM apply_picks WHERE id = ?", (ident,)).fetchone()
        if row is None:
            raise VetoError(f"No pick {target}.")
        if row["status"] != "planned":
            raise VetoError(f"Too late: that application is already {row['status']}.")
        if row["apply_after"] <= now_s:
            raise VetoError("Too late: the apply time for that pick has passed.")
        rows = [row]
    ids = [r["id"] for r in rows]
    conn.executemany(
        "UPDATE apply_picks SET status = 'vetoed', vetoed_by = ?, vetoed_at = ? WHERE id = ? AND status = 'planned'",
        [(by, now_s, i) for i in ids],
    )
    conn.commit()
    return [get_pick(i, conn) for i in ids]


# ---------------------------------------------------------------------------
# Due: apply
# ---------------------------------------------------------------------------


def ensure_materials(job: dict, tailor_fn: Callable[[str], int] | None = None) -> dict | None:
    """Tailored resume + cover letter for the job (generated if missing)."""
    if job.get("tailored_resume_path") and job.get("cover_letter_path"):
        return job
    if tailor_fn is None:
        from jobwright.scoring.tailor import run_single_job_materials as tailor_fn  # noqa: N806
    rc = tailor_fn(job["url"])
    row = get_connection().execute("SELECT * FROM jobs WHERE url = ?", (job["url"],)).fetchone()
    if rc != 0 or row is None or not row["tailored_resume_path"]:
        return None
    return dict(row)


def due(
    user_id: str | None,
    *,
    now: datetime | None = None,
    apply_fn: Callable[..., object] | None = None,
    tailor_fn: Callable[[str], int] | None = None,
    report: bool = True,
    conn=None,
) -> list[dict]:
    """Apply every planned pick whose time has come. Returns the picks touched."""
    from jobwright.apply.runner import apply_job

    conn = conn or get_connection()
    apply_fn = apply_fn or apply_job
    now_s = _iso(now or _now())
    rows = conn.execute(
        "SELECT * FROM apply_picks WHERE status = 'planned' AND apply_after <= ? ORDER BY apply_after, id",
        (now_s,),
    ).fetchall()
    done: list[dict] = []
    for row in rows:
        claimed = conn.execute("UPDATE apply_picks SET status = 'running' WHERE id = ? AND status = 'planned'",
                               (row["id"],)).rowcount
        conn.commit()
        if not claimed:
            continue
        status, outcome, sub_id, note = "skipped", "skipped", None, None
        gate = safety.check_profile(user_id, live=True)
        if not gate.ok:
            # Paused / killed / capped: keep it (and the rest) planned for later.
            conn.execute("UPDATE apply_picks SET status = 'planned', note = ? WHERE id = ?",
                         ("; ".join(gate.reasons)[:300], row["id"]))
            conn.commit()
            break
        try:
            job_row = conn.execute("SELECT * FROM jobs WHERE url = ?", (row["job_url"],)).fetchone()
            if job_row is None:
                note = "job no longer on the board"
            else:
                job = ensure_materials(dict(job_row), tailor_fn)
                if job is None:
                    note = "could not prepare the resume and cover letter"
                else:
                    res = apply_fn(job, dry_run=False, user_id=user_id)
                    outcome = getattr(res, "outcome", "failed")
                    sub_id = getattr(res, "submission_id", None)
                    note = "; ".join(getattr(res, "reasons", []) or []) or None
                    status = ("applied" if outcome == "applied" else
                              "skipped" if outcome in ("skipped", "needs_answer") else "failed")
        except Exception as exc:  # noqa: BLE001
            log.exception("pick %s failed", row["id"])
            status, outcome, note = "failed", "error", str(exc)[:300]
        conn.execute("UPDATE apply_picks SET status = ?, outcome = ?, submission_id = ?, note = ? WHERE id = ?",
                     (status, outcome, sub_id, note, row["id"]))
        conn.commit()
        done.append(get_pick(row["id"], conn))
    if report and done:
        send_report(user_id, done, conn=conn)
    return done


def run_auto(user_id: str | None, *, post: bool = True, **kw) -> dict:
    """``apply auto``: pick (veto mode posts and stops; auto mode applies now)."""
    user = _user(user_id)
    result = pick(user_id, post=post)
    if user and user.apply_mode == "auto" and result["picks"]:
        result["applied"] = due(user_id, **kw)
    return result


def dry_run_auto(user_id: str | None, *, limit: int | None = None, apply_fn=None, tailor_fn=None) -> list[dict]:
    """Rehearsal: what ``auto`` would pick, run as dry runs now (no picks, no messages)."""
    from jobwright.apply.runner import apply_job

    user = _user(user_id)
    cap = limit if limit is not None else (user.apply_daily_cap if user else 1)
    out = []
    for job in candidates(user_id, cap):
        job = ensure_materials(job, tailor_fn)
        if job is None:
            continue
        res = (apply_fn or apply_job)(job, dry_run=True, user_id=user_id)
        out.append(res.as_dict() if hasattr(res, "as_dict") else dict(res))
    return out


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

_LABEL = {
    "applied": "applied ✅",
    "unverified": "sent, but no confirmation page seen ⚠️",
    "needs_answer": "skipped: needs your answer ❓",
    "captcha_timeout": "skipped: CAPTCHA not solved in time",
    "expired": "posting closed",
    "skipped": "skipped",
    "failed": "failed",
    "error": "failed",
    "blocked": "blocked by the site",
}


def render_report(picks: list[dict], submissions: dict[int, dict]) -> str:
    from jobwright.whatsapp import bold

    base = _dashboard_url()
    applied = sum(1 for p in picks if p.get("outcome") == "applied")
    lines = [f"📬 {bold('Applied today')}: {applied} of {len(picks)}"]
    for p in picks:
        sub = submissions.get(p.get("submission_id") or -1) or {}
        label = _LABEL.get(p.get("outcome") or "", p.get("outcome") or "")
        lines.append(f"{p['number']}. {bold(p.get('title') or 'Job')} @ {p.get('company') or ''}: {label}")
        if sub:
            lines.append(f"   Evidence: {base}/apply/submissions/{sub['id']}")
        if p.get("outcome") == "needs_answer" and sub.get("needs"):
            for need in sub["needs"][:3]:
                lines.append(f"   ❓ {need.get('prompt')}")
        elif p.get("note") and p.get("outcome") not in ("applied",):
            lines.append(f"   {p['note'][:160]}")
    return "\n".join(lines)


def _send(user_id: str | None, text: str) -> bool:
    from jobwright.notify import SendUncertain, send_via_hermes

    user = _user(user_id)
    if not user or not user.whatsapp_target:
        log.warning("No WhatsApp target for %s; message not sent", user_id)
        return False
    try:
        send_via_hermes(text, user.whatsapp_target)
        return True
    except SendUncertain:
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("WhatsApp send failed: %s", exc)
        return False


def media_enabled() -> bool:
    return os.environ.get("JOBWRIGHT_HERMES_MEDIA", "on").strip().lower() not in ("0", "off", "false", "no")


def send_report(user_id: str | None, picks: list[dict], conn=None) -> bool:
    """Text report, then one screenshot per applied job (hermes ``MEDIA:<path>``)."""
    from jobwright.apply.evidence import get_submission, submission_file

    subs = {}
    for p in picks:
        if p.get("submission_id"):
            s = get_submission(int(p["submission_id"]), conn)
            if s:
                subs[s["id"]] = s
    ok = _send(user_id, render_report(picks, subs))
    if ok and media_enabled():
        for p in picks:
            sid = p.get("submission_id")
            if not sid or p.get("outcome") not in ("applied", "unverified"):
                continue
            path: Path | None = submission_file(int(sid), "confirmation", conn) or submission_file(
                int(sid), "review", conn)
            if path:
                _send(user_id, f"{p.get('title') or 'Job'} @ {p.get('company') or ''} MEDIA:{path}")
    return ok
