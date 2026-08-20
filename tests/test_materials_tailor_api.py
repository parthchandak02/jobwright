"""Tests for per-job tailor endpoint (POST /api/jobs/{url}/tailor)."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import quote

import pytest

from jobwright.database import close_connection, init_db, insert_manual_job


@pytest.fixture()
def api_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("JOBWRIGHT_DASHBOARD_USER", "testdash")
    monkeypatch.setenv("JOBWRIGHT_USERS_ROOT", str(tmp_path / "users"))
    users_root = tmp_path / "users"
    users_root.mkdir()
    (users_root / "users.yaml").write_text(
        "users:\n  - user_id: testdash\n    name: Test\n    apply_enabled: false\n",
        encoding="utf-8",
    )
    data_dir = users_root / "testdash"
    data_dir.mkdir()
    resume_dir = data_dir / "resume"
    resume_dir.mkdir()
    (resume_dir / "base.pdf").write_bytes(b"%PDF-1.4 minimal")
    (resume_dir / "base.md").write_text("Jane Doe\nOps leader with Python experience.\n", encoding="utf-8")
    log_dir = data_dir / "logs"

    monkeypatch.setattr("jobwright.config.APP_DIR", data_dir)
    monkeypatch.setattr("jobwright.config.DB_PATH", data_dir / "jobwright.db")
    monkeypatch.setattr("jobwright.config.RESUME_DIR", resume_dir)
    monkeypatch.setattr("jobwright.config.RESUME_PDF_PATH", resume_dir / "base.pdf")
    monkeypatch.setattr("jobwright.config.RESUME_MD_PATH", resume_dir / "base.md")
    monkeypatch.setattr("jobwright.config.TAILORED_DIR", data_dir / "tailored_resumes")
    monkeypatch.setattr("jobwright.config.COVER_LETTER_DIR", data_dir / "cover_letters")
    monkeypatch.setattr("jobwright.config.NETWORK_DIR", data_dir / "network")
    monkeypatch.setattr("jobwright.config.LOG_DIR", log_dir)

    import jobwright.users as users_mod

    monkeypatch.setattr(users_mod, "USERS_ROOT", users_root)
    monkeypatch.setattr(users_mod, "REGISTRY_PATH", users_root / "users.yaml")

    def _fake_cmd(args, user_id):  # noqa: ANN001, ANN202
        return [sys.executable, "-c", "import time; time.sleep(30)"]

    monkeypatch.setattr("jobwright.web.routers.runs._jobwright_cmd", _fake_cmd)

    close_connection(data_dir / "jobwright.db")
    init_db(data_dir / "jobwright.db")

    from jobwright.web.app import app
    from jobwright.web.routers import runs as runs_mod

    with TestClient(app) as client:
        yield client, data_dir

    for info in list(runs_mod._runs.values()):
        proc = info.get("proc")
        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=3)
            except Exception:
                pass
    runs_mod._runs.clear()
    close_connection(data_dir / "jobwright.db")


def _enc(url: str) -> str:
    return quote(url, safe="")


def test_tailor_missing_job_404(api_client):
    client, _ = api_client
    url = "https://example.com/missing"
    res = client.post(f"/api/jobs/{_enc(url)}/tailor")
    assert res.status_code == 404
    assert res.json()["detail"] == "Job not found"


def test_tailor_missing_description_400(api_client):
    client, _ = api_client
    url = "https://example.com/no-desc"
    insert_manual_job(url, title="No Desc", company="TestCo", funnel_stage="prepare")
    res = client.post(f"/api/jobs/{_enc(url)}/tailor")
    assert res.status_code == 400
    assert res.json()["detail"] == "Job description required"


def test_tailor_starts_logged_run(api_client):
    client, _ = api_client
    url = "https://example.com/tailor-ok"
    insert_manual_job(
        url,
        title="Chief of Staff",
        company="TestCo",
        description="Chief of Staff role. Python, SQL, stakeholder management.",
        funnel_stage="prepare",
    )
    res = client.post(f"/api/jobs/{_enc(url)}/tailor")
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"]
    assert body["pid"]
    assert body["kind"] == "tailor"
    assert body["stages"] == ["tailor", "cover", "docx"]
    assert body["url"] == url
    assert Path(body["log_path"]).exists()


def test_tailor_defaults_match_instruction_module(api_client):
    from jobwright.scoring.tailor_instructions import (
        DEFAULT_COVER_INSTRUCTIONS,
        DEFAULT_RESUME_INSTRUCTIONS,
    )

    client, _ = api_client
    res = client.get("/api/tailor/defaults")
    assert res.status_code == 200
    body = res.json()
    assert body["resume_instructions"] == DEFAULT_RESUME_INSTRUCTIONS
    assert body["cover_instructions"] == DEFAULT_COVER_INSTRUCTIONS


def test_tailor_custom_instructions_written(api_client):
    client, data_dir = api_client
    url = "https://example.com/tailor-custom"
    insert_manual_job(
        url,
        title="Chief of Staff",
        company="TestCo",
        description="Chief of Staff role. Python, SQL, stakeholder management.",
        funnel_stage="prepare",
    )
    resume_instr = "Keep every role. Put Python first in skills."
    cover_instr = "Name TestCo. Keep it under 200 words."
    res = client.post(
        f"/api/jobs/{_enc(url)}/tailor",
        json={"resume_instructions": resume_instr, "cover_instructions": cover_instr},
    )
    assert res.status_code == 200
    log_dir = data_dir / "logs"
    resume_files = list(log_dir.glob("tailor_resume_instr_*.txt"))
    cover_files = list(log_dir.glob("tailor_cover_instr_*.txt"))
    assert resume_files
    assert cover_files
    assert resume_instr in resume_files[-1].read_text(encoding="utf-8")
    assert cover_instr in cover_files[-1].read_text(encoding="utf-8")


def test_job_materials_pdf_inline(api_client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, data_dir = api_client
    url = "https://example.com/tailor-pdf-preview"
    tailored_dir = data_dir / "tailored_resumes"
    tailored_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = tailored_dir / "manual_test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    md_path = tailored_dir / "manual_test.md"
    md_path.write_text("# Tailored\n", encoding="utf-8")

    insert_manual_job(
        url,
        title="Test",
        company="Co",
        description="Role description here.",
        funnel_stage="prepare",
    )
    from jobwright.database import get_connection

    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET tailored_resume_path = ? WHERE url = ?",
        (str(md_path), url),
    )
    conn.commit()

    enc = _enc(url)
    res = client.get(f"/api/jobs/{enc}/materials/resume.pdf")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/pdf")
    assert "inline" in res.headers.get("content-disposition", "").lower()
    assert res.content.startswith(b"%PDF")


def test_tailor_resume_only_starts_logged_run(api_client):
    client, _ = api_client
    url = "https://example.com/tailor-resume-only"
    insert_manual_job(
        url,
        title="Chief of Staff",
        company="TestCo",
        description="Chief of Staff role. Python, SQL, stakeholder management.",
        funnel_stage="prepare",
    )
    res = client.post(f"/api/jobs/{_enc(url)}/tailor/resume")
    assert res.status_code == 200
    body = res.json()
    assert body["stages"] == ["tailor", "docx"]
    assert body["kind"] == "tailor_resume"


def test_tailor_cover_only_starts_logged_run(api_client):
    client, _ = api_client
    url = "https://example.com/tailor-cover-only"
    insert_manual_job(
        url,
        title="Chief of Staff",
        company="TestCo",
        description="Chief of Staff role. Python, SQL, stakeholder management.",
        funnel_stage="prepare",
    )
    res = client.post(f"/api/jobs/{_enc(url)}/tailor/cover")
    assert res.status_code == 200
    body = res.json()
    assert body["stages"] == ["cover", "docx"]
    assert body["kind"] == "tailor_cover"
