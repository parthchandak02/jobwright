"""User-visible tailor/cover instructions (dashboard Auto + Custom).

The batch pipeline still uses the heavier prompts in tailor.py / cover_letter.py.
Dashboard runs use these strings so the base resume stays mostly intact.
"""

from __future__ import annotations

DEFAULT_RESUME_INSTRUCTIONS = """The base resume is already the strongest version. Change as little as possible.

Goal: increase keyword overlap with THIS job description without rewriting the story.

Do:
- Keep every role, company, date, school, project, and metric exactly.
- In skills, move terms that already appear in the resume and match the JD to the front.
- In at most 2-4 bullets, swap in the job's own wording only when it is already true of that work.
- Keep the same number of bullets per role.

Do not:
- Invent tools, titles, companies, degrees, or numbers.
- Drop, merge, or omit roles.
- Rewrite the summary from scratch. A one-sentence tweak is enough.
- Paste long chunks of the job description."""

DEFAULT_COVER_INSTRUCTIONS = """Start from the candidate's real cover-letter samples. Keep their voice.

Tweak for this specific role: name the company and 1-2 true overlaps with the job description.

Do not rewrite the letter from scratch. Do not restate the resume. Do not invent stories.
Keep it under 250 words. No em dashes."""


def build_dashboard_resume_prompt(profile: dict, user_instructions: str) -> str:
    """Minimal JSON-resume prompt driven by user-editable instructions."""
    resume_facts = profile.get("resume_facts", {})
    companies = resume_facts.get("preserved_companies", [])
    school = resume_facts.get("preserved_school", "")
    metrics = resume_facts.get("real_metrics", [])
    education = profile.get("experience", {})
    education_level = education.get("education_level", "")
    companies_str = ", ".join(companies) if companies else "all companies in the base resume"
    metrics_str = ", ".join(metrics) if metrics else "all numbers in the base resume"
    instructions = (user_instructions or DEFAULT_RESUME_INSTRUCTIONS).strip()

    return f"""You copy the base resume into JSON and apply ONLY the user instructions.

The base resume is already the strongest version. Prefer leaving wording unchanged.

USER INSTRUCTIONS:
{instructions}

HARD RULES (these override the user if they conflict):
- Keep every preserved company in experience headers: {companies_str}
- Keep education: {school or "as in the base resume"}
- Do not invent facts or change real numbers ({metrics_str})
- Do not drop roles or projects to fit a page
- Return ONLY valid JSON. No markdown fences. No commentary.

JSON shape:
{{"title":"Role Title","summary":"keep close to the original","skills":{{"Languages":"...","Frameworks":"...","DevOps & Infra":"...","Databases":"...","Tools":"..."}},"experience":[{{"header":"Title at Company","subtitle":"Tech | Dates","bullets":["bullet 1","bullet 2"]}}],"projects":[{{"header":"Project Name","subtitle":"Tech | Dates","bullets":["bullet 1"]}}],"education":"{school} | {education_level}"}}"""


def build_dashboard_cover_prompt(
    profile: dict,
    *,
    template: str = "",
    examples: list[str] | None = None,
    user_instructions: str = "",
) -> str:
    """Minimal cover-letter prompt: samples plus user-editable instructions."""
    from jobwright import config
    from jobwright.scoring.validator import BANNED_WORDS, LLM_LEAK_PHRASES

    personal = profile.get("personal", {})
    sign_off_name = personal.get("preferred_name") or personal.get("full_name", "")
    instructions = (user_instructions or DEFAULT_COVER_INSTRUCTIONS).strip()
    all_banned = ", ".join(f'"{w}"' for w in BANNED_WORDS)
    leak_banned = ", ".join(f'"{p}"' for p in LLM_LEAK_PHRASES)

    examples_block = ""
    if examples:
        joined = config.join_cover_letter_examples(examples)
        examples_block = f"""
SAMPLE LETTERS (keep this voice; do not copy verbatim):
---
{joined}
---
"""
    template_block = ""
    if template:
        template_block = f"""
TEMPLATE:
---
{template[:4000]}
---
"""

    return f"""Write a cover letter for {sign_off_name}. Change as little as possible from the samples.

USER INSTRUCTIONS:
{instructions}
{template_block}{examples_block}
HARD RULES:
- Do not invent stories, employers, or metrics.
- Do not restate the resume bullet-for-bullet.
- No em dashes or en dashes.
- Banned words: {all_banned}
- Also banned: {leak_banned}
- Sign off with only "{sign_off_name}"
- Output ONLY the letter. Start with "Dear Hiring Manager,"."""
