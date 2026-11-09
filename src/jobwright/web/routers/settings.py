"""Editable user settings surfaced to the dashboard.

Reads and writes the same files the daily pipeline consumes:
- ``profile.json`` (identity + scoring guidance)
- ``searches.yaml`` (discover queries / locations / filters)
- ``resume/base.pdf`` (source of truth; markdown is derived)
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Annotated, Any

import yaml
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from jobwright import config
from jobwright.onboarding import PROFILE_SECTIONS, accept_patterns, allowed_profile_fields
from jobwright.resume import (
    PdfUploadError,
    ResumeUnreadableError,
    cached_pdf_markdown,
    load_resume_text,
    read_upload,
    save_pdf_with_markdown,
)
from jobwright.users import get_user
from jobwright.web.session import current_user_id
from jobwright.web.txguard import TxGuardRoute

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"], route_class=TxGuardRoute)

# Whitelisted profile fields (avoids surfacing secrets like password / eeo data).
_PROFILE_SECTIONS = PROFILE_SECTIONS


def _load_profile() -> dict:
    if config.PROFILE_PATH.exists():
        try:
            return json.loads(config.PROFILE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(500, f"profile.json is not valid JSON: {exc}") from exc
    return {}


def _load_searches() -> dict:
    if config.SEARCH_CONFIG_PATH.exists():
        try:
            return yaml.safe_load(config.SEARCH_CONFIG_PATH.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(500, f"searches.yaml is not valid YAML: {exc}") from exc
    return {}


def _pick(src: dict, keys: list[str]) -> dict:
    return {k: src.get(k) for k in keys}


def _write_json(data: dict) -> None:
    path = config.PROFILE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _write_searches(data: dict) -> None:
    path = config.SEARCH_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )


def _base_materials() -> dict:
    """Base resume and cover letter samples (what the job drawer shows)."""
    resume_markdown = ""
    resume_unreadable = False
    try:
        resume_markdown = load_resume_text()
    except ResumeUnreadableError:
        # A broken PDF must not take Settings down; the page asks for a new copy.
        resume_unreadable = True
    except FileNotFoundError:
        pass

    pdf_path = config.RESUME_PDF_PATH
    has_pdf = pdf_path.is_file()
    return {
        "resume_markdown": resume_markdown,
        "has_resume_pdf": has_pdf,
        # PDF on file but it can't be converted (e.g. zero pages): ask for a new one.
        "resume_unreadable": resume_unreadable,
        "resume_pdf_mtime": int(pdf_path.stat().st_mtime) if has_pdf else None,
        "cover_letter_examples": _list_cover_letter_examples(),
    }


@router.get("")
def get_settings(request: Request) -> dict:
    user_id = current_user_id(request)
    user = get_user(user_id)
    profile = _load_profile()
    searches = _load_searches()
    defaults = searches.get("defaults") or {}

    display_name = (
        (user.name if user else None)
        or (profile.get("personal") or {}).get("full_name")
        or user_id
    )

    return {
        "user_id": user_id,
        "name": display_name,
        "profile": {
            section: _pick(profile.get(section) or {}, keys)
            for section, keys in _PROFILE_SECTIONS
        },
        "searches": {
            "queries": searches.get("queries") or [],
            "locations": searches.get("locations") or [],
            "boards": searches.get("boards") or [],
            "exclude_titles": searches.get("exclude_titles") or [],
            "min_salary": searches.get("min_salary"),
            "hours_old": defaults.get("hours_old"),
            "results_per_site": defaults.get("results_per_site"),
        },
        **_base_materials(),
    }


@router.get("/materials")
def get_base_materials() -> dict:
    """Only the base materials, without profile or searches (job drawer)."""
    return _base_materials()


class ProfileSettings(BaseModel):
    personal: dict[str, Any] | None = None
    compensation: dict[str, Any] | None = None
    experience: dict[str, Any] | None = None
    job_preferences: dict[str, Any] | None = None


@router.put("/profile")
def put_profile(body: ProfileSettings) -> dict:
    profile = _load_profile()
    changed_personal: list[str] = []
    for section, data in allowed_profile_fields(body.model_dump(exclude_none=True)).items():
        if data:
            if section == "personal":
                old = profile.get("personal") or {}
                changed_personal = [k for k, v in data.items() if old.get(k) != v]
            profile.setdefault(section, {}).update(data)
    _write_json(profile)
    if changed_personal:
        from jobwright.apply.answers import note_profile_edit

        note_profile_edit(changed_personal)  # contact answers typed here now say "You entered"
    return {"ok": True}


class SearchSettings(BaseModel):
    queries: list[dict[str, Any]] | None = None
    locations: list[dict[str, Any]] | None = None
    boards: list[str] | None = None
    exclude_titles: list[str] | None = None
    min_salary: int | None = None
    hours_old: int | None = None
    results_per_site: int | None = None


@router.put("/searches")
def put_searches(body: SearchSettings) -> dict:
    searches = _load_searches()
    incoming = body.model_dump(exclude_unset=True)
    for loc in incoming.get("locations") or []:
        if loc.get("remote"):
            loc["remote_scope"] = "any" if loc.get("remote_scope") == "any" else "us"
        else:
            loc.pop("remote_scope", None)
    for key in ("queries", "locations", "boards", "exclude_titles", "min_salary"):
        if key in incoming:
            searches[key] = incoming[key]
    if incoming.get("locations"):
        # New cities must pass the discovery location filter too; keep hand-tuned patterns.
        location_cfg = searches.get("location") or {}
        accept = list(location_cfg.get("accept_patterns") or [])
        accept += [p for p in accept_patterns(incoming["locations"]) if p not in accept]
        searches["location"] = {**location_cfg, "accept_patterns": accept}
    defaults = searches.setdefault("defaults", {})
    for key in ("hours_old", "results_per_site"):
        if incoming.get(key) is not None:
            defaults[key] = incoming[key]
    _write_searches(searches)
    return {"ok": True}


@router.get("/resume.pdf")
def get_resume_pdf() -> FileResponse:
    path = config.RESUME_PDF_PATH
    if not path.is_file():
        raise HTTPException(404, "No resume PDF on file")
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )


def _save_upload(file: UploadFile, pdf_path: Path, md_path: Path) -> tuple[bytes, str]:
    """Size-capped read, then validate + convert before replacing the old files."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "Upload a PDF file")
    try:
        data = read_upload(file.file)
        return data, save_pdf_with_markdown(data, pdf_path, md_path)
    except PdfUploadError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


