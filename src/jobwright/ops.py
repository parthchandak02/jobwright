"""Operator health: per-brief report, missed-run watchdog, alert delivery.

Silence used to look the same as "no jobs today". Now every brief ends with a
report; anything abnormal (preflight failure, a nonzero pipeline exit, a run
that never wrote its own summary, a locked or timed-out run, a failed stage, a
broken or rate-limited discovery source, zero scored jobs, notify failure) is
sent to the operator's WhatsApp target (``ops_target`` in users.yaml, or
JOBWRIGHT_OPS_TARGET). When Hermes cannot deliver it, the alert goes out on a
fallback channel that does not depend on Hermes (JOBWRIGHT_OPS_FALLBACK:
macOS notification and/or an ntfy topic).

A watchdog run (hourly Hermes cron) alerts once per day when a user's brief
never started, is still running, or never finished today, and retries a failed
notify once the WhatsApp bridge is healthy again (at most
JOBWRIGHT_NOTIFY_RETRIES per day). Profiles with the new-job search paused
(``search_enabled: false``) are intentionally quiet and never alerted.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

import jobwright.config as config

log = logging.getLogger(__name__)


@dataclass
class Report:
    user: str
    level: str  # ok | warn | fail
    lines: list[str] = field(default_factory=list)
    key: str = ""  # watchdog problem kind, for once-a-day alert dedupe

    def text(self) -> str:
        icon = {"ok": "OK", "warn": "WARN", "fail": "FAIL"}[self.level]
        return f"[jobwright ops] {icon} brief for {self.user}\n" + "\n".join(f"- {line}" for line in self.lines)


def ops_target() -> str:
    from jobwright.users import load_registry

    env = os.environ.get("JOBWRIGHT_OPS_TARGET", "").strip()
    if env:
        return env
    return str(load_registry().get("ops_target") or "").strip()


def set_ops_target(target: str) -> str:
    from jobwright.users import _normalize_whatsapp_target, load_registry, save_registry

    data = load_registry()
    data["ops_target"] = _normalize_whatsapp_target(target) if target else ""
    save_registry(data)
    return data["ops_target"]


def _read_status(path: Path) -> list[str]:
    try:
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return []


def _parse_when(text: str | None) -> datetime | None:
    """ISO timestamp (``Z`` or offset) as an aware datetime; naive values are local time."""
    if not text:
        return None
    try:
        when = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.astimezone()


def status_started_at(status: list[str]) -> datetime | None:
    """When this brief run began: the last ``brief_started at=`` (else launcher ``started ... at=``) line."""
    found = None
    for prefix in ("started", "brief_started"):  # later wins: brief_started is the run itself
        for line in status:
            if line.split(" ", 1)[0] != prefix:
                continue
            for part in line.split():
                if part.startswith("at="):
                    found = _parse_when(part[3:]) or found
    return found


def _status_value(status: list[str], prefix: str) -> str:
    """Last line starting with ``prefix`` (``""`` if none)."""
    return next((s for s in reversed(status) if s.startswith(prefix)), "")


def last_notify_line(status: list[str]) -> str:
    """The latest notify outcome (``notify_sent`` / ``_skipped`` / ``_failed`` / ``_uncertain``)."""
    return next((s for s in reversed(status) if s.startswith("notify_") and not s.startswith("notify_retry")), "")


def _pipeline_rc(status: list[str]) -> int | None:
    line = _status_value(status, "pipeline_rc=")
    if not line:
        return None
    try:
        return int(line.split("=", 1)[1].split()[0])
    except (IndexError, ValueError):
        return None


def _fmt_age(when: datetime) -> str:
    secs = max(0, int((datetime.now(when.tzinfo) - when).total_seconds()))
    return f"{secs // 3600}h{(secs % 3600) // 60:02d}m" if secs >= 3600 else f"{secs // 60}m"


def _source_line(sources: dict) -> str:
    """One line: ``jobspy +12 (2 errors) · linkedin rate-limited 3 · impact +4 (1/11 boards failed: x)``."""
    parts: list[str] = []
    impact = {k.split(":", 1)[1]: v for k, v in sources.items() if k.startswith("impact:")}
    for name, src in sources.items():
        if name.startswith("impact:"):
            continue
        bits = [name]
        if "new" in src:
            bits.append(f"+{int(src.get('new') or 0)}")
        extra = []
        if str(src.get("status", "")).startswith("error"):
            extra.append("failed")
        elif src.get("errors"):
            extra.append(f"{src['errors']} errors")
        if src.get("rate_limited"):
            extra.append(f"rate-limited {src['rate_limited']}")
        parts.append(" ".join(bits) + (f" ({', '.join(extra)})" if extra else ""))
    if impact:
        failed = [n for n, v in impact.items() if v.get("errors")]
        line = f"impact +{sum(int(v.get('new') or 0) for v in impact.values())}"
        if failed:
            line += f" ({len(failed)}/{len(impact)} boards failed: {', '.join(failed[:4])})"
        parts.append(line)
    return "sources: " + " · ".join(parts)


def _source_warnings(sources: dict) -> list[str]:
    out = []
    for name, src in sources.items():
        errors, new = int(src.get("errors") or 0), src.get("new")
        if str(src.get("status", "")).startswith("error"):
            out.append(f"source {name} failed: {str(src['status'])[7:120]}")
        elif errors and new is not None and int(new or 0) == 0:
            out.append(f"source {name}: 0 new jobs with {errors} errors (broken or blocked?)")
        if src.get("rate_limited"):
            out.append(f"source {name}: rate-limited, gave up on {src['rate_limited']} request(s)")
    return out


def build_brief_report(status_file: Path | None = None) -> Report:
    """Today's brief, judged from its status file and its own run summary.

    The status file (``BRIEF_STATUS_<date>``) is the source of truth for what
    the launcher saw: ``preflight_failed``, ``pipeline_rc=N``,
    ``pipeline_locked``, ``timeout``, the notify outcome. ``logs/last_run.json``
    only counts if it was written by this run (started after the brief did, not
    a dashboard run); otherwise its errors and stages are ignored.
    """
    from jobwright.database import get_connection
    from jobwright.pipeline import lock_holder, read_run_summary
    from jobwright.users import is_search_enabled

    user = config.get_active_user_id() or "legacy"
    status_file = status_file or Path(config.APP_DIR) / f"BRIEF_STATUS_{datetime.now():%Y%m%d}"
    status = _read_status(status_file)
    # Paused search: the brief intentionally ran no stages, so last_run.json is
    # an older run and must not re-raise its errors or count as missing.
    paused = not is_search_enabled(config.get_active_user_id())
    rep = Report(user=user, level="ok")
    if paused:
        rep.lines.append("new job search paused by the person (no discovery today)")

    def bump(level: str) -> None:
        order = {"ok": 0, "warn": 1, "fail": 2}
        if order[level] > order[rep.level]:
            rep.level = level

    preflight_failed = any(s.startswith("preflight_failed") for s in status)
    locked = _status_value(status, "pipeline_locked")
    timed_out = _status_value(status, "timeout")
    rc = _pipeline_rc(status)
    started = status_started_at(status)

    summary = {} if paused else (read_run_summary() or {})
    stale_summary = None
    if summary and started is not None and not paused:
        run_start = _parse_when(summary.get("started_at"))
        if run_start is None or run_start < started - timedelta(seconds=5) or summary.get("web_run_id"):
            stale_summary = summary
            summary = {}

    if preflight_failed:
        bump("fail")
        rep.lines.append("preflight failed: pipeline did not run (see brief log)")
    if timed_out:
        bump("fail")
        rep.lines.append(f"brief killed at its deadline: {timed_out}")
    if locked:
        bump("warn")
        holder = lock_holder()
        rep.lines.append("pipeline skipped: another run held this profile's lock"
                         + (f" ({holder})" if holder else " (released since)"))
    elif rc is not None and rc != 0 and not timed_out:
        bump("fail")
        rep.lines.append(f"pipeline exited with code {rc}"
                         + (" (crashed before writing a run summary)" if not summary else ""))

    for stage, err in (summary.get("errors") or {}).items():
        bump("fail" if stage in ("discover", "score") else "warn")
        rep.lines.append(f"stage {stage}: {str(err)[:160]}")
    stages = {s.get("stage"): s for s in summary.get("stages") or []}

    discover = stages.get("discover")
    if discover:
        detail = discover.get("detail") or {}
        sources = detail.get("sources") or {}
        if sources:
            rep.lines.append(_source_line(sources))
            for warning in _source_warnings(sources):
                bump("warn")
                rep.lines.append(warning)
            total_errors = sum(int(v.get("errors") or 0) for v in sources.values())
            if int(detail.get("new") or 0) == 0 and total_errors:
                bump("warn")
                rep.lines.append(f"discover found 0 new jobs ({total_errors} source errors)")
        if str(discover.get("status")) == "partial":
            bump("warn")
            rep.lines.append("discover partial: some sources failed or were degraded")

    score = (stages.get("score") or {}).get("detail") or {}
    if "score" in stages:
        scored, errors = int(score.get("scored") or 0), int(score.get("errors") or 0)
        rep.lines.append(f"scored {scored} jobs ({errors} failed)")
        if errors and errors > max(3, scored * 0.1):
            bump("warn")
        if scored == 0:
            bump("warn")
            rep.lines.append("score ran but scored 0 jobs")
    enrich_stage = stages.get("enrich") or {}
    enrich = enrich_stage.get("detail") or {}
    if enrich.get("error"):
        rep.lines.append(f"enrich errors: {enrich.get('error')}")
    if enrich.get("budget_skipped"):
        bump("warn")
        rep.lines.append(f"enrich stopped at its time budget; {enrich['budget_skipped']} job(s) left for next run")
    over = [name for name, st in stages.items() if (st.get("detail") or {}).get("over_budget")]
    if over:
        bump("warn")
        rep.lines.append(f"over soft time budget: {', '.join(over)}")

    notify = last_notify_line(status)
    if notify.startswith("notify_failed"):
        bump("fail")
        rep.lines.append(notify.replace("_", " ", 1))
    elif notify.startswith("notify_uncertain"):
        bump("warn")
        rep.lines.append(notify.replace("_", " ", 1)
                         + " — check the chat; if nothing arrived run `ops release-uncertain`")
    elif notify:
        rep.lines.append(notify.replace("_", " ", 1))
    elif status:
        bump("warn")
        rep.lines.append("notify did not run")
    retries = [s for s in status if s.startswith("notify_retry")]
    if retries:
        rep.lines.append(f"{retries[-1]}")
    try:
        conn = get_connection()
        fresh = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE COALESCE(user_fit_score, fit_score) >= 7 "
            "AND discovered_at >= datetime('now', '-1 day')"
        ).fetchone()[0]
        rep.lines.append(f"{fresh} fresh jobs scored 7+ in the last 24h")
        cost = conn.execute(
            "SELECT COALESCE(SUM(prompt_tokens + completion_tokens), 0), SUM(cost_usd) FROM llm_usage "
            "WHERE at >= datetime('now', '-1 day')"
        ).fetchone()
        tokens_line = f"LLM tokens (24h): {int(cost[0]):,}"
        if cost[1] is not None:
            tokens_line += f" (~${cost[1]:.2f})"
        rep.lines.append(tokens_line)
    except Exception as exc:  # noqa: BLE001
        bump("warn")
        rep.lines.append(f"could not read DB stats: {exc}")
    pipeline_skipped = preflight_failed or bool(locked)
    if not summary and not paused and not pipeline_skipped:
        if stale_summary is not None:
            # Crashed before or during the run, or never ran: last_run.json is someone else's.
            bump("fail" if (rc or timed_out) else "warn")
            rep.lines.append(f"no fresh run summary (logs/last_run.json is from "
                             f"{stale_summary.get('started_at') or 'an unknown time'})")
        else:
            bump("warn")
            rep.lines.append("no run summary (logs/last_run.json) found")
    return rep


class Delivery(str):
    """deliver()'s human-readable outcome; ``.delivered`` is True when any channel took it."""

    delivered: bool = False


