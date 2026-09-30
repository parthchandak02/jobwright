"""Regenerate the README images in docs/images/ from fake demo data.

Usage (after `cd frontend && pnpm run build`):
    uv run --extra web --with pillow python scripts/readme_images.py          # write docs/images/*.png
    uv run --extra web --with pillow python scripts/readme_images.py --demo   # click around the demo UI

The built dashboard (frontend/dist) is loaded in headless Chromium on a fake
origin. Playwright answers every /api/** call with the FAKE fixtures below and
aborts every other request, so no API, database, WhatsApp, search or LLM is
touched. Nothing here is real user data.
"""

from __future__ import annotations

import io
import json
import mimetypes
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, ImageDraw
from playwright.sync_api import Route, sync_playwright

from jobwright.database import job_id_for_url
from jobwright.followups import format_followups
from jobwright.notify import build_review_notification, worth_a_look_line

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "frontend" / "dist"
OUT = REPO / "docs" / "images"
ORIGIN = "http://jobwright.demo"
LINK_BASE = "https://jobwright.example.com"
PHONE = {"width": 390, "height": 844}
PHONE_OUT_WIDTH = 600
MAX_BYTES = 250_000

# ---------------------------------------------------------------------------
# Fake fixtures
# ---------------------------------------------------------------------------

PERSON = "Alex Rivera"
EMAIL = "alex@example.com"
GROUP = "Alex – Job Applications"
GROUP_TARGET = "whatsapp:120363000000000001@g.us"
NOW = "2026-09-28T07:02:00"


def _url(slug: str) -> str:
    return f"https://jobs.example.com/{slug}"


def _job(slug, title, company, stage, score, **kw) -> dict:
    url = _url(slug)
    base = {
        "job_id": job_id_for_url(url),
        "whatsapp_notified_at": "2026-09-28T07:00:00" if stage == "backlog" and score >= 7 else None,
        "url": url,
        "title": title,
        "company": company,
        "site": "indeed",
        "location": "San Francisco, CA",
        "salary": "$150,000 - $180,000",
        "work_model": "hybrid",
        "sponsorship_status": "not_found",
        "fit_score": score,
        "ai_fit_score": score,
        "user_fit_score": None,
        "keywords": "product design, design systems, prototyping",
        "reasoning": "Strong overlap with your product design work.",
        "funnel_stage": stage,
        "outcome": None,
        "source": "discover",
        "applied_manually": False,
        "applied_at": None,
        "first_response_at": None,
        "follow_up_at": None,
        "followup_due": False,
        "applied_days_ago": None,
        "notes": None,
        "board_updated_by": "agent",
        "board_updated_at": "2026-09-28T06:40:00",
        "has_resume": stage != "backlog",
        "has_cover": stage != "backlog",
        "application_url": url,
        "discovered_at": "2026-09-28T06:12:00",
        "apply_status": None,
        "score_confidence": 0.8,
        "score_tier": "t1",
        "score_model": "glm-5p3-flash",
        "dealbreakers": [],
        "concerns": [],
        "score_caps": [],
        "location_ok": True,
        "seniority": "match",
        "full_description": "",
    }
    base.update(kw)
    return base


