"""Base resume: PDF is the source of truth; markdown is derived for LLM stages."""

from __future__ import annotations

import logging
from pathlib import Path

from jobwright import config

log = logging.getLogger(__name__)


def pdf_to_markdown(pdf_path: Path) -> str:
    """Convert a PDF to markdown via pymupdf4llm."""
    import pymupdf4llm

    text = pymupdf4llm.to_markdown(str(pdf_path), use_ocr=False)
    if not isinstance(text, str):
        text = str(text)
    return text.strip() + "\n"


def cached_pdf_markdown(pdf_path: Path, md_path: Path) -> str:
    """Return markdown for ``pdf_path``, refreshing ``md_path`` when stale."""
    pdf = Path(pdf_path)
    cache = Path(md_path)
    if (
        cache.is_file()
        and cache.stat().st_mtime >= pdf.stat().st_mtime
        and cache.stat().st_size > 0
    ):
        return cache.read_text(encoding="utf-8")
    text = pdf_to_markdown(pdf)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(text, encoding="utf-8")
    log.info("Wrote derived markdown: %s", cache)
    return text


def load_resume_text() -> str:
    """Return markdown for scoring/tailoring.

    Prefers ``resume/base.pdf`` (converted, cached as ``resume/base.md``).
    Falls back to an existing markdown cache if the PDF is missing.
    """
    pdf = Path(config.RESUME_PDF_PATH)
    md_path = Path(config.RESUME_MD_PATH)

    if pdf.is_file():
        return cached_pdf_markdown(pdf, md_path)

    if md_path.is_file():
        return md_path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"No resume PDF at {pdf}. Add resume/base.pdf for this user."
    )
