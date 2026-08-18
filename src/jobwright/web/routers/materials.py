"""Materials lookup and gated file download."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from jobwright import config
from jobwright.database import get_connection

router = APIRouter(prefix="/api", tags=["materials"])


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

    return {
        "url": url,
        "title": d.get("title"),
        "company": d.get("company"),
        "fit_score": d.get("fit_score"),
        "resume_txt": d.get("tailored_resume_path") if _exists(d.get("tailored_resume_path")) else None,
        "resume_docx": d.get("tailored_resume_docx_path") if _exists(d.get("tailored_resume_docx_path")) else None,
        "cover_txt": d.get("cover_letter_path") if _exists(d.get("cover_letter_path")) else None,
        "cover_docx": d.get("cover_letter_docx_path") if _exists(d.get("cover_letter_docx_path")) else None,
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
