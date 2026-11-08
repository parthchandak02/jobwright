"""Pipeline commands: `init`, `run` (`apply` lives in apply_cmds)."""

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
