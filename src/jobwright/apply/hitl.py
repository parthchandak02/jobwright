"""Human-in-the-loop requests for apply runs (``pending_inputs`` table).

Three kinds:

- ``captcha``: the run found a CAPTCHA. It keeps the browser open (up to
  ``JOBWRIGHT_APPLY_WAIT_MINUTES``, default 20), posts a "finish this one" link
  to the dashboard page ``/apply/pending/<id>`` (live screenshot + "I solved
  it"), and waits. jobwright never solves CAPTCHAs or calls a solving service.
- ``email_code``: the employer emailed the person a code. The run asks in the
  person's WhatsApp group ("please paste the code from <company>") and waits;
  the group's Hermes agent runs ``jobwright --user <id> apply provide <id> <code>``.
  jobwright never reads anyone's email. The code is handed to the waiting run
  through a 0600 file that the run deletes after reading; the table keeps only
  a hash.
- ``answer``: a required attestation (or other fact) is not in the answer
  bank. The job is skipped right away (no waiting); the question is posted so
  the person can reply, which saves the answer for this question and makes the
  job eligible again. The person's own Claude raises these too
  (``ask_questions``, connector tool ``ask_person``, ``asked_by = 'connector'``)
  with optional choices; the person answers them in Settings → About you (Application details).
  An answer is always saved for that exact question (custom answer) and, when
  the question maps to a standard answer key, to that key as well (always when
  Claude named the key, otherwise only when the key is still empty), so the
  next form with the same question fills itself.

Resolution: CLI ``apply provide``, ``POST /api/apply/pending/{id}/provide``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from jobwright import config
from jobwright.database import get_connection

log = logging.getLogger(__name__)

KINDS = ("captcha", "email_code", "answer")
DEFAULT_WAIT_MINUTES = 20
ANSWER_TTL_DAYS = 14
_ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o/1/l/i: typed from a phone


def wait_minutes() -> int:
    try:
        return max(1, min(120, int(os.environ.get("JOBWRIGHT_APPLY_WAIT_MINUTES", DEFAULT_WAIT_MINUTES))))
    except ValueError:
        return DEFAULT_WAIT_MINUTES


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _new_id() -> str:
    return "".join(secrets.choice(_ID_ALPHABET) for _ in range(8))


def inbox_dir() -> Path:
    d = Path(config.APP_DIR) / "apply-inbox"
    d.mkdir(parents=True, exist_ok=True)
    try:
        d.chmod(0o700)
    except OSError:
        pass
    return d


def live_screenshot_path(pending_id: str) -> Path:
    return inbox_dir() / f"{pending_id}.png"


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_pending(
    kind: str,
    prompt: str,
    *,
    job: dict | None = None,
    run_id: str | None = None,
    ttl: timedelta | None = None,
    question_key: str | None = None,
    choices: list[str] | None = None,
    key_explicit: bool = False,
    asked_by: str | None = None,
    conn=None,
) -> dict:
    if kind not in KINDS:
        raise ValueError(f"Unknown pending kind {kind!r}")
    conn = conn or get_connection()
    job = job or {}
    if ttl is None:
        ttl = timedelta(days=ANSWER_TTL_DAYS) if kind == "answer" else timedelta(minutes=wait_minutes())
    now = _now()
    row = {
        "id": _new_id(),
        "job_url": job.get("url"),
        "job_id": job.get("job_id"),
        "run_id": run_id,
        "company": job.get("company") or job.get("site") or "",
        "kind": kind,
        "prompt": prompt.strip()[:1000],
        "question_key": question_key,
        "status": "open",
        "created_at": _iso(now),
        "expires_at": _iso(now + ttl),
        "meta_json": json.dumps({"choices": [str(c)[:200] for c in (choices or [])][:20],
                                 "key_explicit": bool(key_explicit)}) if (choices or key_explicit) else None,
        "asked_by": asked_by,
    }
    if kind == "answer":
        # One open question per job + question text: don't ask twice.
        dup = conn.execute(
            "SELECT * FROM pending_inputs WHERE kind = 'answer' AND status = 'open' AND job_url IS ? AND prompt = ?",
            (row["job_url"], row["prompt"]),
        ).fetchone()
        if dup:
            return _public(dict(dup))
    conn.execute(
        "INSERT INTO pending_inputs (id, job_url, job_id, run_id, company, kind, prompt, question_key, status, "
        "created_at, expires_at, meta_json, asked_by) VALUES (:id, :job_url, :job_id, :run_id, :company, :kind, "
        ":prompt, :question_key, :status, :created_at, :expires_at, :meta_json, :asked_by)",
        row,
    )
    conn.commit()
    return _public(dict(row))


def get_pending(pending_id: str, conn=None) -> dict | None:
    conn = conn or get_connection()
    row = conn.execute("SELECT * FROM pending_inputs WHERE id = ?", (pending_id,)).fetchone()
    return _public(dict(row)) if row else None


def _meta(row: dict) -> dict:
    try:
        meta = json.loads(row.get("meta_json") or "{}")
    except ValueError:
        meta = {}
    return meta if isinstance(meta, dict) else {}


def _public(row: dict) -> dict:
    if row.get("kind") in ("email_code", "captcha"):
        row["resolved_value"] = None
    row["choices"] = [str(c) for c in (_meta(row).get("choices") or [])]
    row.pop("meta_json", None)
    return row


def expire_stale(conn=None) -> int:
    conn = conn or get_connection()
    cur = conn.execute(
        "UPDATE pending_inputs SET status = 'expired' WHERE status = 'open' AND expires_at < ?", (_iso(_now()),)
    )
    conn.commit()
    return cur.rowcount


def list_pending(status: str | None = "open", conn=None, limit: int = 50) -> list[dict]:
    conn = conn or get_connection()
    expire_stale(conn)
    if status:
        rows = conn.execute(
            "SELECT * FROM pending_inputs WHERE status = ? ORDER BY created_at DESC LIMIT ?", (status, limit)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM pending_inputs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_public(dict(r)) for r in rows]


class ProvideError(ValueError):
    pass


def provide(pending_id: str, value: str, *, by: str = "cli", conn=None) -> dict:
    """Resolve an open request. Codes are handed to the waiting run, never stored."""
    conn = conn or get_connection()
    pending_id = (pending_id or "").strip().lower()
    row = conn.execute("SELECT * FROM pending_inputs WHERE id = ?", (pending_id,)).fetchone()
    if row is None:
        raise ProvideError(f"No request {pending_id!r}")
    row = dict(row)
    if row["status"] != "open":
        raise ProvideError(f"Request {pending_id} is already {row['status']}")
    if row["expires_at"] and row["expires_at"] < _iso(_now()):
        conn.execute("UPDATE pending_inputs SET status = 'expired' WHERE id = ?", (pending_id,))
        conn.commit()
        raise ProvideError(f"Request {pending_id} expired")
    value = (value or "").strip()
    kind = row["kind"]
    if kind == "captcha":
        value = value or "solved"
    if not value:
        raise ProvideError("Empty value")
    if kind == "email_code":
        if len(value) > 64:
            raise ProvideError("That does not look like a verification code")
        path = inbox_dir() / pending_id
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(value)
        stored = None
    elif kind == "captcha":
        stored = None
    else:
        stored = value[:2000]
        _save_answer(row, stored, by)
    conn.execute(
        "UPDATE pending_inputs SET status = 'resolved', resolved_at = ?, resolved_by = ?, resolved_value = ?, "
        "value_hash = ? WHERE id = ? AND status = 'open'",
        (_iso(_now()), by, stored, _hash(value), pending_id),
    )
    if kind == "answer" and row.get("job_url"):
        # Eligible again on the next auto run.
        conn.execute(
            "UPDATE jobs SET apply_status = NULL, apply_error = NULL WHERE url = ? AND apply_status = 'needs_answer'",
            (row["job_url"],),
        )
    conn.commit()
    return get_pending(pending_id, conn) or row


def _save_answer(row: dict, value: str, by: str) -> None:
    """The person's answer goes into the answer bank so the next form with this question fills itself."""
    from jobwright.apply import answers as answers_mod

    source = "whatsapp" if by in ("cli", "whatsapp") else ("settings" if by.startswith("dashboard") else "api")
    answers_mod.set_custom_answer(row["prompt"], value, source=source)
    key = row.get("question_key")
    if row.get("asked_by") != "connector" or key not in answers_mod.SPEC_BY_KEY:
        return
    if _meta(row).get("key_explicit") or answers_mod.load_answers().get(key) is None:
        answers_mod.set_answers({key: value}, source=source)


