"""Cover letter PDF examples: conversion, amalgamation, settings API."""

from __future__ import annotations

from pathlib import Path

import pytest


def _write_pdf(path: Path, text: str) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_load_cover_letter_materials_reads_pdf_and_ignores_txt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from jobwright import config

    examples = tmp_path / "cover-letter" / "examples"
    examples.mkdir(parents=True)
    _write_pdf(examples / "dasra.pdf", "Dear hiring team at Dasra")
    (examples / "dasra.txt").write_text("OLD TXT SHOULD BE SKIPPED", encoding="utf-8")
    (examples / "wellspring.txt").write_text("Hello Wellspring team", encoding="utf-8")

    monkeypatch.setattr(config, "COVER_LETTER_EXAMPLES_DIR", examples)
    monkeypatch.setattr(config, "COVER_LETTER_TEMPLATE_PATH", tmp_path / "missing.pdf")
    monkeypatch.setattr(config, "REFERENCES_DIR", tmp_path / "references")

    template, bodies = config.load_cover_letter_materials()
    assert template == ""
    joined = "\n".join(bodies)
    assert "Dasra" in joined
    assert "OLD TXT" not in joined
    assert "Wellspring" not in joined


def test_join_cover_letter_examples_caps_total():
    from jobwright.config import join_cover_letter_examples

    text = join_cover_letter_examples(
        ["AAAA" * 100, "BBBB" * 100],
        per_max=10,
        total_max=40,
    )
    assert "EXAMPLE 1" in text
    assert len(text) <= 50


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
    examples = data_dir / "cover-letter" / "examples"
    examples.mkdir(parents=True)
    resume_dir = data_dir / "resume"
    resume_dir.mkdir()

    monkeypatch.setattr("jobwright.config.APP_DIR", data_dir)
    monkeypatch.setattr("jobwright.config.DB_PATH", data_dir / "jobwright.db")
    monkeypatch.setattr("jobwright.config.PROFILE_PATH", data_dir / "profile.json")
    monkeypatch.setattr("jobwright.config.SEARCH_CONFIG_PATH", data_dir / "searches.yaml")
    monkeypatch.setattr("jobwright.config.RESUME_DIR", resume_dir)
    monkeypatch.setattr("jobwright.config.RESUME_PDF_PATH", resume_dir / "base.pdf")
    monkeypatch.setattr("jobwright.config.RESUME_MD_PATH", resume_dir / "base.md")
    monkeypatch.setattr("jobwright.config.COVER_LETTER_EXAMPLES_DIR", examples)
    monkeypatch.setattr("jobwright.config.COVER_LETTER_INPUT_DIR", data_dir / "cover-letter")
    monkeypatch.setattr("jobwright.config.LOG_DIR", data_dir / "logs")

    import jobwright.users as users_mod

    monkeypatch.setattr(users_mod, "USERS_ROOT", users_root)
    monkeypatch.setattr(users_mod, "REGISTRY_PATH", users_root / "users.yaml")

    from jobwright.database import close_connection, init_db

    close_connection(data_dir / "jobwright.db")
    init_db(data_dir / "jobwright.db")

    from jobwright.web.app import app

    with TestClient(app) as client:
        yield client, examples
    close_connection(data_dir / "jobwright.db")


def test_cover_letter_example_upload_list_delete(api_client, tmp_path: Path):
    client, examples = api_client
    pdf_path = tmp_path / "letter.pdf"
    _write_pdf(pdf_path, "Cover letter for Community Impact")
    pdf_bytes = pdf_path.read_bytes()

    put = client.put(
        "/api/settings/cover-letters",
        files={"file": ("Community Impact.pdf", pdf_bytes, "application/pdf")},
    )
    assert put.status_code == 200, put.text
    example_id = put.json()["id"]
    assert example_id == "Community-Impact"
    assert (examples / f"{example_id}.pdf").is_file()

    listed = client.get("/api/settings")
    assert listed.status_code == 200
    items = listed.json()["cover_letter_examples"]
    assert len(items) == 1
    assert items[0]["id"] == example_id
    assert "Community" in items[0]["markdown"] or "Impact" in items[0]["markdown"]

    pdf_get = client.get(f"/api/settings/cover-letters/{example_id}/pdf")
    assert pdf_get.status_code == 200
    assert pdf_get.headers["content-type"].startswith("application/pdf")

    deleted = client.delete(f"/api/settings/cover-letters/{example_id}")
    assert deleted.status_code == 200
    assert not (examples / f"{example_id}.pdf").exists()
    missing = client.get(f"/api/settings/cover-letters/{example_id}/pdf")
    assert missing.status_code == 404


def test_cover_letter_examples_list_ignores_txt_files(api_client):
    client, examples = api_client
    (examples / "bridgespan.txt").write_text("Dear Bridgespan team\n", encoding="utf-8")
    (examples / "richa-1.txt").write_text("Dear hiring manager\n", encoding="utf-8")

    listed = client.get("/api/settings")
    assert listed.status_code == 200
    assert listed.json()["cover_letter_examples"] == []


def test_cover_letter_example_rejects_non_pdf(api_client):
    client, _examples = api_client
    put = client.put(
        "/api/settings/cover-letters",
        files={"file": ("note.txt", b"not a pdf", "text/plain")},
    )
    assert put.status_code == 400
