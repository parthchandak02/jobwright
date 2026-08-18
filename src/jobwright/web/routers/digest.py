"""Daily digest reader."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from jobwright import config

router = APIRouter(prefix="/api", tags=["digest"])


@router.get("/digest")
def latest_digest() -> dict:
    app_dir = Path(config.APP_DIR)
    digests = sorted(app_dir.glob("DIGEST_*"), reverse=True)
    # Prefer dated DIGEST_YYYYMMDD over DIGEST_DELIVERED_*
    digests = [p for p in digests if p.name.startswith("DIGEST_") and "DELIVERED" not in p.name]
    if not digests:
        return {"path": None, "date": None, "text": ""}
    path = digests[0]
    date = path.name.removeprefix("DIGEST_")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        text = ""
    return {"path": str(path), "date": date, "text": text}
