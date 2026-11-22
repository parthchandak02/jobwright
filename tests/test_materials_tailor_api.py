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

        import jobwright.config as _cfg


        _cfg.set_app_dir(data_dir)
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


def test_tailor_missing_description_400(api_client, caplog):
    client, _ = api_client
    url = "https://example.com/no-desc"
    insert_manual_job(url, title="No Desc", company="TestCo", funnel_stage="prepare")
    with caplog.at_level("WARNING", logger="jobwright.web.routers.materials"):
        res = client.post(f"/api/jobs/{_enc(url)}/tailor")
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "No job description yet" in detail
    assert "enrichment" in detail.lower()
    assert "Prepare" in detail
    assert any(
        "no description yet" in r.message and "No Desc" in r.message and "TestCo" in r.message
        for r in caplog.records
    )


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


def test_tailor_auto_claims_once_per_day(api_client):
    client, _ = api_client
    url = "https://example.com/tailor-auto"
    insert_manual_job(
        url,
        title="Chief of Staff",
        company="TestCo",
        description="Chief of Staff role. Python, SQL, stakeholder management.",
        funnel_stage="prepare",
    )
    first = client.post(f"/api/jobs/{_enc(url)}/tailor", json={"auto": True})
    assert first.status_code == 200
    from jobwright.database import get_connection

    stamp = get_connection().execute(
        "SELECT prepare_auto_started_at FROM jobs WHERE url = ?", (url,)
    ).fetchone()[0]
    assert stamp
    second = client.post(f"/api/jobs/{_enc(url)}/tailor", json={"auto": True})
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "prepare_auto_already"
    # Manual Prepare still works after an auto claim.
    manual = client.post(f"/api/jobs/{_enc(url)}/tailor")
    assert manual.status_code == 200


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


def test_tailor_missing_base_resume_returns_400(api_client, caplog):
    client, data_dir = api_client
    for name in ("base.pdf", "base.md"):
        (data_dir / "resume" / name).unlink(missing_ok=True)
    url = "https://example.com/no-base-resume"
    insert_manual_job(
        url,
        title="Analyst",
        company="TestCo",
        description="Analyze operations metrics.",
        funnel_stage="prepare",
    )
    with caplog.at_level("WARNING", logger="jobwright.web.routers.materials"):
        res = client.post(f"/api/jobs/{_enc(url)}/tailor")
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "No base resume uploaded yet" in detail
    assert "Settings -> Documents" in detail
    assert "Prepare" in detail
    assert str(data_dir) not in detail
    assert any(
        "no base resume" in r.message and "Analyst" in r.message and "TestCo" in r.message
        for r in caplog.records
    )


def test_tailor_unreadable_base_resume_returns_400(api_client, caplog, monkeypatch):
    from jobwright.resume import ResumeUnreadableError

    client, data_dir = api_client
    url = "https://example.com/unreadable-base-resume"
    insert_manual_job(
        url,
        title="Strategist",
        company="TestCo",
        description="Lead strategic planning.",
        funnel_stage="prepare",
    )

    def _bad_resume():
        raise ResumeUnreadableError(f"The resume PDF at {data_dir / 'resume/base.pdf'} could not be read.")

    monkeypatch.setattr("jobwright.resume.load_resume_text", _bad_resume)
    with caplog.at_level("WARNING", logger="jobwright.web.routers.materials"):
        res = client.post(f"/api/jobs/{_enc(url)}/tailor")
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert "Your base resume PDF could not be read" in detail
    assert "Settings -> Documents" in detail
    assert "Prepare" in detail
    assert str(data_dir) not in detail
    assert any(
        "unreadable base resume" in r.message and "Strategist" in r.message and "TestCo" in r.message
        for r in caplog.records
    )


