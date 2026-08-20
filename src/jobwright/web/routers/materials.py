"""Materials lookup and gated file download."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from jobwright import config
from jobwright.database import get_connection
from jobwright.scoring.materials_format import (
    MaterialKind,
    format_material_preview,
    resolve_material_path,
)
from jobwright.scoring.tailor_instructions import (
    DEFAULT_COVER_INSTRUCTIONS,
    DEFAULT_RESUME_INSTRUCTIONS,
)
from jobwright.web.routers.runs import spawn_logged_run
from jobwright.web.session import resolve_dashboard_user

router = APIRouter(prefix="/api", tags=["materials"])

# Cap preview text so the drawer stays scannable (~6–8 KB).
_PREVIEW_MAX_CHARS = 8000


class TailorJobBody(BaseModel):
    resume_instructions: str | None = Field(default=None, max_length=20_000)
    cover_instructions: str | None = Field(default=None, max_length=20_000)


class TailorResumeBody(BaseModel):
    resume_instructions: str | None = Field(default=None, max_length=20_000)


class TailorCoverBody(BaseModel):
    cover_instructions: str | None = Field(default=None, max_length=20_000)


def _sibling_export(path: str | None, suffix: str) -> str | None:
    if not path:
        return None
    candidate = Path(path).with_suffix(suffix)
    return str(candidate) if candidate.is_file() else None


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
        "resume_pdf": _sibling_export(resume_md, ".pdf") or _sibling_export(d.get("tailored_resume_docx_path"), ".pdf"),
        "cover_pdf": _sibling_export(cover_md, ".pdf") or _sibling_export(d.get("cover_letter_docx_path"), ".pdf"),
        "resume_preview": _read_preview(d.get("tailored_resume_path"), "resume"),
        "cover_preview": _read_preview(d.get("cover_letter_path"), "cover"),
        "manifest": manifest_entry,
    }


def _inline_job_pdf(url: str, *, resume: bool) -> FileResponse:
    """Serve tailored resume or cover PDF inline for drawer iframe preview."""
    url = unquote(url)
    conn = get_connection()
    row = conn.execute(
        "SELECT tailored_resume_path, tailored_resume_docx_path, "
        "cover_letter_path, cover_letter_docx_path FROM jobs WHERE url = ?",
        (url,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    d = dict(row)
    if resume:
        md_path = d.get("tailored_resume_path")
        docx_path = d.get("tailored_resume_docx_path")
        filename = "tailored_resume.pdf"
    else:
        md_path = d.get("cover_letter_path")
        docx_path = d.get("cover_letter_docx_path")
        filename = "cover_letter.pdf"
    pdf_path = _sibling_export(md_path, ".pdf") or _sibling_export(docx_path, ".pdf")
    if not pdf_path:
        raise HTTPException(404, "PDF not found")
    resolved = _assert_allowed(Path(pdf_path))
    return FileResponse(
        str(resolved),
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline",
    )


@router.get("/jobs/{url:path}/materials/resume.pdf")
def job_resume_pdf(url: str) -> FileResponse:
    return _inline_job_pdf(url, resume=True)


@router.get("/jobs/{url:path}/materials/cover.pdf")
def job_cover_pdf(url: str) -> FileResponse:
    return _inline_job_pdf(url, resume=False)


@router.get("/tailor/defaults")
def tailor_instruction_defaults() -> dict:
    """Default Auto Tailor instructions shown in Custom Tailor."""
    return {
        "resume_instructions": DEFAULT_RESUME_INSTRUCTIONS,
        "cover_instructions": DEFAULT_COVER_INSTRUCTIONS,
    }


@router.post("/jobs/{url:path}/tailor")
def tailor_job_materials(url: str, request: Request, body: TailorJobBody | None = None) -> dict:
    """Start a verbose per-job tailor run (resume, cover, docx) and return the run handle."""
    return _spawn_tailor_run(url, request, scope="full", body=body)


@router.post("/jobs/{url:path}/tailor/resume")
def tailor_job_resume(url: str, request: Request, body: TailorResumeBody | None = None) -> dict:
    """Start resume-only tailor (tailor + docx)."""
    wrapped = TailorJobBody(resume_instructions=(body or TailorResumeBody()).resume_instructions)
    return _spawn_tailor_run(url, request, scope="resume", body=wrapped)


@router.post("/jobs/{url:path}/tailor/cover")
def tailor_job_cover(url: str, request: Request, body: TailorCoverBody | None = None) -> dict:
    """Start cover-only tailor (cover + docx)."""
    wrapped = TailorJobBody(cover_instructions=(body or TailorCoverBody()).cover_instructions)
    return _spawn_tailor_run(url, request, scope="cover", body=wrapped)


def _spawn_tailor_run(
    url: str,
    request: Request,
    *,
    scope: str,
    body: TailorJobBody | None,
) -> dict:
    url = unquote(url)
    conn = get_connection()
    row = conn.execute(
        "SELECT url, full_description, description FROM jobs WHERE url = ?",
        (url,),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Job not found")
    description = (row["full_description"] or row["description"] or "").strip()
    if not description:
        raise HTTPException(400, "Job description required")

    try:
        from jobwright.resume import load_resume_text

        load_resume_text()
    except FileNotFoundError as e:
        raise HTTPException(400, str(e)) from e

    body = body or TailorJobBody()
    log_dir = Path(config.LOG_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:8]
    resume_file = log_dir / f"tailor_resume_instr_{token}.txt"
    cover_file = log_dir / f"tailor_cover_instr_{token}.txt"
    resume_file.write_text(
        (body.resume_instructions or DEFAULT_RESUME_INSTRUCTIONS).strip(),
        encoding="utf-8",
    )
    cover_file.write_text(
        (body.cover_instructions or DEFAULT_COVER_INSTRUCTIONS).strip(),
        encoding="utf-8",
    )
    args = [
        "tailor-job",
        "--url",
        url,
        "--verbose",
        "--validation",
        "lenient",
    ]
    if scope == "resume":
        args.extend(["--resume-only", "--resume-instructions-file", str(resume_file)])
        stages = ["tailor", "docx"]
        kind = "tailor_resume"
        log_name = "web_tailor_resume"
    elif scope == "cover":
        args.extend(["--cover-only", "--cover-instructions-file", str(cover_file)])
        stages = ["cover", "docx"]
        kind = "tailor_cover"
        log_name = "web_tailor_cover"
    else:
        args.extend(
            [
                "--resume-instructions-file",
                str(resume_file),
                "--cover-instructions-file",
                str(cover_file),
            ]
        )
        stages = ["tailor", "cover", "docx"]
        kind = "tailor"
        log_name = "web_tailor"

    handle = spawn_logged_run(
        args=args,
        user_id=resolve_dashboard_user(request),
        stages=stages,
        log_name=log_name,
        kind=kind,
        extra_env={"JOBWRIGHT_LOG_LEVEL": "DEBUG"},
    )
    return {**handle, "url": url}


@router.get("/download")
def download_file(path: str) -> FileResponse:
    resolved = _assert_allowed(Path(path))
    return FileResponse(
        str(resolved),
        filename=resolved.name,
        media_type="application/octet-stream",
    )