JOBS = [
    _job(
        "northwind/senior-product-designer",
        "Senior Product Designer",
        "Northwind Labs",
        "backlog",
        9,
        salary="$165,000 - $190,000",
        score_confidence=0.88,
        reasoning=(
            "Senior product design role on a B2B analytics suite. Your design-systems work and "
            "research-led process line up with the must-haves, the hybrid San Francisco office is "
            "on your list, and the pay is above your floor."
        ),
        full_description=(
            "## About the role\n\nNorthwind Labs is hiring a Senior Product Designer to lead the "
            "design of our analytics workspace. You will own flows end to end, from research to "
            "shipped UI, and help grow our design system.\n\n## What you'll do\n\n- Lead discovery "
            "and usability studies with customers\n- Design and prototype new workspace features\n"
            "- Contribute components and guidelines to the design system\n\n## About you\n\n"
            "- 5+ years of product design experience\n- A portfolio showing complex, data-heavy UI\n"
            "- Comfortable presenting to engineering and leadership"
        ),
    ),
    _job(
        "brightpath/product-designer-growth",
        "Product Designer, Growth",
        "Brightpath Health",
        "backlog",
        8,
        location="Remote (US)",
        work_model="remote",
        salary="$140,000 - $165,000",
        reasoning="Growth design in digital health; remote and within your pay range.",
    ),
    _job(
        "cobalt/design-systems-lead",
        "Design Systems Lead",
        "Cobalt Maps",
        "backlog",
        8,
        location="Oakland, CA",
        seniority="stretch",
        reasoning="Leads a design system team; a step up in scope but close to your experience.",
    ),
    _job(
        "fernway/ux-designer-ii",
        "UX Designer II",
        "Fernway",
        "backlog",
        6,
        location="Remote (US)",
        work_model="remote",
        seniority="too_junior",
        salary=None,
        reasoning="Solid team, but the level looks below yours and no salary is listed.",
    ),
    _job(
        "kestrel/ux-researcher",
        "Senior UX Researcher",
        "Kestrel Grid",
        "backlog",
        3,
        location="Austin, TX",
        work_model="onsite",
        location_ok=False,
        score_caps=["location"],
        reasoning="Research-only role based on site in Austin. [location]",
    ),
    _job(
        "tidewater/staff-product-designer",
        "Staff Product Designer",
        "Tidewater Studio",
        "prepare",
        8,
        salary="$185,000 - $210,000",
        reasoning="Staff-level IC role on a creative tools product.",
    ),
    _job(
        "quillstone/product-designer",
        "Product Designer",
        "Quillstone",
        "prepare",
        7,
        location="Remote (US)",
        work_model="remote",
        reasoning="Generalist product role at a writing tools startup.",
    ),
    _job(
        "orbitline/senior-product-designer",
        "Senior Product Designer",
        "Orbitline Freight",
        "applied",
        8,
        applied_at="2026-09-16T10:00:00",
        applied_days_ago=12,
        followup_due=True,
        followup_due_at="2026-09-26T10:00:00",
        board_updated_by="human",
    ),
    _job(
        "lumenfield/interaction-designer",
        "Interaction Designer",
        "Lumenfield",
        "applied",
        7,
        applied_at="2026-09-25T10:00:00",
        applied_days_ago=3,
        board_updated_by="human",
    ),
    _job(
        "maplemoss/lead-product-designer",
        "Lead Product Designer",
        "Maple & Moss",
        "in_progress",
        9,
        applied_at="2026-09-08T10:00:00",
        first_response_at="2026-09-12T10:00:00",
        board_updated_by="human",
    ),
]
JOB_BY_ID = {j["job_id"]: j for j in JOBS}
HERO_JOB = JOBS[0]
STAGES = ["backlog", "prepare", "applied", "in_progress", "offer", "closed"]

CRITERIA = {
    "summary": "Senior product design roles on software products, hybrid in the Bay Area or remote in the US.",
    "dealbreakers": [
        {"id": "agency_contract", "label": "Agency or contract-only", "description": "Staffing agency or fixed-term contract roles."},
        {"id": "no_design_ownership", "label": "No design ownership", "description": "Roles that only produce assets for others."},
        {"id": "gambling_crypto", "label": "Gambling or crypto", "description": "Companies whose main business is gambling or crypto."},
    ],
    "must_haves": ["End-to-end product design", "Works closely with research and engineering"],
    "nice_to_haves": ["Design systems", "B2B or data-heavy products", "Mentoring designers"],
    "locations_ok": ["San Francisco Bay Area", "Remote (US)"],
    "locations_not_ok": ["Relocation outside California"],
    "seniority": "Senior or staff individual contributor",
    "min_salary": 150000,
    "notify_threshold": 7,
}

SEARCHES = {
    "queries": [
        {"query": "Senior Product Designer", "tier": 1},
        {"query": "Staff Product Designer", "tier": 1},
        {"query": "Design Systems Designer", "tier": 2},
        {"query": "UX Designer", "tier": 2},
    ],
    "locations": [
        {"location": "San Francisco, CA", "remote": False},
        {"location": "Oakland, CA", "remote": False},
        {"location": "Remote", "remote": True},
    ],
    "boards": ["indeed", "linkedin", "zip_recruiter", "google"],
    "exclude_titles": ["intern", "contract"],
    "min_salary": 150000,
    "hours_old": 72,
    "results_per_site": 30,
}

