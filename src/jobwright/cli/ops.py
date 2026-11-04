"""`jobwright ops ...`: brief reports, watchdog, backups, crons."""

from __future__ import annotations

from typing import Optional

import typer

from jobwright.cli._common import _configure_logging, bootstrap, console


ops_app = typer.Typer(help="Operator health: brief reports, watchdog, alert target.")


@ops_app.command("brief-report")
def ops_brief_report(
    status_file: Optional[str] = typer.Option(None, "--status-file"),
    force: bool = typer.Option(False, "--force", help="Send even when everything is OK."),
) -> None:
    """Summarize today's brief for this user; alert the operator if anything is wrong."""
    bootstrap()
    from pathlib import Path as _Path

    from jobwright.ops import build_brief_report, deliver, write_health

    rep = build_brief_report(_Path(status_file) if status_file else None)
    write_health(rep)
    console.print(rep.text())
    console.print(f"[dim]{deliver(rep, force=force)}[/dim]")


@ops_app.command("watchdog")
def ops_watchdog(
    grace: int = typer.Option(120, "--grace", help="Minutes after the scheduled time."),
    retry_notify: bool = typer.Option(True, "--retry-notify/--no-retry-notify",
                                      help="Re-run a failed notify once the WhatsApp bridge is healthy."),
) -> None:
    """Install briefs for newly set-up profiles, alert for any brief that never started/finished today, retry failed notifies."""
    _configure_logging()
    from jobwright.config import load_env
    from jobwright.ops import (
        deliver,
        install_missing_brief_crons,
        mark_watchdog_alerted,
        retry_failed_notifies,
        watchdog,
        watchdog_already_alerted,
    )

    load_env()
    for user_id in install_missing_brief_crons():
        console.print(f"Installed missing daily brief for {user_id} (setup finished).")
    reports = watchdog(grace_minutes=grace)
    if not reports:
        console.print("All briefs accounted for.")
    for rep in reports:
        console.print(rep.text())
        if watchdog_already_alerted(rep):
            console.print("[dim]already alerted today[/dim]")
            continue
        result = deliver(rep)
        console.print(f"[dim]{result}[/dim]")
        if getattr(result, "delivered", str(result).startswith("sent")):
            mark_watchdog_alerted(rep)
    if retry_notify:
        for rep in retry_failed_notifies():
            console.print(rep.text())
            console.print(f"[dim]{deliver(rep, force=True)}[/dim]")


@ops_app.command("set-target")
def ops_set_target(target: str = typer.Argument(..., help="whatsapp:<jid> for operator alerts ('' to clear).")) -> None:
    """Where operator alerts go (usually the admin's own WhatsApp)."""
    from jobwright.ops import set_ops_target

    console.print(f"ops_target = {set_ops_target(target) or '(cleared)'}")


@ops_app.command("release-uncertain")
def ops_release_uncertain() -> None:
    """After a timed-out WhatsApp send that never arrived: unmark those jobs so the next notify sends them."""
    bootstrap()
    from jobwright.notify import read_uncertain, release_uncertain

    entries = read_uncertain()
    if not entries:
        console.print("No uncertain sends recorded.")
        return
    for e in entries:
        console.print(f"{e.get('at')}: {len(e.get('urls') or [])} job(s) — {e.get('error')}")
    console.print(f"Released {release_uncertain()} job(s); the next notify will include them.")


@ops_app.command("backup")
def ops_backup(
    dest: Optional[str] = typer.Option(None, "--dest", help="Backup root (default JOBWRIGHT_BACKUP_DIR or ~/jobwright-backups)."),
    keep: int = typer.Option(14, "--keep", help="Days of snapshots to keep (pruned only after a clean snapshot)."),
    cleanup_days: int = typer.Option(30, "--cleanup-days", help="Also delete brief status/PID files and brief logs older than this (0 = keep)."),
) -> None:
    """Snapshot every profile (consistent, integrity-checked DB copies + hard-linked files); alert on any error."""
    _configure_logging()
    from pathlib import Path as _Path

    from jobwright.config import load_env
    from jobwright.ops import Report, cleanup_old_brief_files, deliver, safe_backup

    load_env()
    rep = safe_backup(_Path(dest) if dest else None, keep_days=keep)
    console.print(f"Snapshot: {rep['snapshot']}  users: {rep['users']}  pruned: {len(rep.get('pruned') or [])}")
    if cleanup_days > 0:
        try:
            removed = cleanup_old_brief_files(cleanup_days)
            console.print(f"Removed {len(removed)} brief status/log file(s) older than {cleanup_days} days.")
        except Exception as exc:  # noqa: BLE001 - housekeeping must not hide the backup result
            console.print(f"[yellow]Brief file cleanup failed:[/yellow] {exc}")
    if rep["errors"]:
        for e in rep["errors"]:
            console.print(f"[red]{e}[/red]")
        console.print(deliver(Report("backup", "fail", rep["errors"][:5])))
        raise typer.Exit(code=1)


