"""Tests for markdown materials format helpers."""

from __future__ import annotations

from pathlib import Path


def test_assemble_resume_markdown_includes_headers():
    from jobwright.scoring.materials_format import assemble_resume_markdown

    profile = {
        "personal": {
            "full_name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-0100",
        }
    }
    data = {
        "title": "Operator",
        "summary": "Impact-focused leader.",
        "skills": {"Strategy": "OKRs"},
        "experience": [{"header": "Acme", "subtitle": "2020", "bullets": ["Built programs"]}],
        "projects": [],
        "education": "BA University",
    }
    md = assemble_resume_markdown(data, profile)
    assert md.startswith("# Jane Doe")
    assert "## SUMMARY" in md
    assert "## EXPERIENCE" in md
    assert "- Built programs" in md


def test_normalize_for_structured_parse_strips_markdown_headers():
    from jobwright.scoring.materials_format import normalize_for_structured_parse

    text = "# Jane Doe\n## SUMMARY\nHello"
    plain = normalize_for_structured_parse(text)
    assert plain.splitlines()[0] == "Jane Doe"
    assert "SUMMARY" in plain


def test_resolve_material_path_prefers_md(tmp_path: Path):
    from jobwright.scoring.materials_format import resolve_material_path

    legacy = tmp_path / "resume.txt"
    modern = tmp_path / "resume.md"
    modern.write_text("# Resume", encoding="utf-8")
    assert resolve_material_path(tmp_path / "resume.txt") == modern
    assert resolve_material_path(str(legacy)) == modern


def test_format_legacy_resume_markdown_adds_headers():
    from jobwright.scoring.materials_format import format_legacy_resume_markdown

    text = "Jane Doe\nOperator\njane@example.com\n\nSUMMARY\nImpact leader.\n\nEXPERIENCE\n- Built programs"
    md = format_legacy_resume_markdown(text)
    assert md.startswith("# Jane Doe")
    assert "## SUMMARY" in md
    assert "## EXPERIENCE" in md


def test_format_cover_letter_markdown_splits_single_block():
    from jobwright.scoring.materials_format import format_cover_letter_markdown

    text = (
        "Dear Hiring Manager, First paragraph sentence one. First paragraph sentence two. "
        "Second paragraph sentence one. Second paragraph sentence two. "
        "Third paragraph sentence one. Jane Doe"
    )
    md = format_cover_letter_markdown(text)
    assert md.startswith("Dear Hiring Manager,")
    assert md.count("\n\n") >= 3
    assert md.endswith("Jane Doe")


def test_format_material_preview_cover():
    from jobwright.scoring.materials_format import format_material_preview

    text = "Dear Hiring Manager,\n\nBody paragraph one.\n\nBody paragraph two."
    md = format_material_preview(text, "cover")
    assert "Dear Hiring Manager," in md
    assert "Body paragraph one." in md
