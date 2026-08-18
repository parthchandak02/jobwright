"""Tests for DOCX export from structured resume text."""

from __future__ import annotations

from pathlib import Path


SAMPLE_RESUME = """Jane Doe
Chief of Staff
San Francisco, CA
jane@example.com | linkedin.com/in/jane

SUMMARY
Impact-focused operator with partnership experience.

TECHNICAL SKILLS
Strategy: OKRs, roadmap planning
Tools: Notion, Slack

EXPERIENCE
Acme Corp — Chief of Staff
2020 - Present
- Led cross-functional initiatives
- Built partner programs

EDUCATION
BA, Something University
"""


def test_txt_to_docx_roundtrip(tmp_path: Path):
    from jobwright.scoring.docx_export import txt_to_docx

    txt = tmp_path / "resume.txt"
    txt.write_text(SAMPLE_RESUME, encoding="utf-8")
    out = txt_to_docx(txt)
    assert out.exists()
    assert out.suffix == ".docx"
    assert out.stat().st_size > 1000


def test_txt_to_docx_plain_cover(tmp_path: Path):
    from jobwright.scoring.docx_export import txt_to_docx

    txt = tmp_path / "cover.txt"
    txt.write_text(
        "Dear Hiring Manager,\n\nI am excited about this role.\n\nBest,\nJane\n",
        encoding="utf-8",
    )
    out = txt_to_docx(txt)
    assert out.exists()
    assert out.suffix == ".docx"