PROFILE_JSON = {
    "personal": {"full_name": PERSON, "email": EMAIL, "city": "San Francisco", "phone": ""},
    "compensation": {"salary_expectation": "170000", "salary_currency": "USD"},
    "experience": {"target_role": "Senior Product Designer", "years_of_experience_total": "7"},
    "job_preferences": {
        "ideal_roles": ["Senior Product Designer", "Staff Product Designer"],
        "avoid_roles": ["Graphic Designer", "Marketing Designer"],
        "seek": "Product teams that ship often and take research seriously.",
        "company_types": "Software startups and mid-size product companies",
    },
}

RESUME_MD = (
    f"# {PERSON}\n\nSan Francisco, CA · {EMAIL}\n\n## Experience\n\n**Senior Product Designer, Acme Cloud** "
    "(2022 - present)\n\n- Led the redesign of the reporting workspace used by 4,000 teams\n- Built and "
    "maintained the component library with two engineers\n\n**Product Designer, Example Co** (2018 - 2022)\n\n"
    "- Designed onboarding and billing flows\n- Ran monthly usability studies\n"
)

SETTINGS = {
    "user_id": "alex",
    "name": PERSON,
    "profile": PROFILE_JSON,
    "searches": SEARCHES,
    "resume_markdown": RESUME_MD,
    "has_resume_pdf": True,
    "resume_pdf_mtime": 1790000000,
    "cover_letter_examples": [
        {"id": "cl1", "filename": "Cover_letter_design_role.pdf", "kind": "pdf", "mtime": 1790000000, "markdown": "Dear team,"},
    ],
}

PROFILE = {
    "user_id": "alex",
    "name": PERSON,
    "apply_enabled": False,
    "schedule": "0 7 * * *",
    "schedule_label": "Daily at 7:00 AM",
    "timezone": "America/Los_Angeles",
    "whatsapp_target": GROUP_TARGET,
    "whatsapp_chat_name": GROUP,
    "weekly_summary": True,
    "followup_days": 10,
    "brief_cron_name": "jobwright-brief-alex",
    "cron_synced": True,
    "stats": {"total": len(JOBS)},
    "stage_counts": {s: sum(1 for j in JOBS if j["funnel_stage"] == s) for s in STAGES},
    "source": "users.yaml",
}


def me(admin: bool, setup_complete: bool = True) -> dict:
    return {
        "email": EMAIL,
        "is_admin": admin,
        "auth_mode": "cloudflare",
        "active_user": "alex",
        "setup_complete": setup_complete,
        "profiles": [{"user_id": "alex", "name": PERSON}] + ([{"user_id": "sam", "name": "Sam Chen"}] if admin else []),
        "can_create_profile": admin,
    }


def _person(uid, name, email, group, hour, **kw) -> dict:
    base = {
        "user_id": uid,
        "name": name,
        "emails": [email],
        "setup_complete": True,
        "health": {"level": "ok", "lines": []},
        "last_brief": {"at": "2026-09-28T07:01:00", "notified": 6, "status": "ok"},
        "whatsapp": {"target": f"whatsapp:1203630000000000{hour:02d}@g.us", "name": group, "type": "group"},
        "schedule": f"0 {hour} * * *",
        "schedule_label": f"Daily at {hour}:00 AM",
        "hour": hour,
        "minute": 0,
        "notify_threshold": 7,
        "recommended_threshold": 7,
        "brief_top_n": 10,
        "human_gate": True,
        "weekly_summary": True,
        "followup_days": 10,
        "counts": {"new_7d": 48, "sent_7d": 31, "applied_total": 9, "open": 42, "followups_due": 1},
        "cost_30d": {"tokens": 2_410_000, "cost_usd": 0.62},
        "hermes_status": "unchanged",
        "brief_cron": True,
        "error": None,
    }
    base.update(kw)
    return base