def test_job_materials_populates_previews_manifest_and_cover_pdf(api_client):
    import json

    from jobwright.database import get_connection

    client, data_dir = api_client
    assert client.get(f"/api/jobs/{_enc('https://example.com/nope')}/materials").status_code == 404
    assert client.get(f"/api/jobs/{_enc('https://example.com/nope')}/materials/cover.pdf").status_code == 404

    url = "https://example.com/full-materials"
    tailored_dir = data_dir / "tailored_resumes"
    cover_dir = data_dir / "cover_letters"
    tailored_dir.mkdir(parents=True, exist_ok=True)
    cover_dir.mkdir(parents=True, exist_ok=True)

    resume_md = tailored_dir / "role_resume.md"
    resume_docx = tailored_dir / "role_resume.docx"
    long_resume = "# Alex Rivera\n\n## Experience\n" + ("- Built analytics pipelines for operations teams.\n" * 200)
    resume_md.write_text(long_resume, encoding="utf-8")
    resume_docx.write_bytes(b"PK\x03\x04fake-docx")

    cover_md = cover_dir / "role_cover.md"
    cover_docx = cover_dir / "role_cover_export.docx"
    cover_pdf = cover_dir / "role_cover_export.pdf"
    cover_md.write_text("Dear Hiring Team,\n\nI would love to join TestCo.\n", encoding="utf-8")
    cover_docx.write_bytes(b"PK\x03\x04fake-cover-docx")
    cover_pdf.write_bytes(b"%PDF-1.4 cover")

    manifest_path = data_dir / "MATERIALS_MANIFEST_latest.json"
    manifest_path.write_text(
        json.dumps({"jobs": [{"url": "https://example.com/other"}, {"url": url, "status": "ready"}]}),
        encoding="utf-8",
    )

    insert_manual_job(url, title="Ops Lead", company="TestCo", description="Desc", funnel_stage="prepare")
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET tailored_resume_path = ?, tailored_resume_docx_path = ?, "
        "cover_letter_path = ?, cover_letter_docx_path = ?, fit_score = 9 WHERE url = ?",
        (str(resume_md), str(resume_docx), str(cover_md), str(cover_docx), url),
    )
    conn.commit()

    enc = _enc(url)
    res = client.get(f"/api/jobs/{enc}/materials")
    assert res.status_code == 200
    body = res.json()
    assert body["resume_md"] == str(resume_md)
    assert body["resume_docx"] == str(resume_docx)
    assert body["cover_md"] == str(cover_md)
    assert body["cover_docx"] == str(cover_docx)
    assert body["resume_pdf"] is None
    assert body["cover_pdf"] == str(cover_pdf)
    assert body["resume_preview"].startswith("# Alex Rivera")
    assert body["resume_preview"].endswith("\n\u2026")
    assert len(body["resume_preview"]) <= 8002
    assert "Dear Hiring Team" in body["cover_preview"]
    assert body["manifest"] == {"url": url, "status": "ready"}

    pdf_res = client.get(f"/api/jobs/{enc}/materials/cover.pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"].startswith("application/pdf")
    assert "cover_letter.pdf" in pdf_res.headers.get("content-disposition", "")
    assert pdf_res.content == b"%PDF-1.4 cover"

    # Malformed manifest file is ignored instead of breaking the drawer.
    manifest_path.write_text("{not valid json", encoding="utf-8")
    res_bad_manifest = client.get(f"/api/jobs/{enc}/materials")
    assert res_bad_manifest.status_code == 200
    assert res_bad_manifest.json()["manifest"] is None


def test_download_serves_generated_materials_and_blocks_outside_paths(api_client, tmp_path: Path):
    client, data_dir = api_client
    tailored_dir = data_dir / "tailored_resumes"
    cover_dir = data_dir / "cover_letters"
    tailored_dir.mkdir(parents=True, exist_ok=True)
    cover_dir.mkdir(parents=True, exist_ok=True)

    docx_file = tailored_dir / "Alex_Rivera_Resume.docx"
    docx_file.write_bytes(b"PK\x03\x04resume-bytes")
    pdf_file = cover_dir / "Alex_Rivera_Cover.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 cover-bytes")

    res = client.get("/api/download", params={"path": str(docx_file)})
    assert res.status_code == 200
    assert res.content == b"PK\x03\x04resume-bytes"
    assert "Alex_Rivera_Resume.docx" in res.headers.get("content-disposition", "")

    res_pdf = client.get("/api/download", params={"path": str(pdf_file)})
    assert res_pdf.status_code == 200
    assert res_pdf.content == b"%PDF-1.4 cover-bytes"

    # Missing file inside an allowed directory returns 404.
    missing = tailored_dir / "missing.pdf"
    assert client.get("/api/download", params={"path": str(missing)}).status_code == 404

    # Disallowed extension inside an allowed directory returns 403.
    json_in_tailored = tailored_dir / "secret.json"
    json_in_tailored.write_text("{}", encoding="utf-8")
    assert client.get("/api/download", params={"path": str(json_in_tailored)}).status_code == 403

    # Files outside tailored_resumes and cover_letters are always blocked with 403.
    profile_json = data_dir / "profile.json"
    profile_json.write_text("{}", encoding="utf-8")
    outside_pdf = tmp_path / "outside.pdf"
    outside_pdf.write_bytes(b"%PDF-1.4 outside")
    traversal = tailored_dir / ".." / "resume" / "base.pdf"
    for forbidden in (profile_json, data_dir / "jobwright.db", outside_pdf, traversal):
        assert client.get("/api/download", params={"path": str(forbidden)}).status_code == 403

