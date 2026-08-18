"""Subtle dashboard tailor should not hard-fail when the validator is picky."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobwright.database import close_connection, init_db, insert_manual_job
from jobwright.scoring.validator import validate_json_fields


def test_lenient_mode_missing_companies_are_warnings():
    profile = {
        "skills_boundary": {},
        "resume_facts": {
            "preserved_companies": ["IHCL (Tata)", "Quake Capital Partners"],
            "preserved_school": "Kellogg School of Management; NYU Stern",
        },
    }
    data = {
        "title": "Associate Director",
        "summary": "Ops leader for partnerships.",
        "skills": {"Tools": "Excel, Python"},
        "experience": [{"header": "Associate at Other Co", "bullets": ["Did work"]}],
        "projects": [{"header": "Ops dashboard", "bullets": ["Built a tracker"]}],
        "education": "Some School",
    }
    normal = validate_json_fields(data, profile, mode="normal")
    assert normal["passed"] is False
    assert any("IHCL" in e for e in normal["errors"])

    lenient = validate_json_fields(data, profile, mode="lenient")
    assert lenient["passed"] is True
    assert any("IHCL" in w for w in lenient["warnings"])


def test_lenient_empty_projects_is_warning_not_error():
    profile = {"skills_boundary": {}, "resume_facts": {}}
    data = {
        "title": "Ops",
        "summary": "Summary",
        "skills": {"Tools": "Excel"},
        "experience": [{"header": "Role at Co", "bullets": ["Did work"]}],
        "projects": [],
        "education": "School",
    }
    assert validate_json_fields(data, profile, mode="normal")["passed"] is False
    assert validate_json_fields(data, profile, mode="lenient")["passed"] is True


def test_subtle_tailor_persists_last_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    users_root = tmp_path / "users"
    data_dir = users_root / "richa"
    resume_dir = data_dir / "resume"
    tailored_dir = data_dir / "tailored_resumes"
    resume_dir.mkdir(parents=True)
    (resume_dir / "base.pdf").write_bytes(b"%PDF-1.4 x")
    (resume_dir / "base.md").write_text("Jane Doe\nIHCL (Tata)\n", encoding="utf-8")

    monkeypatch.setattr("jobwright.config.APP_DIR", data_dir)
    monkeypatch.setattr("jobwright.config.DB_PATH", data_dir / "jobwright.db")
    monkeypatch.setattr("jobwright.config.RESUME_DIR", resume_dir)
    monkeypatch.setattr("jobwright.config.RESUME_PDF_PATH", resume_dir / "base.pdf")
    monkeypatch.setattr("jobwright.config.RESUME_MD_PATH", resume_dir / "base.md")
    monkeypatch.setattr("jobwright.config.TAILORED_DIR", tailored_dir)
    monkeypatch.setattr("jobwright.config.COVER_LETTER_DIR", data_dir / "cover_letters")

    close_connection(data_dir / "jobwright.db")
    init_db(data_dir / "jobwright.db")
    url = "https://example.com/job-subtle"
    insert_manual_job(
        url,
        title="Associate Director",
        company="Moderna",
        description="Partnerships role in London.",
        funnel_stage="prepare",
    )

    def fake_tailor_resume(resume_text, job, profile, **kwargs):
        return (
            "# Jane Doe\n\n## EXPERIENCE\nIHCL (Tata)\n",
            {
                "attempts": 4,
                "status": "failed_validation",
                "validator": {"passed": False, "errors": ["Company missing"], "warnings": []},
                "judge": None,
            },
        )

    monkeypatch.setattr("jobwright.scoring.tailor.tailor_resume", fake_tailor_resume)
    monkeypatch.setattr("jobwright.scoring.tailor.load_profile", lambda: {})

    from jobwright.scoring.tailor import tailor_one_job

    result = tailor_one_job(url, subtle=True, validation_mode="normal")
    assert result["status"] == "approved_with_judge_warning"
    assert result["path"]
    assert Path(result["path"]).is_file()
    close_connection(data_dir / "jobwright.db")


def test_dashboard_prompt_includes_user_instructions():
    from jobwright.scoring.tailor_instructions import build_dashboard_resume_prompt

    prompt = build_dashboard_resume_prompt(
        {"resume_facts": {}, "experience": {}},
        "Put Python first. Do not rewrite bullets.",
    )
    assert "Put Python first. Do not rewrite bullets." in prompt
    assert "USER INSTRUCTIONS:" in prompt