def _delivery(text: str, delivered: bool) -> Delivery:
    out = Delivery(text)
    out.delivered = delivered
    return out


def fallback_channels() -> list[str]:
    """Alert channels that do not depend on Hermes (JOBWRIGHT_OPS_FALLBACK).

    Comma-separated: ``macos`` (Notification Center via osascript), an ntfy
    topic URL (``https://ntfy.sh/<topic>`` or ``ntfy:<url>``), or ``off``.
    Unset means ``macos`` on macOS (local, needs no account or secret) and
    nothing elsewhere.
    """
    raw = os.environ.get("JOBWRIGHT_OPS_FALLBACK")
    if raw is None:
        return ["macos"] if sys.platform == "darwin" else []
    items = [x.strip() for x in raw.split(",") if x.strip()]
    if any(x.lower() in ("off", "none", "0", "false") for x in items):
        return []
    return items


def _notify_macos(title: str, body: str) -> None:
    # Text goes in as argv, never spliced into the script, so quotes cannot break it.
    script = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
              "-e", "end run"]
    proc = subprocess.run(["osascript", *script, title, body[:900]], capture_output=True, text=True,
                          timeout=15, check=False)
    if proc.returncode != 0:
        raise RuntimeError(f"osascript exit {proc.returncode}: {proc.stderr.strip()[:120]}")


