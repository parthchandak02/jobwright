"""Materials lookup and gated file download."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from jobwright import config
from jobwright.database import get_connection
from jobwright.scoring.materials_format import (
    MaterialKind,
    format_material_preview,
    resolve_material_path,
)

router = APIRouter(prefix="/api", tags=["materials"])

# Cap preview text so the drawer stays scannable (~6–8 KB).
_PREVIEW_MAX_CHARS = 8000


def _allowed_roots() -> list[Path]:
    return [
        Path(config.APP_DIR).resolve(),
        Path(config.TAILORED_DIR).resolve(),
        Path(config.COVER_LETTER_DIR).resolve(),
        Path(config.NETWORK_DIR).resolve(),
        Path(config.LOG_DIR).resolve(),
    ]


def _assert_allowed(path: Path) -> Path:
    resolved = path.resolve()
    if not any(str(resolved).startswith(str(root)) for root in _allowed_roots()):
        raise HTTPException(403, "Access denied")
    if not resolved.is_file():
        raise HTTPException(404, "File not found")
    return resolved


def _load_manifest() -> dict | None:
    path = Path(config.APP_DIR) / "MATERIALS_MANIFEST_latest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_preview(path: str | None, kind: MaterialKind) -> str | None:
    """Read and format markdown/text for drawer preview; return None if missing/unreadable."""
    resolved = resolve_material_path(path)
    if not resolved:
        return None
    try:
        text = resolved.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    text = format_material_preview(text, kind)
    if not text:
        return None
    if len(text) > _PREVIEW_MAX_CHARS:
        return text[:_PREVIEW_MAX_CHARS].rstrip() + "\n…"
    return text


@router.get("/jobs/{url:path}/materials")
def job_materials(url: str) -> dict:
    url = unquote(url)
    conn = get_connection()
    row = conn.execute(
        "SELECT tailored_resume_path, tailored_resume_docx_path, "
        "cover_letter_path, cover_letter_docx_path, title, company, fit_score "
        "FROM jobs WHERE url = ?",
        (url,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")

    d = dict(row)
    manifest_entry = None
    manifest = _load_manifest()
    if manifest:
        for job in manifest.get("jobs") or []:
            if job.get("url") == url:
                manifest_entry = job
                break

    def _exists(p: str | None) -> bool:
        return bool(p) and Path(p).is_file()

    resume_md_path = resolve_material_path(d.get("tailored_resume_path"))
    cover_md_path = resolve_material_path(d.get("cover_letter_path"))
    resume_md = str(resume_md_path) if resume_md_path else None
    cover_md = str(cover_md_path) if cover_md_path else None

    return {
        "url": url,
        "title": d.get("title"),
        "company": d.get("company"),
        "fit_score": d.get("fit_score"),
        "resume_md": resume_md,
        "resume_docx": d.get("tailored_resume_docx_path") if _exists(d.get("tailored_resume_docx_path")) else None,
        "cover_md": cover_md,
        "cover_docx": d.get("cover_letter_docx_path") if _exists(d.get("cover_letter_docx_path")) else None,
        "resume_preview": _read_preview(d.get("tailored_resume_path"), "resume"),
        "cover_preview": _read_preview(d.get("cover_letter_path"), "cover"),
        "manifest": manifest_entry,
    }


@router.get("/download")
def download_file(path: str) -> FileResponse:
    resolved = _assert_allowed(Path(path))
    return FileResponse(
        str(resolved),
        filename=resolved.name,
        media_type="application/octet-stream",
    )
