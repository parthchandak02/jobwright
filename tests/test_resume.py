"""PDF resume is the source of truth; markdown is derived."""

from pathlib import Path

import pytest


def _write_pdf(path: Path, text: str) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    doc.save(path)
    doc.close()


def test_load_resume_text_converts_pdf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import jobwright.config as config
    from jobwright.resume import load_resume_text

    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    pdf = resume_dir / "base.pdf"
    md = resume_dir / "base.md"
    _write_pdf(pdf, "RICHA A. JATIA\nKellogg School of Management")

    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.setattr(config, "RESUME_DIR", resume_dir)
    monkeypatch.setattr(config, "RESUME_PDF_PATH", pdf)
    monkeypatch.setattr(config, "RESUME_MD_PATH", md)
    monkeypatch.setattr(config, "RESUME_PATH", md)

    text = load_resume_text()
    assert "RICHA" in text.upper() or "JATIA" in text.upper() or "Kellogg" in text
    assert md.is_file()
    cached = load_resume_text()
    assert cached == text


def test_load_resume_text_missing_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import jobwright.config as config
    from jobwright.resume import load_resume_text

    resume_dir = tmp_path / "resume"
    resume_dir.mkdir()
    monkeypatch.setattr(config, "RESUME_PDF_PATH", resume_dir / "base.pdf")
    monkeypatch.setattr(config, "RESUME_MD_PATH", resume_dir / "base.md")
    with pytest.raises(FileNotFoundError):
        load_resume_text()
