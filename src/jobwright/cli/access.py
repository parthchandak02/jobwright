"""`jobwright access ...`: the Cloudflare Access allowlist."""

from __future__ import annotations

import typer

from jobwright.cli._common import console


access_app = typer.Typer(help="Cloudflare Access allowlist (policy 'jobwright users') kept in sync with users.yaml.")


def _print_access_plan(plan: dict) -> None:
    app_info = plan.get("app") or {}
    console.print(f"App: {app_info.get('name')} ({app_info.get('domain')})")
    managed = plan.get("managed_policy") or {}
    console.print(f"Policy '{managed.get('name')}': {'exists' if managed.get('exists') else 'missing (created on sync)'}")
    console.print(f"Current: {', '.join(plan['current']) or '(none)'}")
    console.print(f"Desired: {', '.join(plan['desired']) or '(none)'}")
    for e in plan["add"]:
        console.print(f"[green]+ {e}[/green]")
    for e in plan["remove"]:
        console.print(f"[red]- {e}[/red]")
    if plan.get("other_policies_emails"):
        console.print(f"Also allowed by other policies (not managed): {', '.join(plan['other_policies_emails'])}")
    console.print("[green]In sync[/green]" if plan.get("in_sync") else "[yellow]Out of sync[/yellow]")


def _access_call(fn):
    from jobwright.cf_access import CFAccessError
    from jobwright.config import load_env

    load_env()
    try:
        return fn()
    except CFAccessError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc


@access_app.command("status")
def access_status() -> None:
    """Show the Access allowlist diff (users.yaml emails + admins vs the managed policy)."""
    from jobwright.cf_access import plan_sync

    _print_access_plan(_access_call(plan_sync))


@access_app.command("sync")
def access_sync(yes: bool = typer.Option(False, "--yes", help="Apply the change (default: dry-run diff).")) -> None:
    """Set the 'jobwright users' allow policy to exactly the users.yaml emails + admins."""
    from jobwright.cf_access import apply_sync, plan_sync

    if not yes:
        _print_access_plan(_access_call(plan_sync))
        console.print("Dry run. Re-run with --yes to apply.")
        return
    plan = _access_call(apply_sync)
    _print_access_plan(plan)
    console.print("Created policy." if plan.get("created") else ("Updated policy." if plan.get("applied") else "No change."))
