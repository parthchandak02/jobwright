"""`jobwright users ...`: the local multi-profile registry."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from jobwright.cli._common import console


users_app = typer.Typer(help="Manage multi-profile users (local registry).")


@users_app.command("add")
def users_add(
    user_id: str = typer.Argument(..., help="Short id (e.g. richa)."),
    name: str = typer.Option("", "--name", "-n", help="Display name."),
    whatsapp: str = typer.Option(
        "", "--whatsapp", "-w",
        help="Hermes deliver target, e.g. whatsapp:1203634...",
    ),
    apply_enabled: bool = typer.Option(
        False, "--apply/--no-apply",
        help="Enable gated live apply for this user (default: off / find-only).",
    ),
    schedule: str = typer.Option(
        "0 */3 * * 1-5", "--schedule",
        help="Cron schedule for morning prep (default: every 3h weekdays).",
    ),
    template: Optional[str] = typer.Option(
        None, "--template",
        help="Seed searches.yaml from a packaged template (e.g. nontech-bay-area).",
    ),
) -> None:
    """Register a new user and create their data directory.

    API keys are global (one .env, see `jobwright doctor`); a new user only gets
    a data dir for their profile/resume/searches.
    """
    from jobwright.users import add_user, USERS_ROOT
    from jobwright.config import CONFIG_DIR
    import shutil

    try:
        user = add_user(
            user_id=user_id,
            name=name,
            whatsapp_target=whatsapp,
            apply_enabled=apply_enabled,
            schedule=schedule,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    data_dir = user.resolve_data_dir()
    if template:
        src = CONFIG_DIR / f"searches.{template}.yaml"
        if not src.exists():
            src = CONFIG_DIR / f"{template}.yaml"
        if src.exists():
            shutil.copy2(src, data_dir / "searches.yaml")
            console.print(f"[green]Seeded searches.yaml from {src.name}[/green]")
        else:
            console.print(f"[yellow]Template not found:[/yellow] {template}")
        # Seed a starter profile when using the nontech template
        if template == "nontech-bay-area" and not (data_dir / "profile.json").exists():
            # cli/users.py -> repo root is four levels up (was parents[2] from cli.py)
            profile_src = Path(__file__).resolve().parents[3] / "profile.example.json"
            if profile_src.exists():
                shutil.copy2(profile_src, data_dir / "profile.json")
                console.print(f"[green]Seeded profile.json from {profile_src.name}[/green]")
                console.print("[yellow]Edit profile.json: email, phone, sponsorship, etc.[/yellow]")

    console.print(f"[green]Created user[/green] {user.user_id}")
    console.print(f"  data dir:       {data_dir}")
    console.print(f"  apply_enabled:  {user.apply_enabled}")
    console.print(f"  whatsapp:       {user.whatsapp_target or '(none)'}")
    console.print(f"  registry:       {USERS_ROOT / 'users.yaml'}")
    console.print(
        "\nNext: copy resume/base.pdf + profile.json into the data dir, "
        f"or run [bold]jobwright --user {user_id} init[/bold]"
    )


@users_app.command("list")
def users_list() -> None:
    """List registered multi-profile users."""
    from jobwright.users import list_users, REGISTRY_PATH

    users = list_users()
    if not users:
        console.print(
            f"[yellow]No users registered.[/yellow]\n"
            f"Add one: jobwright users add <id>\n"
            f"Registry: {REGISTRY_PATH}"
        )
        return

    table = Table(title="jobwright Users", show_header=True, header_style="bold cyan")
    table.add_column("user_id")
    table.add_column("name")
    table.add_column("apply")
    table.add_column("whatsapp")
    table.add_column("schedule")
    table.add_column("data_dir")
    for u in users:
        table.add_row(
            u.user_id,
            u.name,
            "yes" if u.apply_enabled else "no",
            u.whatsapp_target or "-",
            u.schedule,
            str(u.resolve_data_dir()),
        )
    console.print(table)


@users_app.command("show")
def users_show(user_id: str = typer.Argument(...)) -> None:
    """Show one user's registry record and data dir contents."""
    from jobwright.users import get_user

    user = get_user(user_id)
    if user is None:
        console.print(f"[red]Unknown user:[/red] {user_id}")
        raise typer.Exit(code=1)
    data_dir = user.resolve_data_dir()
    console.print(f"[bold]{user.user_id}[/bold] ({user.name})")
    console.print(f"  apply_enabled:   {user.apply_enabled}")
    console.print(f"  whatsapp_target: {user.whatsapp_target or '-'}")
    console.print(f"  schedule:        {user.schedule}")
    console.print(f"  digest_schedule: {user.digest_schedule}")
    console.print(f"  data_dir:        {data_dir}")
    for fname in (
        "profile.json", "resume/base.pdf", "searches.yaml",
        "connections.csv", "target_companies.yaml",
        "jobwright.db",
    ):
        exists = (data_dir / fname).exists()
        mark = "[green]OK[/green]" if exists else "[dim]missing[/dim]"
        console.print(f"  {fname:24} {mark}")
    examples_dir = data_dir / "cover-letter" / "examples"
    ex_count = len(list(examples_dir.glob("*.pdf"))) if examples_dir.is_dir() else 0
    console.print(f"  cover-letter/examples   {ex_count} file(s)")