# Sync handlers: the PDF conversion (pymupdf) blocks, so it runs in the threadpool.
@router.put("/resume.pdf")
def put_resume_pdf(file: Annotated[UploadFile, File()]) -> dict:
    data, markdown = _save_upload(file, config.RESUME_PDF_PATH, config.RESUME_MD_PATH)
    return {"ok": True, "bytes": len(data), "markdown_chars": len(markdown)}


_EXAMPLE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
_SKIP_EXAMPLE_STEMS = {"readme"}


def _sanitize_example_stem(filename: str) -> str:
    stem = Path(filename or "example").stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-") or "example"
    return stem[:80]


def _example_pdf_path(example_id: str) -> Path:
    if not _EXAMPLE_ID_RE.match(example_id):
        raise HTTPException(400, "Invalid cover letter id")
    return config.COVER_LETTER_EXAMPLES_DIR / f"{example_id}.pdf"


def _unique_example_stem(stem: str) -> str:
    examples_dir = config.COVER_LETTER_EXAMPLES_DIR
    candidate = stem
    n = 2
    while (examples_dir / f"{candidate}.pdf").exists():
        candidate = f"{stem}-{n}"
        n += 1
        if n > 99:
            raise HTTPException(400, "Too many cover letters with this name")
    return candidate


def _list_cover_letter_examples() -> list[dict[str, Any]]:
    examples_dir = config.COVER_LETTER_EXAMPLES_DIR
    if not examples_dir.is_dir():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(examples_dir.glob("*.pdf")):
        if not path.is_file() or not _EXAMPLE_ID_RE.match(path.stem):
            continue
        if path.stem.lower() in _SKIP_EXAMPLE_STEMS:
            continue
        markdown = ""
        try:
            markdown = cached_pdf_markdown(path, path.with_suffix(".md"))
        except Exception:  # noqa: BLE001 - one broken example must not break the list
            log.warning("could not read cover letter example %s", path, exc_info=True)
            markdown = ""
        items.append(
            {
                "id": path.stem,
                "filename": path.name,
                "kind": "pdf",
                "mtime": int(path.stat().st_mtime),
                "markdown": markdown,
            }
        )
    return items


@router.get("/cover-letters/{example_id}/pdf")
def get_cover_letter_example_pdf(example_id: str) -> FileResponse:
    path = _example_pdf_path(example_id)
    if not path.is_file():
        raise HTTPException(404, "Cover letter PDF not found")
    return FileResponse(
        str(path),
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
    )


@router.put("/cover-letters")
def put_cover_letter_example(file: Annotated[UploadFile, File()]) -> dict:
    examples_dir = config.COVER_LETTER_EXAMPLES_DIR
    examples_dir.mkdir(parents=True, exist_ok=True)
    stem = _unique_example_stem(_sanitize_example_stem(file.filename or "example"))
    path = examples_dir / f"{stem}.pdf"
    data, markdown = _save_upload(file, path, path.with_suffix(".md"))
    return {
        "ok": True,
        "id": stem,
        "filename": path.name,
        "bytes": len(data),
        "markdown_chars": len(markdown),
    }


@router.delete("/cover-letters/{example_id}")
def delete_cover_letter_example(example_id: str) -> dict:
    if not _EXAMPLE_ID_RE.match(example_id):
        raise HTTPException(400, "Invalid cover letter id")
    examples_dir = config.COVER_LETTER_EXAMPLES_DIR
    removed = False
    for suffix in (".pdf", ".txt", ".md"):
        path = examples_dir / f"{example_id}{suffix}"
        if path.is_file():
            path.unlink()
            removed = True
    if not removed:
        raise HTTPException(404, "Cover letter not found")
    return {"ok": True}