def ask_questions(questions: list[dict], *, job: dict, asked_by: str = "connector", conn=None) -> list[dict]:
    """Questions only the person can answer, raised by their Claude for one job (kind ``answer``).

    Each question is ``{"text", "choices"?, "key"?}``. ``key`` (a standard answer key) means Claude
    matched it to that answer; without it the keyword classifier's key is filled only when empty.
    Already-answered questions are returned with ``status = 'answered'`` and their saved value instead.
    """
    from jobwright.apply import answers as answers_mod

    conn = conn or get_connection()
    bank = answers_mod.load_answers()
    out: list[dict] = []
    for q in questions:
        text = " ".join(str(q.get("text") or "").split())[:500]
        if len(text) < 3:
            raise ValueError("Each question needs its text, word for word from the form")
        explicit = (q.get("key") or "").strip() or None
        if explicit and explicit not in answers_mod.SPEC_BY_KEY:
            raise ValueError(f"Unknown answer key {explicit!r}")
        key = explicit or answers_mod.key_for_question(text)
        choices = [" ".join(str(c).split()) for c in (q.get("choices") or []) if str(c).strip()]
        saved = bank.custom(text)
        if saved is None and explicit:
            saved = bank.get(explicit)
        if saved is not None:
            out.append({"question": text, "status": "answered", "value": saved})
            continue
        row = create_pending("answer", text, job=job, question_key=key, choices=choices,
                             key_explicit=bool(explicit), asked_by=asked_by, conn=conn)
        out.append({"question": text, "status": "asked", "id": row["id"], "choices": row.get("choices") or [],
                    "saves_to": key or "this exact question", "kind": answers_mod.question_kind(text)})
    return out


