"""Tests for DOCX export from structured resume markdown."""

from __future__ import annotations

from pathlib import Path


SAMPLE_RESUME_MD = """# Jane Doe
Chief of Staff
San Francisco, CA
jane@example.com | linkedin.com/in/jane

## SUMMARY
Impact-focused operator with partnership experience.

## TECHNICAL SKILLS
Strategy: OKRs, roadmap planning
Tools: Notion, Slack

## EXPERIENCE
Acme Corp — Chief of Staff
2020 - Present
- Led cross-functional initiatives
- Built partner programs

## EDUCATION
BA, Something University
"""


def test_material_to_docx_roundtrip(tmp_path: Path):
    from jobwright.scoring.docx_export import material_to_docx

    md = tmp_path / "resume.md"
    md.write_text(SAMPLE_RESUME_MD, encoding="utf-8")
    out = material_to_docx(md)
    assert out.exists()
    assert out.suffix == ".docx"
    assert out.stat().st_size > 1000


def test_material_to_docx_plain_cover(tmp_path: Path):
    from jobwright.scoring.docx_export import material_to_docx

    md = tmp_path / "cover.md"
    md.write_text(
        "Dear Hiring Manager,\n\nI am excited about this role.\n\nBest,\nJane\n",
        encoding="utf-8",
    )
    out = material_to_docx(md)
    assert out.exists()
    assert out.suffix == ".docx"
