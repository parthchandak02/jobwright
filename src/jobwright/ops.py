"""Operator health: per-brief report, missed-run watchdog, alert delivery.

Silence used to look the same as "no jobs today". Now every brief ends with a
report; anything abnormal (preflight failure, failed stage, zero scored jobs,
notify failure, provider errors) is sent to the operator's WhatsApp target
(``ops_target`` in users.yaml, or JOBWRIGHT_OPS_TARGET). A watchdog run
(Hermes cron, e.g. 08:30) alerts when a user's brief never started or never
finished today.
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


def watchdog(grace_minutes: int = 120) -> list[Report]:
    """Alert for every user whose brief should have finished by now but did not."""
    from jobwright.users import list_users

    reports: list[Report] = []
    now = datetime.now()
    for user in list_users():
        start = _cron_clock_today(user.schedule)
        if start is None or now < start + timedelta(minutes=grace_minutes):
            continue
        status_path = user.resolve_data_dir() / f"BRIEF_STATUS_{now:%Y%m%d}"
        status = _read_status(status_path)
        if not status:
            reports.append(Report(user.user_id, "fail", [f"no brief started today (scheduled {user.schedule})"]))
        elif not any(s.startswith("done") for s in status):
            reports.append(Report(user.user_id, "fail", ["brief started but has not finished", *status[-3:]]))
    return reports
