"""`jobwright hermes ...`: Hermes gateway config generated from users.yaml."""

from __future__ import annotations

from typing import Optional

import typer

from jobwright.cli._common import console, err_console


hermes_app = typer.Typer(help="Hermes gateway config generated from users.yaml.")


@hermes_app.command("channels")
def hermes_channels_cmd(
    apply_changes: bool = typer.Option(False, "--apply", help="Write the changes (backup first)."),
    prune: bool = typer.Option(False, "--prune", help="Also remove managed entries whose group no longer belongs to a profile."),
    config_path: Optional[str] = typer.Option(None, "--config", help="Hermes config (default $HERMES_CONFIG or ~/.hermes/config.yaml)."),
) -> None:
    """Per-profile WhatsApp group instructions in the Hermes config: show the diff, optionally apply."""
    from jobwright import hermes_channels
    from jobwright.hermes_cron import hermes_dry_run

    try:
        result = hermes_channels.apply(config_path, prune=prune) if apply_changes else \
            hermes_channels.plan(config_path, prune=prune).as_dict()
    except (OSError, ValueError) as exc:
        err_console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1)
    for e in result["entries"]:
        console.print(f"{e['status']:<9}  {e['user_id']}  {e['jid']}  {','.join(e['changes'])}")
    for s in result["skipped"]:
        console.print(f"[dim]skipped    {s['user_id']}  {s['reason']}[/dim]")
    for jid in result["orphans"]:
        console.print(f"[yellow]orphan     {jid}  (managed entry with no profile; --prune removes it)[/yellow]")
    if result["diff"]:
        console.print(result["diff"], markup=False, highlight=False, soft_wrap=True)
    if not result["changed"]:
        console.print("Hermes config is up to date.")
    elif not apply_changes:
        console.print("Re-run with --apply to write, then `hermes gateway restart`.")
    elif result.get("written"):
        console.print(f"Written. Backup: {result['backup']}\nRun `hermes gateway restart` to apply it.")
    elif hermes_dry_run():
        console.print("JOBWRIGHT_HERMES_DRY_RUN is set: nothing written.")
