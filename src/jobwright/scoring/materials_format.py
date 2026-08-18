"""Markdown materials format for tailored resumes and cover letters."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from jobwright.scoring.validator import sanitize_text

MATERIAL_SUFFIXES = (".md", ".txt")
MaterialKind = Literal["resume", "cover"]


def assemble_resume_markdown(data: dict, profile: dict) -> str:
    """Convert JSON resume data to markdown.

    Header (name, contact) is code-injected from the profile, never LLM-generated.
    """
    personal = profile.get("personal", {})
    lines: list[str] = []

    lines.append(f"# {personal.get('full_name', '').strip()}")
    lines.append(sanitize_text(data.get("title", "Software Engineer")))

    contact_parts: list[str] = []
    if personal.get("email"):
        contact_parts.append(personal["email"])
    if personal.get("phone"):
        contact_parts.append(personal["phone"])
    if personal.get("github_url"):
        contact_parts.append(personal["github_url"])
    if personal.get("linkedin_url"):
        contact_parts.append(personal["linkedin_url"])
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")

    lines.append("## SUMMARY")
    lines.append(sanitize_text(data["summary"]))
    lines.append("")

    lines.append("## TECHNICAL SKILLS")
    if isinstance(data["skills"], dict):
        for cat, val in data["skills"].items():
            lines.append(f"{cat}: {sanitize_text(str(val))}")
    lines.append("")

    lines.append("## EXPERIENCE")
    for entry in data.get("experience", []):
        lines.append(sanitize_text(entry.get("header", "")))
        if entry.get("subtitle"):
            lines.append(sanitize_text(entry["subtitle"]))
        for b in entry.get("bullets", []):
            lines.append(f"- {sanitize_text(b)}")
        lines.append("")

    lines.append("## PROJECTS")
    for entry in data.get("projects", []):
        lines.append(sanitize_text(entry.get("header", "")))
        if entry.get("subtitle"):
            lines.append(sanitize_text(entry["subtitle"]))
        for b in entry.get("bullets", []):
            lines.append(f"- {sanitize_text(b)}")
        lines.append("")

    lines.append("## EDUCATION")
    lines.append(sanitize_text(str(data.get("education", ""))))

    return "\n".join(lines)


def normalize_for_structured_parse(text: str) -> str:
    """Strip lightweight markdown so resume parsers keep working."""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            out.append(stripped[3:].strip())
        elif stripped.startswith("# "):
            out.append(stripped[2:].strip())
        else:
            out.append(line.rstrip())
    return "\n".join(out)


def resolve_material_path(path: str | Path | None) -> Path | None:
    """Return an on-disk markdown/text material path, preferring .md over legacy .txt."""
    if not path:
        return None
    p = Path(path)
    if p.is_file():
        return p
    for suffix in MATERIAL_SUFFIXES:
        candidate = p.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    return None


def generated_material_exists(
    md_path: str | Path | None,
    docx_path: str | Path | None = None,
) -> bool:
    """True when a tailored markdown/text or DOCX file is on disk."""
    if resolve_material_path(md_path):
        return True
    return bool(docx_path and Path(docx_path).is_file())


def material_docx_path(path: str | Path | None) -> Path | None:
    """Sibling DOCX for a markdown/text material path."""
    resolved = resolve_material_path(path)
    if not resolved:
        return None
    docx = resolved.with_suffix(".docx")
    return docx if docx.is_file() else None


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def format_cover_letter_markdown(text: str) -> str:
    """Normalize cover letter text into markdown paragraphs for preview and storage."""
    text = text.strip()
    if not text:
        return text
    if "\n\n" in text:
        return "\n\n".join(p.strip() for p in re.split(r"\n\s*\n", text) if p.strip())

    match = re.match(r"^(Dear[^,]+,)\s*(.*)$", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return text

    greeting, body = match.group(1).strip(), match.group(2).strip()
    sentences = _split_sentences(body)
    if len(sentences) <= 1:
        return f"{greeting}\n\n{body}"

    sign_off = ""
    last = sentences[-1]
    if re.match(r"^(Best|Regards|Thanks|Sincerely)\b", last, re.IGNORECASE):
        sign_off = sentences.pop()
    elif len(last.split()) <= 4 and not last.endswith((".", "!", "?")):
        sign_off = sentences.pop()

    if not sentences:
        parts = [greeting]
        if sign_off:
            parts.append(sign_off)
        return "\n\n".join(parts)

    if len(sentences) <= 3:
        paragraphs = sentences
    else:
        count = len(sentences)
        sizes = [count // 3 + (1 if i < count % 3 else 0) for i in range(3)]
        paragraphs, idx = [], 0
        for size in sizes:
            if size:
                paragraphs.append(" ".join(sentences[idx : idx + size]))
                idx += size

    parts = [greeting, *paragraphs]
    if sign_off:
        parts.append(sign_off)
    return "\n\n".join(parts)


def format_legacy_resume_markdown(text: str) -> str:
    """Upgrade legacy plain-text resumes to markdown for dashboard preview."""
    text = text.strip()
    if not text or text.lstrip().startswith("#"):
        return text

    lines = text.splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            out.append("")
            continue

        is_section = (
            stripped == stripped.upper()
            and len(stripped) > 3
            and not stripped.startswith(("-", "•", "\u2022"))
            and ":" not in stripped
        )
        if is_section:
            out.append(f"## {stripped}")
        elif i == 0:
            out.append(f"# {stripped}")
        else:
            out.append(line.rstrip())
    return "\n".join(out)


def format_material_preview(text: str, kind: MaterialKind) -> str:
    """Return display-ready markdown for drawer previews (legacy-safe)."""
    text = text.strip()
    if not text:
        return text
    if kind == "cover":
        return format_cover_letter_markdown(text)
    return format_legacy_resume_markdown(text)
