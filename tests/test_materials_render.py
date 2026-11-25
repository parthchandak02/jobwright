"""Tailored resume text becomes the HTML and DOCX people submit.

PDF bytes need Chromium, so these tests stop at the HTML (html_only) and at
the Word file. Expected strings are the fixture text, not a second parser.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jobwright.scoring import pdf as pdf_mod
from jobwright.scoring.docx_export import material_to_docx
from jobwright.scoring.materials_format import normalize_for_structured_parse
from jobwright.scoring.pdf import build_html, parse_entries, parse_resume, parse_skills

RESUME_MD = """# Alex Rivera
Program Manager
Oakland, CA
alex@example.com | 415-555-0100 | linkedin.com/in/alex

## SUMMARY
Operator who runs grant programs.

## TECHNICAL SKILLS
Strategy: OKRs, roadmaps
Tools: Excel, SQL

## EXPERIENCE
Example Org, Program Manager
2019 - 2024 | Oakland
- Led a grant program that paid 40 partners
- Hired four program staff

Other Org, Advisor
2024 - Present
\u2022 Built the quarterly board pack

## PROJECTS
Grant Tracker
Excel
- Tracked 40 open grants

## EDUCATION
BA, Example State University
"""


def _plain() -> str:
    return normalize_for_structured_parse(RESUME_MD)


def _html() -> str:
    return build_html(parse_resume(_plain()))


def _docx_text(path: Path) -> str:
    from docx import Document

    return "\n".join(p.text for p in Document(str(path)).paragraphs)


def test_header_with_location_and_contact():
    parsed = parse_resume(_plain())
    assert parsed["name"] == "Alex Rivera"
    assert parsed["title"] == "Program Manager"
    assert parsed["location"] == "Oakland, CA"
    assert parsed["contact"] == "alex@example.com | 415-555-0100 | linkedin.com/in/alex"
    assert set(parsed["sections"]) == {
        "SUMMARY",
        "TECHNICAL SKILLS",
        "EXPERIENCE",
        "PROJECTS",
        "EDUCATION",
    }


def test_three_line_header_with_email_is_contact_not_location():
    text = "Alex Rivera\nProgram Manager\nalex@example.com | 415-555-0100\n\nSUMMARY\nShort.\n"
    parsed = parse_resume(text)
    assert parsed["location"] == ""
    assert parsed["contact"] == "alex@example.com | 415-555-0100"
    assert "<div class=\"location\">" not in build_html(parsed)


def test_three_line_header_without_email_is_location():
    text = "Alex Rivera\nProgram Manager\nOakland, CA\n\nSUMMARY\nShort.\n"
    parsed = parse_resume(text)
    assert parsed["location"] == "Oakland, CA"
    assert parsed["contact"] == ""
    assert '<div class="location">Oakland, CA</div>' in build_html(parsed)


def test_skills_split_once_and_skip_lines_without_a_colon():
    skills = parse_skills(parse_resume(_plain())["sections"]["TECHNICAL SKILLS"])
    assert skills == [("Strategy", "OKRs, roadmaps"), ("Tools", "Excel, SQL")]
    assert parse_skills("Tools: Excel: advanced, SQL\nJust a note\n") == [
        ("Tools", "Excel: advanced, SQL"),
    ]


def test_experience_keeps_a_second_role_and_a_bullet_character():
    entries = parse_entries(parse_resume(_plain())["sections"]["EXPERIENCE"])
    assert entries == [
        {
            "title": "Example Org, Program Manager",
            "subtitle": "2019 - 2024 | Oakland",
            "bullets": [
                "Led a grant program that paid 40 partners",
                "Hired four program staff",
            ],
        },
        {
            "title": "Other Org, Advisor",
            "subtitle": "2024 - Present",
            "bullets": ["Built the quarterly board pack"],
        },
    ]
    projects = parse_entries(parse_resume(_plain())["sections"]["PROJECTS"])
    assert projects == [
        {
            "title": "Grant Tracker",
            "subtitle": "Excel",
            "bullets": ["Tracked 40 open grants"],
        }
    ]


def test_shouted_bullet_stays_under_the_role():
    # The date line needs a lowercase word. A line with no lowercase letters
    # ("2019 - 2024") is read as a new section header, not a subtitle.
    text = (
        "Alex Rivera\n\nSUMMARY\nShort.\n\nEXPERIENCE\n"
        "Example Org\n2019 - Present\n- SHIPPED THE BOARD PACK\n"
    )
    entries = parse_entries(parse_resume(text)["sections"]["EXPERIENCE"])
    assert entries == [
        {
            "title": "Example Org",
            "subtitle": "2019 - Present",
            "bullets": ["SHIPPED THE BOARD PACK"],
        }
    ]


def test_html_keeps_every_section_in_resume_order():
    html = _html()
    assert '<div class="name">Alex Rivera</div>' in html
    assert '<div class="title">Program Manager</div>' in html
    assert "alex@example.com &nbsp;|&nbsp; 415-555-0100 &nbsp;|&nbsp; linkedin.com/in/alex" in html
    assert '<span class="skill-cat">Strategy:</span> OKRs, roadmaps' in html
    assert "<li>Led a grant program that paid 40 partners</li>" in html
    assert "<li>Hired four program staff</li>" in html
    assert "<li>Built the quarterly board pack</li>" in html
    assert '<div class="entry-title">Other Org, Advisor</div>' in html
    assert "<li>Tracked 40 open grants</li>" in html
    assert "BA, Example State University" in html
    order = [
        "Operator who runs grant programs.",
        "Strategy:",
        "Led a grant program that paid 40 partners",
        "Tracked 40 open grants",
        "Example State University",
    ]
    positions = [html.index(piece) for piece in order]
    assert positions == sorted(positions)


def test_convert_to_pdf_html_only_writes_that_html(tmp_path: Path):
    src = tmp_path / "resume.md"
    src.write_text(RESUME_MD, encoding="utf-8")
    out = pdf_mod.convert_to_pdf(src, html_only=True)
    assert out == src.with_suffix(".html")
    text = out.read_text(encoding="utf-8")
    assert "Alex Rivera" in text
    assert "Led a grant program that paid 40 partners" in text
    assert "Tracked 40 open grants" in text
    explicit = tmp_path / "card.html"
    written = pdf_mod.convert_to_pdf(src, output_path=explicit, html_only=True)
    assert written == explicit
    assert "Hired four program staff" in explicit.read_text(encoding="utf-8")


def test_convert_to_pdf_missing_file(tmp_path: Path):
    missing = tmp_path / "no-such-resume.md"
    with pytest.raises(FileNotFoundError, match="no-such-resume.md"):
        pdf_mod.convert_to_pdf(missing, html_only=True)


def test_docx_resume_contains_the_same_facts(tmp_path: Path):
    src = tmp_path / "resume.md"
    src.write_text(RESUME_MD, encoding="utf-8")
    text = _docx_text(material_to_docx(src))
    for piece in (
        "Alex Rivera",
        "Program Manager",
        "Oakland, CA",
        "alex@example.com",
        "Strategy: OKRs, roadmaps",
        "Led a grant program that paid 40 partners",
        "Hired four program staff",
        "Other Org, Advisor",
        "Built the quarterly board pack",
        "Tracked 40 open grants",
        "BA, Example State University",
    ):
        assert piece in text, piece


def test_docx_cover_letter_keeps_every_paragraph(tmp_path: Path):
    from docx import Document

    src = tmp_path / "letter.md"
    src.write_text(
        "Dear Hiring Manager,\n\n"
        "I led the grant program at Example Org.\n\n"
        "At Other Org, I built the quarterly board pack.\n\n"
        "I would welcome the chance to discuss the role.\n\n"
        "Best,\n"
        "Alex Rivera\n",
        encoding="utf-8",
    )
    doc = Document(str(material_to_docx(src)))
    paragraphs = [p.text for p in doc.paragraphs]
    assert paragraphs == [
        "Dear Hiring Manager,",
        "I led the grant program at Example Org.",
        "At Other Org, I built the quarterly board pack.",
        "I would welcome the chance to discuss the role.",
        "Best,\nAlex Rivera",
    ]


def test_convert_to_pdf_cover_letter_renders_paragraphs_not_resume_header(tmp_path: Path):
    src = tmp_path / "letter_CL.md"
    src.write_text(
        "Dear Hiring Manager,\n\n"
        "I led the grant program at Example Org.\n\n"
        "At Other Org, I built the quarterly board pack.\n\n"
        "I would welcome the chance to discuss the role.\n\n"
        "Best,\n"
        "Alex Rivera\n",
        encoding="utf-8",
    )
    out = pdf_mod.convert_to_pdf(src, html_only=True)
    html = out.read_text(encoding="utf-8")
    assert '<div class="header">' not in html
    assert '<div class="name">' not in html
    for piece in (
        "Dear Hiring Manager,",
        "I led the grant program at Example Org.",
        "At Other Org, I built the quarterly board pack.",
        "I would welcome the chance to discuss the role.",
        "Best,<br>Alex Rivera",
    ):
        assert piece in html, piece



def test_batch_convert_skips_covers_sidecars_and_existing_pdfs(monkeypatch, tmp_path: Path):
    from jobwright import config

    tailored = tmp_path / "tailored"
    tailored.mkdir()
    monkeypatch.setattr(config._state(), "TAILORED_DIR", tailored)
    (tailored / "a_role.md").write_text(RESUME_MD, encoding="utf-8")
    (tailored / "b_role.md").write_text(RESUME_MD, encoding="utf-8")
    (tailored / "b_role.pdf").write_bytes(b"%PDF")
    (tailored / "c_role_CL.md").write_text("Dear Hiring Manager,\n\nBody.\n", encoding="utf-8")
    (tailored / "c_role_CL.txt").write_text("legacy cover", encoding="utf-8")
    (tailored / "notes_JOB.txt").write_text("sidecar", encoding="utf-8")
    (tailored / "legacy.txt").write_text("Alex Rivera\n\nSUMMARY\nShort.\n", encoding="utf-8")
    seen: list[str] = []

    def fake_convert(path, output_path=None, html_only=False):
        seen.append(Path(path).name)
        if Path(path).name == "bad.md":
            raise RuntimeError("render failed")
        return Path(path).with_suffix(".pdf")

    (tailored / "bad.md").write_text(RESUME_MD, encoding="utf-8")
    monkeypatch.setattr(pdf_mod, "convert_to_pdf", fake_convert)
    # md files sort before txt. a_role and bad are missing PDFs; b_role already has one.
    assert pdf_mod.batch_convert() == 2
    assert seen == ["a_role.md", "bad.md", "legacy.txt"]
    assert pdf_mod.batch_convert(limit=1) == 1
    assert seen[-1] == "a_role.md"


def test_numeric_date_range_subtitle_keeps_experience_bullets_and_later_roles():
    text = (
        "# Alex Rivera\nProduct Manager\nalex@example.com\n\n"
        "## SUMMARY\nOperator shipping data products.\n\n"
        "## EXPERIENCE\n"
        "Example Org, Senior PM\n2019 - 2024\n- Launched billing platform\n\n"
        "Earlier Org, PM\n2017 - 2019\n- Grew retention by 15%\n"
    )
    parsed = parse_resume(normalize_for_structured_parse(text))
    assert list(parsed["sections"]) == ["SUMMARY", "EXPERIENCE"]
    assert parse_entries(parsed["sections"]["EXPERIENCE"]) == [
        {"title": "Example Org, Senior PM", "subtitle": "2019 - 2024", "bullets": ["Launched billing platform"]},
        {"title": "Earlier Org, PM", "subtitle": "2017 - 2019", "bullets": ["Grew retention by 15%"]},
    ]
    html = build_html(parsed)
    assert "Launched billing platform" in html
    assert "Earlier Org, PM" in html


def test_resume_without_summary_does_not_leak_sections_into_header():
    text = "# Alex Rivera\nProduct Manager\n\n## EXPERIENCE\nExample Org\n2020 - Present\n- Built core workflows\n"
    parsed = parse_resume(normalize_for_structured_parse(text))
    assert parsed["name"] == "Alex Rivera"
    assert parsed["title"] == "Product Manager"
    assert parsed["location"] == ""
    assert parsed["contact"] == ""
    assert "EXPERIENCE" in parsed["sections"]


def test_build_html_and_mupdf_escape_angle_brackets_and_ampersands(tmp_path: Path):
    import pymupdf

    src = tmp_path / "special_chars.md"
    src.write_text(
        "# Alex Rivera\nR&D Lead\nalex@example.com\n\n"
        "## SUMMARY\nBuilt <internal> analytics and P&L tools.\n\n"
        "## TECHNICAL SKILLS\nCloud: AWS & GCP\n\n"
        "## EXPERIENCE\nAT&T, Senior Engineer\n2020 - 2024\n"
        "- Reduced p99 latency <50ms with >99.9% uptime\n"
        "- Shipped migration in <a week for core billing\n",
        encoding="utf-8",
    )
    html = pdf_mod.convert_to_pdf(src, html_only=True).read_text(encoding="utf-8")
    assert "&lt;internal&gt;" in html
    assert "&lt;50ms" in html
    assert "&lt;a week" in html
    assert "AT&amp;T" in html

    pdf_out = tmp_path / "special_chars.pdf"
    pdf_mod._render_mupdf(html, str(pdf_out))
    rendered = "\n".join(page.get_text() for page in pymupdf.open(str(pdf_out)))
    assert "<internal>" in rendered
    assert "<50ms" in rendered
    assert "Shipped migration in <a week for core billing" in rendered
    assert "AT&T, Senior Engineer" in rendered

