"""Per-job materials and research: `tailor-job`, `network`, `targets`."""

from __future__ import annotations

from typing import Optional

import typer

from jobwright.cli._common import bootstrap, console


def tailor_job(
    url: str = typer.Option(..., "--url", help="Job URL to tailor resume and cover letter for."),
    verbose: bool = typer.Option(True, "--verbose", "-v", help="DEBUG logs to stdout."),
    validation: str = typer.Option("lenient", "--validation"),
    resume_instructions_file: Optional[str] = typer.Option(
        None, "--resume-instructions-file", help="Override resume tailor instructions (text file).",
    ),
    cover_instructions_file: Optional[str] = typer.Option(
        None, "--cover-instructions-file", help="Override cover letter instructions (text file).",
    ),
    resume_only: bool = typer.Option(
        False, "--resume-only", help="Tailor resume and export DOCX only.",
    ),
    cover_only: bool = typer.Option(
        False, "--cover-only", help="Generate cover letter and export DOCX only.",
    ),
) -> None:
    """Tailor resume + cover letter for one job (dashboard / verbose logs)."""
    import os
    from pathlib import Path

    if resume_only and cover_only:
        raise typer.BadParameter("Use only one of --resume-only or --cover-only.")
    if verbose:
        os.environ["JOBWRIGHT_LOG_LEVEL"] = "DEBUG"
    bootstrap()
    from jobwright.config import check_tier

    check_tier(2, "AI scoring/tailoring")
    from jobwright.scoring.tailor import (
        run_single_job_cover,
        run_single_job_materials,
        run_single_job_resume,
    )

    def _read_opt(path: str | None) -> str | None:
        if not path:
            return None
        p = Path(path)
        if not p.is_file():
            raise typer.BadParameter(f"Instructions file not found: {path}")
        return p.read_text(encoding="utf-8")

    resume_instr = _read_opt(resume_instructions_file)
    cover_instr = _read_opt(cover_instructions_file)
    if resume_only:
        rc = run_single_job_resume(url, validation_mode=validation, resume_instructions=resume_instr)
    elif cover_only:
        rc = run_single_job_cover(url, validation_mode=validation, cover_instructions=cover_instr)
    else:
        rc = run_single_job_materials(
            url,
            validation_mode=validation,
            resume_instructions=resume_instr,
            cover_instructions=cover_instr,
        )
    raise typer.Exit(code=rc)


def network(
    top: int = typer.Option(25, "--top", "-n", help="How many contacts to keep."),
    csv: Optional[str] = typer.Option(
        None, "--csv",
        help="Path to LinkedIn Connections.csv (default: <data_dir>/connections.csv).",
    ),
) -> None:
    """Rank LinkedIn 1st-degree contacts from an exported Connections.csv (no scraping)."""
    bootstrap()
    from jobwright.config import check_tier
    from pathlib import Path

    check_tier(2, "network ranking")
    from jobwright.network.rank import run_network_rank

    try:
        result = run_network_rank(
            top_n=top,
            csv_path=Path(csv) if csv else None,
        )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    console.print(result["digest"])
    console.print(
        f"\n[dim]Saved {result['ranked']}/{result['contacts']} → "
        f"{result['txt_path']}[/dim]"
    )


def targets(
    limit: int = typer.Option(30, "--limit", "-n", help="Max companies to generate."),
    merge: bool = typer.Option(
        False, "--merge-searches",
        help="Also write company names into searches.yaml target_companies.",
    ),
) -> None:
    """Build a ranked target-company list from the active profile (LLM)."""
    bootstrap()
    from jobwright.config import check_tier

    check_tier(2, "target company list")
    from jobwright.targets.build import run_targets

    result = run_targets(limit=limit, merge_into_searches=merge)
    console.print(result["digest"])
    console.print(
        f"\n[dim]Saved {result['count']} companies → {result['yaml_path']}[/dim]"
    )