ADMIN_OVERVIEW = {
    "bridge": "connected",
    "access": {"configured": True, "in_sync": True, "add": [], "remove": [], "error": None},
    "hermes": {"changed": False, "pending": 0, "error": None},
    "settings": {"admins": [EMAIL], "ops_target": "whatsapp:120363000000000099@g.us", "ops_target_name": "jobwright ops"},
    "users": [
        _person("alex", PERSON, EMAIL, GROUP, 7),
        _person("sam", "Sam Chen", "sam@example.com", "Sam – Job Search", 6,
                counts={"new_7d": 35, "sent_7d": 22, "applied_total": 4, "open": 30, "followups_due": 0},
                cost_30d={"tokens": 1_720_000, "cost_usd": 0.44}),
        _person("jordan", "Jordan Patel", "jordan@example.com", "Jordan – Jobs", 8,
                last_brief={"at": "2026-09-28T08:01:00", "notified": 0, "status": "skipped"},
                health={"level": "warn", "lines": ["No new matches scored 7+ today"]},
                counts={"new_7d": 19, "sent_7d": 8, "applied_total": 2, "open": 15, "followups_due": 2},
                cost_30d={"tokens": 980_000, "cost_usd": 0.25}),
        _person("morgan", "Morgan Lee", "morgan@example.com", "Morgan – Daily list", 7, minute=30,
                schedule="30 7 * * *", schedule_label="Daily at 7:30 AM",
                counts={"new_7d": 27, "sent_7d": 17, "applied_total": 6, "open": 21, "followups_due": 0},
                cost_30d={"tokens": 1_310_000, "cost_usd": 0.34}),
    ],
}