def _notify_ntfy(url: str, title: str, body: str, level: str) -> None:
    import urllib.request

    headers = {"Title": title, "Priority": "high" if level == "fail" else "default", "Tags": "warning"}
    token = os.environ.get("JOBWRIGHT_OPS_NTFY_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body.encode("utf-8"), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310 - operator-configured URL
        if resp.status >= 300:
            raise RuntimeError(f"ntfy HTTP {resp.status}")


def send_fallback(report: Report) -> list[tuple[str, bool, str]]:
    """Send ``report`` on every fallback channel; [(channel, ok, detail)]."""
    title = f"jobwright ops {report.level.upper()}: {report.user}"
    body = "\n".join(report.lines) or report.level
    results = []
    for channel in fallback_channels():
        try:
            if channel.lower() == "macos":
                _notify_macos(title, body)
            elif channel.startswith(("http://", "https://", "ntfy:")):
                url = channel[5:] if channel.startswith("ntfy:") else channel
                _notify_ntfy(url, title, body, report.level)
            else:
                raise ValueError("unknown channel")
            results.append((channel, True, "sent"))
        except Exception as exc:  # noqa: BLE001
            log.warning("ops fallback %s failed: %s", channel, exc)
            results.append((channel, False, str(exc)[:120]))
    return results


def _fallback_suffix(results: list[tuple[str, bool, str]]) -> str:
    if not results:
        return ""
    shown = ", ".join(f"{_channel_name(c)} {'ok' if ok else 'failed'}" for c, ok, _ in results)
    return f"; fallback: {shown}"


def _channel_name(channel: str) -> str:
    return "macos" if channel.lower() == "macos" else "ntfy"


def deliver(report: Report, *, force: bool = False) -> Delivery:
    """Send to the ops target when not ok (or forced); fall back to non-Hermes channels on failure."""
    heartbeat = os.environ.get("JOBWRIGHT_OPS_HEARTBEAT", "").lower() in ("1", "true", "yes")
    if report.level == "ok" and not (force or heartbeat):
        return _delivery("ok (no alert)", False)
    target = ops_target()
    if not target:
        results = send_fallback(report) if report.level != "ok" else []
        return _delivery("no ops_target configured (alert logged only)" + _fallback_suffix(results),
                         any(ok for _, ok, _ in results))
    from jobwright.notify import send_via_hermes

    try:
        send_via_hermes(report.text(), target)
        return _delivery(f"sent to {target}", True)
    except Exception as exc:  # noqa: BLE001
        results = send_fallback(report) if report.level != "ok" else []
        return _delivery(f"alert delivery failed: {exc}" + _fallback_suffix(results),
                         any(ok for _, ok, _ in results))


def write_health(report: Report) -> Path:
    """Persist the latest report for the dashboard status banner."""
    path = Path(config.LOG_DIR) / "ops_health.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"at": datetime.now().astimezone().isoformat(), "level": report.level, "lines": report.lines}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def read_health() -> dict | None:
    try:
        return json.loads((Path(config.LOG_DIR) / "ops_health.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


_DOW_NAMES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
_MONTH_NAMES = {m: i for i, m in enumerate(
    ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def _cron_field_matches(field_expr: str, value: int, lo: int, hi: int, names: dict[str, int] | None = None) -> bool:
    """Does ``value`` match one cron field (``*``, ``a``, ``a-b``, ``*/n``, ``a-b/n``, lists, names)?"""
    def num(tok: str) -> int:
        tok = tok.strip().lower()
        return names[tok[:3]] if names and tok[:3] in names else int(tok)

    for part in field_expr.split(","):
        part = part.strip()
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            step = max(1, int(step_s))
        if part in ("*", ""):
            first, last = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            first, last = num(a), num(b)
        else:
            first = last = num(part)
            if step != 1:
                last = hi
        if first <= value <= last and (value - first) % step == 0:
            return True
    return False


def _cron_runs_today(expr: str, today: datetime) -> bool:
    parts = (expr or "").split()
    if len(parts) != 5:
        return True
    _, _, dom, month, dow = parts
    try:
        if not _cron_field_matches(month, today.month, 1, 12, _MONTH_NAMES):
            return False
        cron_dow = (today.weekday() + 1) % 7  # cron: 0 = Sunday (7 also Sunday)
        dow_ok = _cron_field_matches(dow, cron_dow, 0, 7, _DOW_NAMES) or (
            cron_dow == 0 and _cron_field_matches(dow, 7, 0, 7, _DOW_NAMES))
        dom_ok = _cron_field_matches(dom, today.day, 1, 31)
    except (ValueError, KeyError):
        return True  # unparseable: assume it runs (alerting beats silence)
    # Cron semantics: when both day fields are restricted, either may match.
    if dom.strip() != "*" and dow.strip() != "*":
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def _cron_clock_today(expr: str) -> datetime | None:
    """Today's run time for a once-a-day cron, or None (not today, or not a fixed daily time)."""
    parts = (expr or "").split()
    if len(parts) != 5 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    now = datetime.now()
    if not _cron_runs_today(expr, now):
        return None
    return now.replace(hour=int(parts[1]), minute=int(parts[0]), second=0, microsecond=0)


def brief_process(data_dir: Path) -> tuple[int, datetime] | None:
    """(pid, started) of a live run_daily_brief.sh for this profile, from BRIEF_PID; else None."""
    pid_file = data_dir / "BRIEF_PID"
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
        started = datetime.fromtimestamp(pid_file.stat().st_mtime)
    except (OSError, ValueError):
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        pass
    try:
        cmd = subprocess.run(["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True,
                             timeout=5, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        cmd = "run_daily_brief"  # cannot tell: trust the live pid
    if "run_daily_brief" not in cmd:
        return None  # pid reused by something else
    return pid, started


def _hours(delta: timedelta) -> str:
    return f"{delta.total_seconds() / 3600:.1f}h"


def watchdog(grace_minutes: int = 120, start_grace_minutes: int = 30) -> list[Report]:
    """Alert for every user whose brief never started, or should have finished by now but did not.

    The launcher writes the status file within seconds, so a missing file is
    flagged after ``start_grace_minutes``; an unfinished run after ``grace_minutes``.
    A brief whose process is still alive (e.g. yesterday's run past midnight,
    which makes the launcher skip today's) is reported as still running, and a
    run killed at its deadline as timed out, never as "no brief started".
    """
    from jobwright.users import list_users

    reports: list[Report] = []
    now = datetime.now()
    for user in list_users():
        start = _cron_clock_today(user.schedule)
        if start is None or now < start + timedelta(minutes=start_grace_minutes):
            continue
        if not _is_set_up(user.user_id):
            continue  # setup unfinished: no brief is expected yet
        if not user.search_enabled:
            continue  # the person paused the search on purpose; nothing is missed
        data_dir = user.resolve_data_dir()
        status_path = data_dir / f"BRIEF_STATUS_{now:%Y%m%d}"
        status = _read_status(status_path)
        running = brief_process(data_dir)
        if not status:
            if running:
                pid, since = running
                reports.append(Report(user.user_id, "fail", [
                    f"brief still running for {_hours(now - since)} (pid {pid}, started {since:%a %H:%M}); "
                    f"today's brief (scheduled {user.schedule}) did not start because of it"],
                    key="still_running"))
            else:
                reports.append(Report(user.user_id, "fail", [f"no brief started today (scheduled {user.schedule})"],
                                      key="not_started"))
            continue
        timeout = _status_value(status, "timeout")
        if timeout:
            reports.append(Report(user.user_id, "fail", [f"brief timed out: {timeout}", *status[-3:]],
                                  key="timed_out"))
            continue
        # A late manual rerun counts from when it started; the file is not touched again until it ends.
        started = max(start, datetime.fromtimestamp(status_path.stat().st_mtime))
        if now >= started + timedelta(minutes=grace_minutes) and not any(s.startswith("done") for s in status):
            if running:
                lines = [f"brief still running for {_hours(now - running[1])} (pid {running[0]})", *status[-3:]]
            else:
                lines = ["brief started but has not finished (process gone: crashed or killed)", *status[-3:]]
            reports.append(Report(user.user_id, "fail", lines, key="not_finished"))
    return reports


# ---------------------------------------------------------------------------
# Notify retry (watchdog)
# ---------------------------------------------------------------------------

def notify_retry_limit() -> int:
    try:
        return max(0, int(os.environ.get("JOBWRIGHT_NOTIFY_RETRIES", "3")))
    except ValueError:
        return 3


def notify_needs_retry(status: list[str]) -> bool:
    """Today's brief finished but its WhatsApp list did not go out.

    True when the last notify outcome is ``notify_failed``, or when the run
    finished (``done``) with no notify outcome at all after a pipeline that
    ran. Never for ``notify_uncertain`` (it may have arrived) or a brief that is
    still running.
    """
    if not status or not any(s.startswith("done") for s in status):
        return False
    last = last_notify_line(status)
    if last.startswith("notify_failed"):
        return True
    if last:
        return False
    return not any(s.startswith(("preflight_failed", "timeout")) for s in status)


def _bridge_healthy() -> bool:
    from jobwright.hermes_cron import hermes_dry_run
    from jobwright.preflight import check_hermes, check_whatsapp_bridge

    if hermes_dry_run():
        return True
    return check_hermes().ok and check_whatsapp_bridge().ok


def _run_notify_subprocess(user_id: str, status_path: Path) -> int:
    """``jobwright --user <id> notify --status-file F`` in its own process (own user context)."""
    proc = subprocess.run(
        [sys.executable, "-m", "jobwright", "--user", user_id, "notify", "--status-file", str(status_path)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    if proc.returncode != 0:
        log.warning("notify retry for %s exited %s: %s", user_id, proc.returncode, proc.stderr[-300:])
    return proc.returncode


def _retry_log(data_dir: Path) -> Path:
    return data_dir / "logs" / "notify_retries.json"


def retry_failed_notifies(runner=None, healthy=None, max_per_day: int | None = None) -> list[Report]:
    """Re-run notify for profiles whose brief notify failed today, once the bridge is healthy.

    At most ``max_per_day`` attempts per profile per day (JOBWRIGHT_NOTIFY_RETRIES,
    default 3), recorded in ``logs/notify_retries.json`` and as a
    ``notify_retry N`` line in the status file. Notify's own row claim + lock
    make a retry safe even if the original notify is still running.
    """
    from jobwright.users import list_users

    runner = runner or _run_notify_subprocess
    healthy = healthy or _bridge_healthy
    limit = notify_retry_limit() if max_per_day is None else max_per_day
    today = f"{datetime.now():%Y%m%d}"
    out: list[Report] = []
    bridge_ok: bool | None = None
    for user in list_users():
        if not _is_set_up(user.user_id):
            continue
        data_dir = user.resolve_data_dir()
        status_path = data_dir / f"BRIEF_STATUS_{today}"
        status = _read_status(status_path)
        if not notify_needs_retry(status):
            continue
        log_path = _retry_log(data_dir)
        try:
            data = json.loads(log_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        attempts = data.get("attempts", []) if data.get("date") == today else []
        if len(attempts) >= limit:
            continue
        if bridge_ok is None:
            bridge_ok = bool(healthy())
        if not bridge_ok:
            log.info("notify retry for %s waits: WhatsApp bridge / hermes not healthy", user.user_id)
            continue
        n = len(attempts) + 1
        with status_path.open("a", encoding="utf-8") as fh:
            fh.write(f"notify_retry {n}/{limit} by watchdog at={datetime.now().astimezone().isoformat()}\n")
        try:
            rc = runner(user.user_id, status_path)
        except Exception as exc:  # noqa: BLE001
            rc = -1
            log.warning("notify retry for %s crashed: %s", user.user_id, exc)
        result = last_notify_line(_read_status(status_path)) or f"notify exited {rc}"
        attempts.append({"at": datetime.now().astimezone().isoformat(), "rc": rc, "result": result[:200]})
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps({"date": today, "attempts": attempts}, indent=2), encoding="utf-8")
        ok = not result.startswith(("notify_failed", "notify exited"))
        level = "ok" if ok else ("fail" if n >= limit else "warn")
        lines = [f"notify retry {n}/{limit} by watchdog: {result.replace('_', ' ', 1)}"]
        if not ok and n >= limit:
            lines.append("no more automatic retries today; send from the dashboard when the bridge is back")
        out.append(Report(user.user_id, level, lines, key=f"notify_retry_{n}"))
    return out


def _is_set_up(user_id: str) -> bool:
    from jobwright.onboarding import is_set_up

    try:
        return is_set_up(user_id)
    except Exception:  # noqa: BLE001
        log.exception("could not read setup status for %s", user_id)
        return False


def install_missing_brief_crons() -> list[str]:
    """Give every set-up profile with a chat its brief cron (and one-time welcome) if it has none.

    The dashboard creates the cron when the daily-list step is saved; this
    covers anyone who finished setup some other way or left before that step.
    """
    from jobwright.hermes_cron import brief_cron_installed, ensure_brief_cron
    from jobwright.users import list_users
    from jobwright.welcome import send_welcome

    installed = []
    for user in list_users():
        if not user.whatsapp_target or brief_cron_installed(user.user_id) or not _is_set_up(user.user_id):
            continue
        result = ensure_brief_cron(user.user_id, user.schedule)
        if result.get("ok"):
            send_welcome(user.user_id)
            installed.append(user.user_id)
        else:
            log.warning("brief cron for %s not installed: %s", user.user_id, result.get("error"))
    return installed


def _watchdog_marker(user_id: str) -> Path:
    from jobwright.users import get_user

    return get_user(user_id).resolve_data_dir() / "logs" / "watchdog_alerts.json"


def watchdog_already_alerted(report: Report) -> bool:
    """True when this user was already alerted about this problem today (the watchdog runs hourly)."""
    try:
        data = json.loads(_watchdog_marker(report.user).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("date") == f"{datetime.now():%Y%m%d}" and report.key in (data.get("keys") or [])


def mark_watchdog_alerted(report: Report) -> None:
    path = _watchdog_marker(report.user)
    today = f"{datetime.now():%Y%m%d}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    keys = (data.get("keys") or []) if data.get("date") == today else []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"date": today, "keys": [*keys, report.key]}), encoding="utf-8")


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------

def default_backup_root() -> Path:
    env = os.environ.get("JOBWRIGHT_BACKUP_DIR", "").strip()
    return Path(env).expanduser() if env else Path.home() / "jobwright-backups"


LIVE_DB = "jobwright.db"
# Not the live DB: leftovers from smoke tests, manual copies, stray WAL files.
_CLUTTER = ("*.bak", "*.bak.*", "*.db.bak*", "*.db-journal", "*-wal", "*-shm", "smoke*.db", "*.smoke.db",
            "*.db.tmp", "*.db.old")


def _is_clutter(name: str) -> bool:
    from fnmatch import fnmatch

    return name != LIVE_DB and any(fnmatch(name, pat) for pat in _CLUTTER)


def _integrity(db: Path) -> str:
    with closing(sqlite3.connect(db, timeout=30)) as conn:
        rows = conn.execute("PRAGMA integrity_check").fetchall()
    return "ok" if [r[0] for r in rows] == ["ok"] else "; ".join(str(r[0]) for r in rows[:3])


def _snapshots(dest_root: Path) -> list[Path]:
    return sorted(p for p in dest_root.iterdir()
                  if p.is_dir() and not p.name.startswith(".") and p.name[:4].isdigit())


def backup_users(dest_root: Path | None = None, keep_days: int = 14) -> dict:
    """Snapshot every profile: consistent SQLite copies + hard-linked file tree.

    Layout: <dest>/<YYYY-mm-dd_HHMM>/{users.yaml, <user_id>/...}. Unchanged files
    are hard links into the previous snapshot (rsync --link-dest), so daily
    snapshots cost only what changed. Every copied DB gets ``PRAGMA
    integrity_check``. Snapshots older than keep_days are removed only when
    this snapshot had no errors (a bad night never eats the good history).
    Stale ``*.bak`` / ``*-wal`` / ``smoke*.db`` files are not copied.

    Raises when the destination cannot be used (e.g. the backup volume is
    unmounted); ``safe_backup`` turns that into an error report.
    """
    import shutil

    from jobwright.users import REGISTRY_PATH, list_users

    dest_root = (dest_root or default_backup_root()).expanduser()
    if not dest_root.exists() and not dest_root.parent.exists():
        # Never create a fake mount point on the internal disk.
        raise RuntimeError(f"backup destination parent {dest_root.parent} is missing (volume not mounted?)")
    dest_root.mkdir(exist_ok=True)
    try:
        dest_root.chmod(0o700)
    except OSError:
        pass
    previous = _snapshots(dest_root)
    snap = dest_root / f".tmp-{datetime.now():%Y-%m-%d_%H%M%S}"
    snap.mkdir()
    report: dict = {"snapshot": None, "users": {}, "errors": [], "pruned": []}
    if REGISTRY_PATH.exists():
        shutil.copy2(REGISTRY_PATH, snap / "users.yaml")
    for user in list_users():
        src = user.resolve_data_dir()
        if not src.exists():
            report["errors"].append(f"{user.user_id}: data dir missing ({src})")
            continue
        out = snap / user.user_id
        out.mkdir()
        cmd = ["rsync", "-a", "--exclude", "*.db", "--exclude", "*.db-wal", "--exclude", "*.db-shm",
               "--exclude", "chrome-workers/", "--exclude", "apply-workers/", "--exclude", "logs/*.log",
               "--exclude", ".pipeline.lock", "--exclude", ".notify.lock"]
        for pat in _CLUTTER:
            cmd += ["--exclude", pat]
        if previous and (previous[-1] / user.user_id).exists():
            cmd += ["--link-dest", str(previous[-1] / user.user_id)]
        proc = subprocess.run([*cmd, f"{src}/", f"{out}/"], capture_output=True, text=True, check=False)
        if proc.returncode not in (0, 24):
            report["errors"].append(f"{user.user_id}: rsync {proc.returncode} {proc.stderr[:200]}")
        dbs = 0
        for db in sorted(src.glob("*.db")):
            if _is_clutter(db.name):
                continue
            try:
                with closing(sqlite3.connect(db, timeout=30)) as source, \
                        closing(sqlite3.connect(out / db.name)) as target:
                    source.backup(target)
                check = _integrity(out / db.name)
                if check != "ok":
                    report["errors"].append(f"{user.user_id}: {db.name}: integrity_check failed: {check[:160]}")
                dbs += 1
            except sqlite3.Error as exc:
                report["errors"].append(f"{user.user_id}: {db.name}: {exc}")
        report["users"][user.user_id] = {"dbs": dbs}
    final = dest_root / snap.name.removeprefix(".tmp-")
    n = 2
    while final.exists():
        final = dest_root / f"{snap.name.removeprefix('.tmp-')}-{n}"
        n += 1
    snap.rename(final)
    report["snapshot"] = str(final)
    if report["errors"]:
        log.warning("backup had errors; keeping every older snapshot")
        return report
    cutoff = datetime.now() - timedelta(days=keep_days)
    for old in previous:
        try:
            if datetime.strptime(old.name[:10], "%Y-%m-%d") < cutoff:
                shutil.rmtree(old)
                report["pruned"].append(old.name)
        except ValueError:
            continue
    return report


def safe_backup(dest_root: Path | None = None, keep_days: int = 14) -> dict:
    """backup_users that never raises: a crash (unmounted SSD, full disk) becomes an error report."""
    try:
        return backup_users(dest_root, keep_days=keep_days)
    except Exception as exc:  # noqa: BLE001
        log.exception("backup crashed")
        return {"snapshot": None, "users": {}, "errors": [f"backup crashed: {type(exc).__name__}: {exc}"],
                "pruned": []}


def restore_snapshot(
    snapshot: str,
    user_id: str,
    to_dir: Path | None = None,
    *,
    force: bool = False,
    backup_root: Path | None = None,
) -> dict:
    """Copy one profile out of a snapshot (``latest`` or a snapshot name) and verify its DB.

    Restores to a separate directory by default (``~/jobwright-restore/<user>-<snapshot>``).
    Refuses to write into a live profile's data dir, or any non-empty
    directory, unless ``force``; with ``force`` the existing directory is moved
    aside to ``<dir>.pre-restore-<time>`` first, never deleted.
    """
    import shutil

    from jobwright.users import list_users

    root = (backup_root or default_backup_root()).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"no backups at {root}")
    snaps = _snapshots(root)
    if snapshot == "latest":
        if not snaps:
            raise FileNotFoundError(f"no snapshots in {root}")
        snap = snaps[-1]
    else:
        snap = root / snapshot
        if not snap.is_dir() or snap.name.startswith("."):
            raise FileNotFoundError(f"snapshot {snapshot!r} not found in {root}")
    src = snap / user_id
    if not src.is_dir():
        raise FileNotFoundError(f"user {user_id!r} is not in snapshot {snap.name}")
    target = (to_dir or Path.home() / "jobwright-restore" / f"{user_id}-{snap.name}").expanduser()
    live = {u.resolve_data_dir().resolve() for u in list_users()}
    is_live = target.resolve() in live
    moved_aside = None
    if target.exists() and any(target.iterdir()):
        if not force:
            what = "a live profile's data dir" if is_live else "not empty"
            raise FileExistsError(f"{target} is {what}; pass --force to move it aside and restore there")
        moved_aside = target.with_name(f"{target.name}.pre-restore-{datetime.now():%Y%m%d_%H%M%S}")
        target.rename(moved_aside)
    elif is_live and not force:
        raise FileExistsError(f"{target} is a live profile's data dir; pass --force to restore there")
    if target.exists():
        target.rmdir()  # empty
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, target, symlinks=True)
    checks = {db.name: _integrity(db) for db in sorted(target.glob("*.db"))}
    return {"snapshot": snap.name, "user": user_id, "restored_to": str(target),
            "moved_aside": str(moved_aside) if moved_aside else None, "integrity": checks,
            "ok": all(v == "ok" for v in checks.values())}


def cleanup_old_brief_files(days: int = 30) -> list[str]:
    """Remove BRIEF_STATUS_* / BRIEF_PID_* files and logs/brief_*.log older than ``days`` (by the date in the name)."""
    from jobwright.users import list_users

    cutoff = datetime.now() - timedelta(days=days)
    removed: list[str] = []
    for user in list_users():
        data = user.resolve_data_dir()
        candidates = [*data.glob("BRIEF_STATUS_*"), *data.glob("BRIEF_PID_*"), *(data / "logs").glob("brief_*.log")]
        for path in candidates:
            stamp = path.stem.rsplit("_", 1)[-1]
            try:
                when = datetime.strptime(stamp[:8], "%Y%m%d")
            except ValueError:
                continue
            if when < cutoff:
                try:
                    path.unlink()
                    removed.append(str(path))
                except OSError as exc:
                    log.warning("could not remove %s: %s", path, exc)
    return removed
