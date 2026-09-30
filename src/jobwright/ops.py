"""Operator health: per-brief report, missed-run watchdog, alert delivery.

Silence used to look the same as "no jobs today". Now every brief ends with a
report; anything abnormal (preflight failure, failed stage, zero scored jobs,
notify failure, provider errors) is sent to the operator's WhatsApp target
(``ops_target`` in users.yaml, or JOBWRIGHT_OPS_TARGET). A watchdog run
(hourly Hermes cron) alerts once per day when a user's brief never started or
never finished today.
"""

from __future__ import annotations

import json
import logging
import os
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


def build_brief_report(status_file: Path | None = None) -> Report:
    from jobwright.database import get_connection
    from jobwright.pipeline import read_run_summary

    user = config.get_active_user_id() or "legacy"
    status_file = status_file or Path(config.APP_DIR) / f"BRIEF_STATUS_{datetime.now():%Y%m%d}"
    status = _read_status(status_file)
    summary = read_run_summary() or {}
    rep = Report(user=user, level="ok")

    def bump(level: str) -> None:
        order = {"ok": 0, "warn": 1, "fail": 2}
        if order[level] > order[rep.level]:
            rep.level = level

    if any(s.startswith("preflight_failed") for s in status):
        bump("fail")
        rep.lines.append("preflight failed: pipeline did not run (see brief log)")
    for stage, err in (summary.get("errors") or {}).items():
        bump("fail" if stage in ("discover", "score") else "warn")
        rep.lines.append(f"stage {stage}: {str(err)[:160]}")
    stages = {s.get("stage"): s for s in summary.get("stages") or []}
    score = (stages.get("score") or {}).get("detail") or {}
    if "score" in stages:
        scored, errors = int(score.get("scored") or 0), int(score.get("errors") or 0)
        rep.lines.append(f"scored {scored} jobs ({errors} failed)")
        if errors and errors > max(3, scored * 0.1):
            bump("warn")
    enrich = (stages.get("enrich") or {}).get("detail") or {}
    if enrich.get("error"):
        rep.lines.append(f"enrich errors: {enrich.get('error')}")
    notify = next((s for s in reversed(status) if s.startswith("notify_")), "")
    if notify.startswith("notify_failed"):
        bump("fail")
        rep.lines.append(notify.replace("_", " ", 1))
    elif notify:
        rep.lines.append(notify.replace("_", " ", 1))
    elif status:
        bump("warn")
        rep.lines.append("notify did not run")
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
    if not summary:
        bump("warn")
        rep.lines.append("no run summary (logs/last_run.json) found")
    return rep


def deliver(report: Report, *, force: bool = False) -> str:
    """Send to the ops target when not ok (or forced). Returns what happened."""
    heartbeat = os.environ.get("JOBWRIGHT_OPS_HEARTBEAT", "").lower() in ("1", "true", "yes")
    if report.level == "ok" and not (force or heartbeat):
        return "ok (no alert)"
    target = ops_target()
    if not target:
        return "no ops_target configured (alert logged only)"
    from jobwright.notify import send_via_hermes

    try:
        send_via_hermes(report.text(), target)
        return f"sent to {target}"
    except Exception as exc:  # noqa: BLE001
        return f"alert delivery failed: {exc}"


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


def _cron_clock_today(expr: str) -> datetime | None:
    parts = (expr or "").split()
    if len(parts) != 5 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    now = datetime.now()
    return now.replace(hour=int(parts[1]), minute=int(parts[0]), second=0, microsecond=0)


def watchdog(grace_minutes: int = 120, start_grace_minutes: int = 30) -> list[Report]:
    """Alert for every user whose brief never started, or should have finished by now but did not.

    The launcher writes the status file within seconds, so a missing file is
    flagged after ``start_grace_minutes``; an unfinished run after ``grace_minutes``.
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
        status_path = user.resolve_data_dir() / f"BRIEF_STATUS_{now:%Y%m%d}"
        status = _read_status(status_path)
        if not status:
            reports.append(Report(user.user_id, "fail", [f"no brief started today (scheduled {user.schedule})"],
                                  key="not_started"))
            continue
        # A late manual rerun counts from when it started; the file is not touched again until it ends.
        started = max(start, datetime.fromtimestamp(status_path.stat().st_mtime))
        if now >= started + timedelta(minutes=grace_minutes) and not any(s.startswith("done") for s in status):
            reports.append(Report(user.user_id, "fail", ["brief started but has not finished", *status[-3:]],
                                  key="not_finished"))
    return reports


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


def backup_users(dest_root: Path | None = None, keep_days: int = 14) -> dict:
    """Snapshot every profile: consistent SQLite copies + hard-linked file tree.

    Layout: <dest>/<YYYY-mm-dd_HHMM>/{users.yaml, <user_id>/...}. Unchanged files
    are hard links into the previous snapshot (rsync --link-dest), so daily
    snapshots cost only what changed. Snapshots older than keep_days are removed.
    """
    import shutil
    import sqlite3
    import subprocess

    from jobwright.users import REGISTRY_PATH, list_users

    dest_root = (dest_root or default_backup_root()).expanduser()
    dest_root.mkdir(parents=True, exist_ok=True)
    try:
        dest_root.chmod(0o700)
    except OSError:
        pass
    previous = sorted(p for p in dest_root.iterdir() if p.is_dir() and not p.name.startswith("."))
    snap = dest_root / f".tmp-{datetime.now():%Y-%m-%d_%H%M%S}"
    snap.mkdir()
    report: dict = {"snapshot": None, "users": {}, "errors": []}
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
               "--exclude", "chrome-workers/", "--exclude", "apply-workers/", "--exclude", "logs/*.log"]
        if previous:
            cmd += ["--link-dest", str(previous[-1] / user.user_id)]
        proc = subprocess.run([*cmd, f"{src}/", f"{out}/"], capture_output=True, text=True, check=False)
        if proc.returncode not in (0, 24):
            report["errors"].append(f"{user.user_id}: rsync {proc.returncode} {proc.stderr[:200]}")
        dbs = 0
        for db in src.glob("*.db"):
            try:
                with sqlite3.connect(db, timeout=30) as source, sqlite3.connect(out / db.name) as target:
                    source.backup(target)
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
    cutoff = datetime.now() - timedelta(days=keep_days)
    for old in previous:
        try:
            if datetime.strptime(old.name[:10], "%Y-%m-%d") < cutoff:
                shutil.rmtree(old)
        except ValueError:
            continue
    return report