ADMIN_COSTS = {
    "days": 30,
    "users": [
        {"user_id": u["user_id"], "name": u["name"], "prompt_tokens": u["cost_30d"]["tokens"] * 9 // 10,
         "completion_tokens": u["cost_30d"]["tokens"] // 10, "total_tokens": u["cost_30d"]["tokens"],
         "calls": u["cost_30d"]["tokens"] // 3000, "cost_usd": u["cost_30d"]["cost_usd"], "error": None}
        for u in ADMIN_OVERVIEW["users"]
    ],
    "total": {"prompt_tokens": 5_778_000, "completion_tokens": 642_000, "total_tokens": 6_420_000, "calls": 2140, "cost_usd": 1.65},
}

CONNECTIONS = {
    "csv_contacts": [
        {"name": "Jamie Ortiz", "company": "Northwind Labs", "position": "Design Manager", "why": "Manages the product design team", "rank_score": 0.92, "source": "csv"},
        {"name": "Priya Nair", "company": "Northwind Labs", "position": "Senior Product Designer", "why": "Same role, same team", "rank_score": 0.81, "source": "csv"},
    ],
    "web_contacts": [],
    "manual_contacts": [],
}

MATERIALS = {
    "resume_md": RESUME_MD,
    "resume_docx": "Alex_Rivera_Northwind_Labs.docx",
    "cover_md": "Dear Northwind Labs team,\n\nI would love to help shape your analytics workspace...",
    "cover_docx": "Alex_Rivera_Northwind_Labs_cover.docx",
    "resume_preview": RESUME_MD,
    "cover_preview": (
        "Dear Tidewater Studio team,\n\nI have spent six years designing tools people use for hours a day, "
        "most recently leading the design system at a B2B analytics company. Your staff role on the "
        "creative tools product is the kind of deep, craft-heavy work I want next."
    ),
}

def _metrics(threshold: int, tp: int, fp: int, fn: int) -> dict:
    p, r = tp / (tp + fp), tp / (tp + fn)
    return {"threshold": threshold, "predicted_pos": tp + fp, "tp": tp, "fp": fp, "fn": fn,
            "precision": p, "recall": r, "f05": 1.25 * p * r / (0.25 * p + r)}


QUALITY = {
    "labels_total": 34,
    "labels_30d": 21,
    "eval_set": {"size": 34, "relevant": 14},
    "notified_30d": 58,
    "notified_advanced_30d": 11,
    "latest_eval": {
        "run_id": "demo",
        "at": "2026-09-27T17:00:00",
        "prompt_version": "v2",
        "config": {"n": 34, "positives": 14},
        "metrics": {"6": _metrics(6, 12, 5, 2), "7": _metrics(7, 10, 2, 4)},
        "metrics_explicit": {"6": _metrics(6, 12, 5, 2), "7": _metrics(7, 10, 2, 4)},
        "baseline": {"7": _metrics(7, 8, 5, 6)},
        "baseline_explicit": {"7": _metrics(7, 8, 5, 6)},
        "errors": 0,
    },
    "recommended_threshold": {"threshold": 6, "meets_bar": True, "min_precision": 0.7,
                              "precision": 12 / 17, "recall": 12 / 14, "current": 7},
    "usage_30d": [],
}

DRAFT = {"profile": PROFILE_JSON, "criteria": CRITERIA, "searches": {k: SEARCHES[k] for k in ("queries", "locations", "boards", "min_salary")}}

NOTIFY_JOBS = [{**j, "date_posted": f"2026-09-{27 - i % 2:02d}"}
               for i, j in enumerate(j for j in JOBS if j["funnel_stage"] == "backlog" and j["fit_score"] >= 7)]
FOLLOWUPS = [{"title": JOBS[7]["title"], "company": JOBS[7]["company"], "applied_days_ago": 12, "job_id": JOBS[7]["job_id"]}]


def whatsapp_message() -> str:
    """The daily list exactly as notify.py formats it (review-first, the onboarding default)."""
    msg = build_review_notification(NOTIFY_JOBS, LINK_BASE)
    msg += "\n\n" + worth_a_look_line(2, LINK_BASE)
    msg += "\n\n" + format_followups(FOLLOWUPS, LINK_BASE)
    return msg


# ---------------------------------------------------------------------------
# API mock
# ---------------------------------------------------------------------------


def api_response(method: str, path: str, state: dict):
    if path == "/api/me":
        return me(state["admin"], state.get("setup_complete", True))
    if path == "/api/board":
        cols = {s: [j for j in JOBS if j["funnel_stage"] == s] for s in STAGES}
        return {"stages": STAGES, "columns": cols, "total": len(JOBS), "closed_total": 14}
    if path == "/api/profile":
        return PROFILE
    if path == "/api/settings":
        return SETTINGS
    if path == "/api/criteria":
        return {"criteria": CRITERIA, "derived": False}
    if path == "/api/status":
        return {
            "last_run": {"started_at": "2026-09-28T07:00:00", "finished_at": "2026-09-28T07:02:00", "ok": True, "errors": {}, "stages_requested": []},
            "health": {"at": NOW, "level": "ok", "lines": []},
            "whatsapp_bridge": "connected",
        }
    if path == "/api/notify/preview":
        return {"sent": 0, "skipped": False, "dry_run": True, "message": whatsapp_message(),
                "jobs": [{"job_id": j["job_id"], "title": j["title"], "company": j["company"]} for j in NOTIFY_JOBS]}
    if path == "/api/onboarding/calibration":
        return {"ready": True, "scored_count": 40, "rated_count": 12, "target": 10, "jobs": []}
    if path == "/api/onboarding/status":
        done = state.get("setup_complete", True)
        steps = {"resume": True, "profile": done, "criteria": done, "searches": done, "cover_letters": done,
                 "whatsapp": done, "schedule": done, "first_run": done}
        return {"email": EMAIL, "has_profile": True, "user_id": "alex", "steps": steps, "complete": done}
    if path == "/api/onboarding/draft":
        return DRAFT
    if path == "/api/runs":
        return {"runs": []}
    if path == "/api/quality":
        return QUALITY
    if path == "/api/admin/overview":
        return ADMIN_OVERVIEW
    if path.startswith("/api/admin/costs"):
        return ADMIN_COSTS
    if path == "/api/admin/settings":
        return {"admins": [EMAIL], "ops_target": ADMIN_OVERVIEW["settings"]["ops_target"]}
    if path == "/api/tailor/defaults":
        return {"resume_instructions": "", "cover_instructions": ""}
    m = re.fullmatch(r"/api/jobs/([^/]+)(/.*)?", path)
    if m and m.group(1) in JOB_BY_ID:
        job, sub = JOB_BY_ID[m.group(1)], m.group(2) or ""
        if sub == "":
            return job
        if sub == "/connections":
            return CONNECTIONS
        if sub == "/materials":
            return MATERIALS if job["has_resume"] else {"resume_md": None, "resume_docx": None, "cover_md": None, "cover_docx": None}
        if sub == "/history":
            return {"history": [{"from_stage": None, "to_stage": "backlog", "actor": "agent", "at": job["discovered_at"], "note": None}]}
        if sub == "/labels":
            return {"labels": [], "machine_scores": [{"score": job["fit_score"], "confidence": job["score_confidence"], "tier": "t1",
                                                      "model": job["score_model"], "prompt_version": "v2", "run_kind": "brief", "created_at": NOW}]}
    return None


def install_routes(page, state: dict, misses: list[str]) -> None:
    def handle(route: Route) -> None:
        req = route.request
        parsed = urlparse(req.url)
        if f"{parsed.scheme}://{parsed.netloc}" != ORIGIN:
            route.abort()
            return
        if parsed.path.startswith("/api/"):
            body = api_response(req.method, parsed.path, state)
            if body is None:
                misses.append(f"{req.method} {parsed.path}")
                route.fulfill(status=404, content_type="application/json", body='{"detail":"demo"}')
                return
            route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
            return
        file = (DIST / parsed.path.lstrip("/")).resolve()
        if not file.is_file() or DIST not in file.parents:
            file = DIST / "index.html"
        mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        route.fulfill(status=200, content_type=mime, body=file.read_bytes())

    page.route("**/*", handle)


# ---------------------------------------------------------------------------
# Image post-processing
# ---------------------------------------------------------------------------


def save_png(img: Image.Image, name: str) -> Path:
    path = OUT / name
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    if buf.tell() <= MAX_BYTES:
        path.write_bytes(buf.getvalue())
        return path
    for colors in (256, 192, 128, 96, 64):
        q = img.quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
        buf = io.BytesIO()
        q.save(buf, format="PNG", optimize=True)
        if buf.tell() <= MAX_BYTES:
            break
    path.write_bytes(buf.getvalue())
    return path


def frame_phone(png: bytes) -> Image.Image:
    shot = Image.open(io.BytesIO(png)).convert("RGB")
    h = round(shot.height * PHONE_OUT_WIDTH / shot.width)
    shot = shot.resize((PHONE_OUT_WIDTH, h), Image.Resampling.LANCZOS)
    bezel, radius = 10, 44
    w, hh = PHONE_OUT_WIDTH + 2 * bezel, h + 2 * bezel
    scale = 3
    big = Image.new("L", (w * scale, hh * scale), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * scale - 1, hh * scale - 1), radius=(radius + bezel) * scale, fill=255)
    outer = big.resize((w, hh), Image.Resampling.LANCZOS)
    inner_big = Image.new("L", (PHONE_OUT_WIDTH * scale, h * scale), 0)
    ImageDraw.Draw(inner_big).rounded_rectangle((0, 0, PHONE_OUT_WIDTH * scale - 1, h * scale - 1), radius=radius * scale, fill=255)
    inner = inner_big.resize((PHONE_OUT_WIDTH, h), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (w, hh), (0, 0, 0, 0))
    canvas.paste(Image.new("RGBA", (w, hh), (38, 38, 44, 255)), (0, 0), outer)
    canvas.paste(shot.convert("RGBA"), (bezel, bezel), inner)
    return canvas