def answered_questions(conn=None, *, days: int = 30, limit: int = 50) -> list[dict]:
    """Recently answered ``answer`` requests (with the answer: the person gave it to be used)."""
    conn = conn or get_connection()
    since = _iso(_now() - timedelta(days=days))
    rows = conn.execute(
        "SELECT * FROM pending_inputs WHERE kind = 'answer' AND status = 'resolved' AND resolved_at >= ? "
        "ORDER BY resolved_at DESC LIMIT ?", (since, limit)).fetchall()
    return [_public(dict(r)) for r in rows]


def cancel(pending_id: str, conn=None) -> None:
    conn = conn or get_connection()
    conn.execute("UPDATE pending_inputs SET status = 'cancelled' WHERE id = ? AND status = 'open'", (pending_id,))
    conn.commit()


def wait_for(
    pending_id: str,
    *,
    timeout_s: float | None = None,
    poll_s: float = 2.0,
    on_tick: Callable[[], None] | None = None,
    conn=None,
    sleep: Callable[[float], None] = time.sleep,
) -> str | None:
    """Block until the request is resolved; return the value (None = timed out).

    ``on_tick`` runs every poll (the runner refreshes the live screenshot).
    """
    conn = conn or get_connection()
    deadline = time.monotonic() + (timeout_s if timeout_s is not None else wait_minutes() * 60)
    while True:
        row = conn.execute("SELECT status, kind FROM pending_inputs WHERE id = ?", (pending_id,)).fetchone()
        if row is None:
            return None
        if row["status"] == "resolved":
            if row["kind"] == "email_code":
                path = inbox_dir() / pending_id
                try:
                    value = path.read_text(encoding="utf-8").strip()
                finally:
                    try:
                        path.unlink()
                    except OSError:
                        pass
                return value
            got = conn.execute("SELECT resolved_value FROM pending_inputs WHERE id = ?", (pending_id,)).fetchone()
            return (got["resolved_value"] if got and got["resolved_value"] else "solved")
        if row["status"] != "open":
            return None
        if time.monotonic() >= deadline:
            conn.execute("UPDATE pending_inputs SET status = 'expired' WHERE id = ? AND status = 'open'",
                         (pending_id,))
            conn.commit()
            return None
        if on_tick:
            try:
                on_tick()
            except Exception:  # noqa: BLE001 - a screenshot failure must not end the wait
                log.debug("pending tick failed", exc_info=True)
        sleep(poll_s)
        # A fresh read each loop: provide() runs in another process.
        if conn.in_transaction:
            conn.commit()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def _dashboard_url() -> str:
    from jobwright.notify import DEFAULT_BASE_URL

    return os.environ.get("JOBWRIGHT_PUBLIC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def pending_link(pending_id: str) -> str:
    return f"{_dashboard_url()}/apply/pending/{pending_id}"


def render_message(row: dict, *, title: str = "") -> str:
    from jobwright.whatsapp import bold

    company = row.get("company") or "the employer"
    ref = row["id"]
    minutes = wait_minutes()
    if row["kind"] == "email_code":
        return (
            f"📩 Applying to {bold(company)}{f' ({title})' if title else ''}: they emailed you a verification code.\n"
            f"Please paste the code from {company} here (just the code). Ref {ref}.\n"
            f"I'll wait {minutes} minutes, then skip this one."
        )
    if row["kind"] == "captcha":
        return (
            f"🧩 The {bold(company)} application{f' ({title})' if title else ''} needs a quick human check (CAPTCHA).\n"
            f"Finish this one: {pending_link(ref)}\n"
            f"I'll keep it open {minutes} minutes. Ref {ref}."
        )
    return (
        f"❓ To apply to {bold(title or 'this job')} at {bold(company)} I need your answer to:\n"
        f"“{row['prompt']}”\n"
        f"Reply with your answer (ref {ref}), or save it in Settings → Application answers. "
        f"I skipped this job for now."
    )


def render_questions(rows: list[dict], *, title: str = "") -> str:
    from jobwright.whatsapp import bold

    company = (rows[0].get("company") if rows else "") or "the employer"
    lines = [f"❓ Your Claude is applying to {bold(title or 'a job')} at {bold(company)} and needs your answer:"]
    for r in rows:
        choices = f" ({' / '.join(r.get('choices') or [])})" if r.get("choices") else ""
        lines.append(f"• “{r['prompt']}”{choices} (ref {r['id']})")
    lines.append(f"Reply with the ref and your answer, or answer in Settings → About you: {_dashboard_url()}"
                 "/profile?tab=about#application-details. I'll remember it for every application after this.")
    return "\n".join(lines)


def notify_questions(rows: list[dict], user_id: str | None, *, title: str = "") -> bool:
    """One WhatsApp message for several questions from the person's Claude (no-op without a chat)."""
    from jobwright.notify import SendUncertain, send_via_hermes
    from jobwright.users import get_user

    rows = [r for r in rows if r.get("id") and not r.get("notified_at")]
    user = get_user(user_id) if user_id else None
    if not rows or not (user and user.whatsapp_target):
        return False
    try:
        send_via_hermes(render_questions(rows, title=title), user.whatsapp_target)
    except SendUncertain:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("Posting questions failed: %s", exc)
        return False
    conn = get_connection()
    for r in rows:
        conn.execute("UPDATE pending_inputs SET notified_at = ? WHERE id = ?", (_iso(_now()), r["id"]))
    conn.commit()
    return True


def notify(row: dict, user_id: str | None, *, title: str = "") -> bool:
    """Post the request to the person's WhatsApp group (no-op in Hermes dry run)."""
    from jobwright.notify import SendUncertain, send_via_hermes
    from jobwright.users import get_user

    user = get_user(user_id) if user_id else None
    targets = []
    if user and user.whatsapp_target:
        targets.append(user.whatsapp_target)
    if row["kind"] == "captcha":
        # Only the operator can reach the Mac mini's browser window.
        from jobwright.users import load_registry

        ops = str(load_registry().get("ops_target") or os.environ.get("JOBWRIGHT_OPS_TARGET") or "").strip()
        if ops and ops not in targets:
            targets.append(ops)
    if not targets:
        log.warning("No WhatsApp target for %s; pending %s not posted", user_id, row["id"])
        return False
    text = render_message(row, title=title)
    sent = False
    for target in targets:
        try:
            send_via_hermes(text, target)
            sent = True
        except SendUncertain:
            sent = True
        except Exception as exc:  # noqa: BLE001
            log.warning("Posting pending %s failed: %s", row["id"], exc)
    if sent:
        conn = get_connection()
        conn.execute("UPDATE pending_inputs SET notified_at = ? WHERE id = ?", (_iso(_now()), row["id"]))
        conn.commit()
    return sent