@ops_app.command("restore")
def ops_restore(
    snapshot: str = typer.Option(..., "--snapshot", help="Snapshot name (e.g. 2026-11-02_0230) or 'latest'."),
    user_id: str = typer.Option(..., "--user", help="Profile to restore from the snapshot."),
    to: Optional[str] = typer.Option(None, "--to", help="Directory to restore into (default ~/jobwright-restore/<user>-<snapshot>)."),
    force: bool = typer.Option(False, "--force", help="Allow a live profile dir / non-empty dir (moved aside first, never deleted)."),
    dest: Optional[str] = typer.Option(None, "--dest", help="Backup root (default JOBWRIGHT_BACKUP_DIR or ~/jobwright-backups)."),
) -> None:
    """Restore one profile from a backup snapshot into a separate directory and integrity-check its DB."""
    _configure_logging()
    from pathlib import Path as _Path

    from jobwright.config import load_env
    from jobwright.ops import restore_snapshot

    load_env()
    try:
        out = restore_snapshot(snapshot, user_id, _Path(to) if to else None, force=force,
                               backup_root=_Path(dest) if dest else None)
    except (FileNotFoundError, FileExistsError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    console.print(f"Restored {out['user']} from {out['snapshot']} to {out['restored_to']}")
    if out["moved_aside"]:
        console.print(f"Previous contents moved to {out['moved_aside']}")
    for name, check in out["integrity"].items():
        console.print(f"  {name}: integrity_check {check}")
    if not out["ok"]:
        raise typer.Exit(code=1)


def eval_eligible(user_id: str, min_labels: int = 20, min_relevant: int = 3) -> bool:
    from jobwright import config as _config
    from jobwright.database import get_connection
    from jobwright.labels import build_eval_set

    with _config.user_context(user_id):
        if not _config.DB_PATH.exists():
            return False
        items = build_eval_set(get_connection())
    return len(items) >= min_labels and sum(i.label for i in items) >= min_relevant


@ops_app.command("weekly-eval")
def ops_weekly_eval(min_labels: int = typer.Option(20, "--min-labels", help="Skip profiles with fewer ratings.")) -> None:
    """Accuracy check for every profile with enough ratings; alerts the operator on failure."""
    import subprocess as _sp
    import sys as _sys

    from jobwright.config import load_env
    from jobwright.ops import Report, deliver
    from jobwright.users import list_users

    load_env()
    failed = []
    for u in list_users():
        if not eval_eligible(u.user_id, min_labels):
            console.print(f"skip  {u.user_id}  (fewer than {min_labels} ratings)")
            continue
        proc = _sp.run([_sys.executable, "-m", "jobwright.cli", "--user", u.user_id, "eval", "-w", "8"], check=False)
        console.print(f"{'ok' if proc.returncode == 0 else 'FAIL'}  {u.user_id}")
        if proc.returncode != 0:
            failed.append(u.user_id)
    if failed:
        console.print(deliver(Report("weekly-eval", "fail", [f"accuracy check failed for {', '.join(failed)}"])))
        raise typer.Exit(code=1)


@ops_app.command("install-crons")
def ops_install_crons(
    backup_dest: Optional[str] = typer.Option(None, "--backup-dest", help="Backup root for the nightly backup cron."),
    skip_ops: bool = typer.Option(False, "--skip-ops", help="Only the per-user brief crons."),
) -> None:
    """Create or update every jobwright Hermes cron: briefs, watchdog, backup, weekly summary."""
    import os as _os

    from jobwright.config import load_env
    from jobwright.hermes_cron import (
        BACKUP_CRON_NAME,
        WATCHDOG_CRON_NAME,
        WEEKLY_EVAL_CRON_NAME,
        WEEKLY_SUMMARY_CRON_NAME,
        ensure_backup_cron,
        ensure_brief_cron,
        ensure_watchdog_cron,
        ensure_weekly_eval_cron,
        ensure_weekly_summary_cron,
    )
    from jobwright.users import list_users

    load_env()
    from jobwright.onboarding import is_set_up

    results = []
    for u in list_users():
        if not is_set_up(u.user_id):
            console.print(f"[dim]skip  jobwright-brief-{u.user_id}  (setup not finished)[/dim]")
            continue
        results.append((f"jobwright-brief-{u.user_id}", ensure_brief_cron(u.user_id, u.schedule or "0 6 * * *")))
    if not skip_ops:
        results.append((WATCHDOG_CRON_NAME, ensure_watchdog_cron()))
        dest = backup_dest or _os.environ.get("JOBWRIGHT_BACKUP_DIR", "")
        results.append((BACKUP_CRON_NAME, ensure_backup_cron(dest=dest)))
        results.append((WEEKLY_SUMMARY_CRON_NAME, ensure_weekly_summary_cron()))
        results.append((WEEKLY_EVAL_CRON_NAME, ensure_weekly_eval_cron()))
    failed = False
    for name, r in results:
        ok = bool(r.get("ok"))
        failed = failed or not ok
        console.print(f"{'[green]ok[/green]' if ok else '[red]FAIL[/red]'}  {name}  {r.get('error') or ''}")
    if failed:
        raise typer.Exit(code=1)