# ---------------------------------------------------------------------------
# Static HTML renders (hero banner, WhatsApp bubble)
# ---------------------------------------------------------------------------

LOGO_SVG = (
    '<svg viewBox="0 0 32 32" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">'
    '<rect x="8" y="6" width="16" height="20" rx="2.5" stroke-width="2"/><path d="M11.5 11.5h9" stroke-width="2"/>'
    '<path d="M11.5 16h6" stroke-width="2" opacity="0.55"/><path d="M17.5 21.5l2 2 4.5-4.5" stroke-width="2"/></svg>'
)
FONT = ('ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI Variable Text", "Segoe UI", system-ui, '
        'Roboto, "Helvetica Neue", Arial, sans-serif')


def hero_html() -> str:
    cards = "".join(
        f'<div class="card"><div class="t">{j["title"]}</div><div class="c">{j["company"]} · {j["location"]}</div>'
        f'<span class="s s{min(j["fit_score"], 9)}">{j["fit_score"]}</span></div>'
        for j in NOTIFY_JOBS
    )
    return f"""<!doctype html><html><head><style>
    * {{ box-sizing: border-box; margin: 0; }}
    body {{ width: 1200px; height: 600px; font-family: {FONT}; color: oklch(0.22 0.01 260);
      background: linear-gradient(120deg, oklch(0.985 0.002 80) 45%, oklch(0.96 0.02 262));
      display: flex; align-items: center; padding: 0 88px; gap: 64px; }}
    .left {{ flex: 1; }}
    .mark {{ width: 76px; height: 76px; border-radius: 18px; background: oklch(0.52 0.15 262); color: white; padding: 12px; }}
    h1 {{ font-size: 64px; letter-spacing: -0.03em; font-weight: 650; margin-top: 28px; }}
    .tag {{ font-size: 26px; line-height: 1.35; color: oklch(0.5 0.01 260); margin-top: 14px; max-width: 560px; }}
    .pill {{ display: inline-flex; gap: 8px; margin-top: 30px; }}
    .pill span {{ font-size: 15px; padding: 7px 14px; border-radius: 999px; border: 1px solid oklch(0.86 0.005 80);
      background: white; color: oklch(0.4 0.01 260); }}
    .right {{ width: 440px; background: white; border: 1px solid oklch(0.915 0.004 80); border-radius: 16px;
      box-shadow: 0 1px 2px oklch(0.3 0.02 262 / 0.08), 0 16px 40px -16px oklch(0.3 0.05 262 / 0.22); padding: 20px; }}
    .head {{ font-size: 13px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: oklch(0.5 0.01 260);
      display: flex; justify-content: space-between; margin-bottom: 12px; }}
    .head b {{ color: oklch(0.52 0.15 262); }}
    .card {{ position: relative; border: 1px solid oklch(0.915 0.004 80); border-radius: 12px; padding: 14px 64px 14px 16px; margin-top: 10px; }}
    .t {{ font-size: 17px; font-weight: 600; }}
    .c {{ font-size: 14px; color: oklch(0.5 0.01 260); margin-top: 3px; }}
    .s {{ position: absolute; right: 16px; top: 50%; transform: translateY(-50%); font-weight: 650; font-size: 15px;
      width: 34px; height: 28px; border-radius: 999px; display: grid; place-items: center; font-variant-numeric: tabular-nums; }}
    .s9 {{ background: oklch(0.55 0.11 155 / 0.14); color: oklch(0.42 0.1 155); }}
    .s8, .s7 {{ background: oklch(0.52 0.15 262 / 0.12); color: oklch(0.45 0.15 262); }}
    </style></head><body>
    <div class="left"><div class="mark">{LOGO_SVG}</div><h1>jobwright</h1>
    <p class="tag">One short list of jobs a day, picked for you and explained.</p>
    <div class="pill"><span>Finds</span><span>Scores</span><span>Sends to WhatsApp</span><span>Tailors</span></div></div>
    <div class="right"><div class="head"><span>Today's list</span><b>{len(NOTIFY_JOBS)} new</b></div>{cards}</div>
    </body></html>"""


