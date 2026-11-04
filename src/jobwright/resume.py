"""Base resume: PDF is the source of truth; markdown is derived for LLM stages."""

from __future__ import annotations

import logging
import os
import tempfile
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


MAX_PDF_BYTES = 10 * 1024 * 1024  # resume / cover-letter uploads


class PdfUploadError(ValueError):
    """An uploaded PDF was rejected; ``status`` is the HTTP status to answer with."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def read_upload(fileobj, limit: int = MAX_PDF_BYTES) -> bytes:
    """Read at most ``limit`` bytes of an upload; reject anything bigger."""
    data = fileobj.read(limit + 1)
    if len(data) > limit:
        raise PdfUploadError(f"That file is too big. The limit is {limit // (1024 * 1024)} MB.", status=413)
    return data


def save_pdf_with_markdown(data: bytes, pdf_path: Path, md_path: Path) -> str:
    """Validate an uploaded PDF, then replace ``pdf_path`` and its markdown cache.

    The new file is written and converted under temporary names first, so a
    corrupt or oversized upload leaves the previous PDF and markdown untouched.
    Returns the markdown.
    """
    if len(data) > MAX_PDF_BYTES:
        raise PdfUploadError(f"That file is too big. The limit is {MAX_PDF_BYTES // (1024 * 1024)} MB.", status=413)
    if not data.startswith(b"%PDF"):
        raise PdfUploadError("File is not a PDF")
    pdf_path = Path(pdf_path)
    md_path = Path(md_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_pdf_name = tempfile.mkstemp(prefix=".upload-", suffix=".pdf", dir=str(pdf_path.parent))
    tmp_pdf = Path(tmp_pdf_name)
    tmp_md = md_path.with_name(f".{tmp_pdf.stem}.md")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            text = pdf_to_markdown(tmp_pdf)
        except Exception as exc:  # noqa: BLE001 - pymupdf raises many types for bad files
            raise PdfUploadError("Could not read that PDF. Try exporting it again.") from exc
        # Written after the PDF, so the cache is never older than the PDF it describes.
        tmp_md.write_text(text, encoding="utf-8")
        os.replace(tmp_pdf, pdf_path)
        os.replace(tmp_md, md_path)
    finally:
        for leftover in (tmp_pdf, tmp_md):
            try:
                leftover.unlink()
            except FileNotFoundError:
                pass
    return text


class ResumeUnreadableError(FileNotFoundError):
    """resume/base.pdf exists but can't be converted. Subclasses FileNotFoundError
    so every "no resume yet" handler also covers a broken file."""


def load_resume_text() -> str:
    """Return markdown for scoring/tailoring.

    Prefers ``resume/base.pdf`` (converted, cached as ``resume/base.md``).
    Falls back to an existing markdown cache if the PDF is missing.
    """
    pdf = Path(config.RESUME_PDF_PATH)
    md_path = Path(config.RESUME_MD_PATH)

    if pdf.is_file():
        try:
            return cached_pdf_markdown(pdf, md_path)
        except Exception as exc:  # noqa: BLE001 - pymupdf raises many types (IndexError on 0 pages)
            log.warning("could not convert resume PDF %s: %s", pdf, exc)
            raise ResumeUnreadableError(
                f"The resume PDF at {pdf} could not be read. Upload a new copy."
            ) from exc

    if md_path.is_file():
        return md_path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"No resume PDF at {pdf}. Add resume/base.pdf for this user."
    )