@users_app.command("remove")
def users_remove(
    user_id: str = typer.Argument(...),
    delete_data: bool = typer.Option(
        False, "--delete-data",
        help="Also delete users/<id>/ data directory (destructive).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Remove a user from the registry (optionally delete their data dir)."""
    from jobwright.users import remove_user, get_user

    user = get_user(user_id)
    if user is None:
        console.print(f"[red]Unknown user:[/red] {user_id}")
        raise typer.Exit(code=1)
    if delete_data and not yes:
        confirm = typer.confirm(
            f"Delete data dir {user.resolve_data_dir()} permanently?"
        )
        if not confirm:
            console.print("Aborted.")
            raise typer.Exit()
    remove_user(user_id, delete_data=delete_data)
    console.print(f"[green]Removed user[/green] {user_id}")


@users_app.command("set")
def users_set(
    user_id: str = typer.Argument(...),
    apply_enabled: Optional[bool] = typer.Option(
        None, "--apply/--no-apply", help="Toggle live apply.",
    ),
    whatsapp: Optional[str] = typer.Option(None, "--whatsapp", "-w"),
    name: Optional[str] = typer.Option(None, "--name", "-n"),
    schedule: Optional[str] = typer.Option(None, "--schedule"),
    human_gate: bool | None = typer.Option(
        None, "--human-gate/--no-human-gate",
        help="Human gate: stop the daily brief before material generation.",
    ),
    brief_top_n: int | None = typer.Option(
        None, "--brief-top-n",
        help="Per-brief notify cap (top N by fit score; 0 = uncapped).",
    ),
    search: bool | None = typer.Option(
        None, "--search/--pause-search",
        help="Keep looking for new jobs (default on); --pause-search stops the daily search.",
    ),
) -> None:
    """Update fields on an existing user."""
    from jobwright.users import update_user

    fields: dict = {}
    if apply_enabled is not None:
        fields["apply_enabled"] = apply_enabled
    if whatsapp is not None:
        fields["whatsapp_target"] = whatsapp
    if name is not None:
        fields["name"] = name
    if schedule is not None:
        fields["schedule"] = schedule
    if human_gate is not None:
        fields["human_gate"] = human_gate
    if brief_top_n is not None:
        fields["brief_top_n"] = brief_top_n
    if search is not None:
        fields["search_enabled"] = search
    if not fields:
        console.print("[yellow]No fields to update.[/yellow]")
        raise typer.Exit(code=1)
    try:
        user = update_user(user_id, **fields)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)
    console.print(f"[green]Updated[/green] {user.user_id}: {fields}")