def whatsapp_html() -> str:
    import html

    text = html.escape(whatsapp_message())
    text = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<b>\1</b>", text)  # WhatsApp *bold*
    text = re.sub(r"(?<![\w_/])_([^_\n]+?)_(?![\w_])", r"<i>\1</i>", text)  # WhatsApp _italic_
    text = re.sub(r"(https://\S+)", r'<a>\1</a>', text)
    return f"""<!doctype html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><style>
    * {{ box-sizing: border-box; margin: 0; }}
    body {{ width: {PHONE['width']}px; min-height: {PHONE['height']}px; font-family: {FONT}; background: #efeae2; }}
    .bar {{ background: #f6f5f3; border-bottom: 1px solid #ddd8d0; padding: 54px 16px 10px; display: flex; align-items: center; gap: 10px; }}
    .av {{ width: 36px; height: 36px; border-radius: 50%; background: oklch(0.52 0.15 262); color: white; padding: 6px; }}
    .n {{ font-weight: 600; font-size: 16px; color: #111b21; }}
    .sub {{ font-size: 12.5px; color: #667781; }}
    .day {{ margin: 14px auto 6px; width: fit-content; font-size: 12px; background: white; color: #54656f; padding: 4px 10px;
      border-radius: 8px; box-shadow: 0 1px 0.5px rgba(0,0,0,.13); }}
    .b {{ margin: 6px 20px 6px 10px; background: white; border-radius: 0 10px 10px 10px; padding: 7px 9px 20px;
      box-shadow: 0 1px 0.5px rgba(0,0,0,.13); position: relative; font-size: 13.4px; line-height: 1.4; color: #111b21;
      white-space: pre-wrap; overflow-wrap: anywhere; }}
    .who {{ font-size: 12.8px; font-weight: 600; color: oklch(0.52 0.15 262); margin-bottom: 2px; }}
    .b a {{ color: #027eb5; }}
    .time {{ position: absolute; right: 9px; bottom: 5px; font-size: 11px; color: #667781; }}
    </style></head><body>
    <div class="bar"><div class="av">{LOGO_SVG}</div><div><div class="n">{html.escape(GROUP)}</div><div class="sub">You, jobwright</div></div></div>
    <div class="day">Today</div>
    <div class="b"><div class="who">jobwright</div>{text}<span class="time">7:02 AM</span></div>
    </body></html>"""


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


