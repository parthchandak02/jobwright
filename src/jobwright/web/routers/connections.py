"""Per-job network connections."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from jobwright import config
from jobwright.network.manual_connections import (
    add_manual_contact,
    get_manual_contacts,
    remove_manual_contact,
    search_connections_csv,
)
from jobwright.network.research import present_contact

router = APIRouter(prefix="/api", tags=["connections"])


def _load_contacts() -> dict:
    path = Path(config.NETWORK_DIR) / "job_contacts_latest.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if isinstance(data, dict) and "jobs" in data:
        return data["jobs"] if isinstance(data["jobs"], dict) else {}
    return data if isinstance(data, dict) else {}


@router.get("/jobs/{url:path}/connections")
def job_connections(url: str) -> dict:
    url = unquote(url)
    contacts = _load_contacts()
    entry = contacts.get(url) or {}
    csv_contacts = [c for c in (present_contact(c) for c in (entry.get("csv_contacts") or [])) if c]
    web_contacts = [c for c in (present_contact(c) for c in (entry.get("web_contacts") or [])) if c]
    return {
        "url": url,
        "title": entry.get("title"),
        "company": entry.get("company"),
        "fit_score": entry.get("fit_score"),
        "csv_contacts": csv_contacts,
        "web_contacts": web_contacts,
        "manual_contacts": get_manual_contacts(url),
    }


@router.get("/connections/search")
def connections_search(q: str = "", limit: int = 10) -> dict:
    limit = max(1, min(limit, 25))
    return {"results": search_connections_csv(q, limit=limit)}


class AddConnectionBody(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    name: str | None = None
    company: str | None = None
    position: str | None = None
    email: str | None = None
    url: str | None = None


@router.post("/jobs/{url:path}/connections")
def add_job_connection(url: str, body: AddConnectionBody) -> dict:
    url = unquote(url)
    try:
        contact = add_manual_contact(url, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"contact": contact, "manual_contacts": get_manual_contacts(url)}


@router.delete("/jobs/{url:path}/connections/{contact_id}")
def delete_job_connection(url: str, contact_id: str) -> dict:
    url = unquote(url)
    if not remove_manual_contact(url, contact_id):
        raise HTTPException(404, "Connection not found")
    return {"manual_contacts": get_manual_contacts(url)}
