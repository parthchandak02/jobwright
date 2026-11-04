"""Pipeline commands: `init`, `run`, `apply`."""

from __future__ import annotations

from typing import Optional

import typer

from jobwright.cli._common import VALID_STAGES, bootstrap, console


def init() -> None:
    """Run the first-time setup wizard (profile, resume, search config)."""
    bootstrap()
    from jobwright.wizard.init import run_wizard

    run_wizard()


def run(
    stages: Optional[list[str]] = typer.Argument(
        None,
        help=(
            "Pipeline stages to run. "
            f"Valid: {', '.join(VALID_STAGES)}, all. "
            "Omit to run the default brief for this profile."
        ),
    ),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for tailor/cover stages."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads for discovery/enrichment stages."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stages without executing."),
    verbose: bool = typer.Option(
        False, "--verbose", "-v",
        help="Force JOBWRIGHT_LOG_LEVEL=DEBUG for maximum backend log detail.",
    ),
    validation: str = typer.Option(
        "normal",
        "--validation",
        help=(
            "Validation strictness for tailor/cover stages. "
            "strict: banned words = errors, judge must pass. "
            "normal: banned words = warnings only (default, recommended for Gemini free tier). "
            "lenient: banned words ignored, LLM judge skipped (fastest, fewest API calls)."
        ),
    ),
) -> None:
    """Run pipeline stages: discover, enrich, score, portfolio, tailor, cover, pdf, docx, connect (no stages = the default brief)."""
    if verbose:
        import os
        os.environ["JOBWRIGHT_LOG_LEVEL"] = "DEBUG"
    bootstrap()

    from jobwright.pipeline import run_pipeline

    # When no stages are given, let the pipeline resolve the default brief
    # stage list (which honors the user's human_gate config key). Explicit
    # stage lists always run verbatim — on-demand `run tailor cover docx`
    # still generates materials for an approved job.
    explicit = list(stages) if stages else None

    # Validate stage names
    if explicit:
        for s in explicit:
            if s != "all" and s not in VALID_STAGES:
                console.print(
                    f"[red]Unknown stage:[/red] '{s}'. "
                    f"Valid stages: {', '.join(VALID_STAGES)}, all"
                )
                raise typer.Exit(code=1)

    # Gate AI stages behind Tier 2 (default briefs include scoring either way).
    llm_stages = {"score", "tailor", "cover"}
    runs_llm = explicit is None or "all" in explicit or any(s in llm_stages for s in explicit)
    if runs_llm:
        from jobwright.config import check_tier
        check_tier(2, "AI scoring/tailoring")

    # Validate the --validation flag value
    valid_modes = ("strict", "normal", "lenient")
    if validation not in valid_modes:
        console.print(
            f"[red]Invalid --validation value:[/red] '{validation}'. "
            f"Choose from: {', '.join(valid_modes)}"
        )
        raise typer.Exit(code=1)

    result = run_pipeline(
        stages=explicit,
        min_score=min_score,
        dry_run=dry_run,
        workers=workers,
        validation_mode=validation,
    )

    if result.get("locked"):
        # 75 (EX_TEMPFAIL): another run holds the lock; run_daily_brief.sh
        # records "pipeline_locked" so the brief report can say so.
        raise typer.Exit(code=75)
    if result.get("errors"):
        raise typer.Exit(code=1)