def demo() -> int:
    """Open the dashboard with the fake fixtures in a visible browser; writes are ignored."""
    misses: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.add_init_script("localStorage.setItem('jobwright-theme','light')")
        install_routes(page, {"admin": True}, misses)
        page.goto(ORIGIN + "/")
        print("Demo running with fake data. Close the browser window to stop.", flush=True)
        page.wait_for_event("close", timeout=0)
        browser.close()
    return 0


def main() -> int:
    if not (DIST / "index.html").is_file():
        print("frontend/dist missing: run `cd frontend && pnpm run build` first", file=sys.stderr)
        return 1
    if "--demo" in sys.argv[1:]:
        return demo()
    OUT.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    misses: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()

        def new_page(state: dict, viewport=PHONE, scale=2):
            ctx = browser.new_context(viewport=viewport, device_scale_factor=scale, color_scheme="light",
                                      timezone_id="America/Los_Angeles", locale="en-US", is_mobile=viewport is PHONE,
                                      has_touch=viewport is PHONE)
            ctx.add_init_script("localStorage.setItem('jobwright-theme','light')")
            page = ctx.new_page()
            install_routes(page, state, misses)
            return page

        def shot(state: dict, path: str, name: str, prepare=None) -> None:
            page = new_page(state)
            page.goto(ORIGIN + path)
            page.wait_for_load_state("networkidle")
            if prepare:
                prepare(page)
            page.wait_for_timeout(600)
            page.evaluate("document.activeElement && document.activeElement.blur()")
            page.wait_for_timeout(150)
            written.append(save_png(frame_phone(page.screenshot()), name))
            page.context.close()

        admin = {"admin": True}
        member = {"admin": False}
        shot(admin, "/", "board.png", lambda page: page.get_by_role("tab", name="Board").click())
        shot(admin, f"/jobs/{HERO_JOB['job_id']}", "job-drawer.png")

        def to_fit(page):
            page.get_by_role("button", name="Draft my search").click()
            page.get_by_role("button", name="Continue").click()
            page.wait_for_load_state("networkidle")

        shot({"admin": False, "setup_complete": False}, "/welcome", "welcome.png", to_fit)
        shot(member, "/profile?tab=whatsapp", "settings-daily-list.png")
        shot(admin, "/admin", "admin.png")
        shot(member, "/quality", "match-quality.png")

        def to_materials(page):
            heading = page.get_by_role("heading", name="Resume", exact=True)
            section = page.locator("section", has=heading)
            section.get_by_role("combobox").first.click()
            page.get_by_role("option", name="Tailored for this job").click()
            section.get_by_role("tab", name="Markdown").click()
            heading.evaluate("el => el.scrollIntoView({block: 'start'})")

        prepared = next(j for j in JOBS if j["company"] == "Tidewater Studio")
        shot(member, f"/jobs/{prepared['job_id']}", "materials.png", to_materials)

        for name, html_doc, viewport, frame in (
            ("whatsapp-list.png", whatsapp_html(), PHONE, True),
            ("hero.png", hero_html(), {"width": 1200, "height": 600}, False),
        ):
            page = new_page({"admin": True}, viewport=viewport)
            page.set_content(html_doc)
            page.wait_for_timeout(200)
            png = page.screenshot()
            img = frame_phone(png) if frame else Image.open(io.BytesIO(png)).convert("RGB")
            written.append(save_png(img, name))
            page.context.close()
        browser.close()

    for path in written:
        with Image.open(path) as im:
            print(f"{path.relative_to(REPO)}  {im.width}x{im.height}  {path.stat().st_size // 1024} KB")
    if misses:
        print("Unmocked API calls (answered 404):", *sorted(set(misses)), sep="\n  ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