def apply(
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max applications to submit."),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel browser workers."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for job selection."),
    model: str = typer.Option("composer-2.5", "--model", "-m", help="Agent model name."),
    agent_provider: str = typer.Option(
        None, "--agent-provider",
        help="Stage-6 agent: cursor-sdk (default), cursor-cli, claude.",
    ),
    continuous: bool = typer.Option(False, "--continuous", "-c", help="Run forever, polling for new jobs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without submitting (the default)."),
    live: bool = typer.Option(False, "--live", help="Actually submit applications (requires apply_enabled)."),
    headless: bool = typer.Option(False, "--headless", help="Run browsers in headless mode."),
    url: Optional[str] = typer.Option(None, "--url", help="Apply to a specific job URL."),
    gen: bool = typer.Option(False, "--gen", help="Generate prompt file for manual debugging instead of running."),
    mark_applied: Optional[str] = typer.Option(None, "--mark-applied", help="Manually mark a job URL as applied."),
    mark_failed: Optional[str] = typer.Option(None, "--mark-failed", help="Manually mark a job URL as failed (provide URL)."),
    fail_reason: Optional[str] = typer.Option(None, "--fail-reason", help="Reason for --mark-failed."),
    reset_failed: bool = typer.Option(False, "--reset-failed", help="Reset all failed jobs for retry."),
) -> None:
    """Launch auto-apply to submit job applications."""
    bootstrap()

    import os
    from jobwright.config import get_active_user_id
    from jobwright.users import is_apply_enabled

    if live and dry_run:
        console.print("[red]--live and --dry-run are mutually exclusive.[/red]")
        raise typer.Exit(code=2)
    # Dry-run unless the caller explicitly asked for --live. Never infer live.
    dry_run = not live

    active = get_active_user_id()
    if live and not is_apply_enabled(active):
        console.print(
            f"[red]Live apply disabled[/red] for user '{active}'.\n"
            f"Enable with: jobwright users set {active} --apply\n"
            "Finding + tailoring still work without apply."
        )
        raise typer.Exit(code=1)

    if agent_provider:
        os.environ["AGENT_PROVIDER"] = agent_provider

    import jobwright.config as config
    from jobwright.config import check_tier, get_agent_provider
    from jobwright.database import get_connection

    # --- Utility modes (no Chrome/Claude needed) ---

    if mark_applied:
        from jobwright.apply.launcher import mark_job
        mark_job(mark_applied, "applied")
        console.print(f"[green]Marked as applied:[/green] {mark_applied}")
        return

    if mark_failed:
        from jobwright.apply.launcher import mark_job
        mark_job(mark_failed, "failed", reason=fail_reason)
        console.print(f"[yellow]Marked as failed:[/yellow] {mark_failed} ({fail_reason or 'manual'})")
        return

    if reset_failed:
        from jobwright.apply.launcher import reset_failed as do_reset
        count = do_reset()
        console.print(f"[green]Reset {count} failed job(s) for retry.[/green]")
        return

    # --- Full apply mode ---

    # Check 1: Tier 3 required (agent + Chrome)
    check_tier(3, "auto-apply")

    # Check 2: Profile exists
    if not config.PROFILE_PATH.exists():
        console.print(
            "[red]Profile not found.[/red]\n"
            "Run [bold]jobwright init[/bold] to create your profile first."
        )
        raise typer.Exit(code=1)

    # Check 3: Tailored resumes exist (skip for --gen with --url)
    if not (gen and url):
        conn = get_connection()
        ready = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
        ).fetchone()[0]
        if ready == 0:
            console.print(
                "[red]No tailored resumes ready.[/red]\n"
                "Run [bold]jobwright run score tailor[/bold] first to prepare applications."
            )
            raise typer.Exit(code=1)

    if gen:
        from jobwright.apply.launcher import gen_prompt
        target = url or ""
        if not target:
            console.print("[red]--gen requires --url to specify which job.[/red]")
            raise typer.Exit(code=1)
        prompt_file = gen_prompt(target, min_score=min_score, model=model)
        if not prompt_file:
            console.print("[red]No matching job found for that URL.[/red]")
            raise typer.Exit(code=1)
        mcp_path = config.PROFILE_PATH.parent / ".mcp-apply-0.json"
        provider = get_agent_provider()
        console.print(f"[green]Wrote prompt to:[/green] {prompt_file}")
        console.print(f"\n[bold]Run manually ({provider}):[/bold]")
        if provider == "cursor-cli":
            console.print(
                f"  agent -p --trust --force --approve-mcps --workspace {config.APPLY_WORKER_DIR}/0 "
                f"$(cat {prompt_file})"
            )
        elif provider == "claude":
            console.print(
                f"  claude --model {model} -p "
                f"--mcp-config {mcp_path} "
                f"--permission-mode bypassPermissions < {prompt_file}"
            )
        else:
            console.print(f"  AGENT_PROVIDER=cursor-sdk jobwright apply --url {target}")
        return

    from jobwright.apply.launcher import main as apply_main

    effective_limit = limit if limit is not None else (0 if continuous else 1)

    console.print("\n[bold blue]Launching Auto-Apply[/bold blue]")
    console.print(f"  Limit:    {'unlimited' if continuous else effective_limit}")
    console.print(f"  Workers:  {workers}")
    console.print(f"  Provider: {get_agent_provider()}")
    console.print(f"  Model:    {model}")
    console.print(f"  Headless: {headless}")
    console.print(f"  Dry run:  {dry_run}")
    if url:
        console.print(f"  Target:   {url}")
    console.print()

    apply_main(
        limit=effective_limit,
        target_url=url,
        min_score=min_score,
        headless=headless,
        model=model,
        dry_run=dry_run,
        continuous=continuous,
        workers=workers,
    )
