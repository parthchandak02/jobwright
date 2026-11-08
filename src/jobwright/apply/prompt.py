"""Instructions for the apply agent: honest, answer bank first, no guessing.

``build_agent_system_prompt`` is the prompt for the tool-driven agent
(``apply/agent.py`` + ``apply/tools.py``). ``build_prompt`` keeps the old
signature for the legacy Playwright-MCP providers (dry runs only) and carries
the same rules.

What is deliberately NOT here any more (it was in the ApplyPilot fork):
passwords in the prompt, CAPTCHA-solving services, reading email, "do whatever
it takes", answering "yes" to tools the person has not used, declining EEO
questions on the person's behalf, default answers for criminal history / age /
background checks, and invented salary rules.
"""

from __future__ import annotations

from jobwright.apply.answers import ATTESTATION_CATEGORIES, AnswerBank

MAX_RESUME_CHARS = 14_000
MAX_JD_CHARS = 6_000

RULES = """\
RULES (they are checked by the tools too; a refused tool call means you broke one):
1. Be truthful. Never claim experience, skills, tools, titles, dates, degrees, licences or clearances that are
   not in the resume. If a question asks about something the resume does not show, answer honestly
   ("I have not used X professionally; I have used Y, which is similar because ...") or leave an optional
   field empty. Never round up years of experience. Never overstate to win the job.
2. Saved answers first. For any field that a saved answer covers (phone, address, links, education, how
   they heard, notice period, ...) use the saved value exactly (source="answer_bank").
3. ATTESTATIONS come ONLY from saved answers. Attestations are questions about: work authorization,
   visa sponsorship, criminal history or background checks, EEO / demographics (gender, race, ethnicity,
   veteran, disability, sexual orientation), age, "I certify / attest" statements, salary expectation,
   start date, relocation, and whether they worked for this employer before. Classify every question you
   fill: pass category=<one of {categories}> when it is one, else null. If the saved answer is
   "(NOT SAVED)", do NOT answer it, do not pick "decline", do not guess: call
   ask_human(kind='answer', prompt=<the exact question text>) and then finish(status='needs_answer',
   questions=[...every such question...]).
4. Open questions that are not attestations ("Why do you want to work here?", "Describe a project ...") may
   be written from the resume and the job description: concise (2-5 sentences unless a length is asked),
   specific, first person, plain language, nothing invented. source="resume_ai".
5. Upload the tailored resume to the resume field and the cover letter where one is requested.
6. CAPTCHA: never try to solve it and never use a solving service. Call ask_human(kind='captcha',
   prompt=...) and wait. If nobody solves it, finish(status='captcha_timeout').
7. Email verification code: you cannot read email. Call ask_human(kind='email_code', prompt='Please paste
   the code from <company>'), then fill_secret(ref, name='email_code').
8. Accounts: only if the site requires an account to apply. Use the person's email; for any password field
   use fill_secret(ref, name='account_password') (you never see it). Never use "Sign in with Google /
   LinkedIn / Apple". In a dry run, stop before creating an account: finish(status='dry_run_ready').
9. Stay on this employer's application. Never apply through LinkedIn Easy Apply or a job board.
10. Final submit: only when every required field is filled and no attestation is unanswered. In a dry run
   the submit click is blocked: fill everything, then finish(status='dry_run_ready').
11. After submitting, take a snapshot. If the page asks for a code, handle it (rule 7). Then
   finish(status='submitted') with a one-line summary. Do not say it was submitted unless you clicked the
   final submit button; the system checks the confirmation page itself.
12. If the posting is closed or gone: finish(status='expired'). If the site blocks you or you cannot
   continue: finish(status='blocked' or 'failed') with the reason. Never loop on the same failing action.
"""


def _job_block(job: dict) -> str:
    jd = (job.get("full_description") or job.get("description") or "")[:MAX_JD_CHARS]
    return (
        f"Title: {job.get('title') or ''}\n"
        f"Company: {job.get('company') or job.get('site') or ''}\n"
        f"Location: {job.get('location') or ''}\n"
        f"Application URL: {job.get('application_url') or job.get('url')}\n"
        f"Job description (excerpt):\n{jd}"
    )


def _identity_block(profile: dict, answers: AnswerBank) -> str:
    personal = profile.get("personal") or {}
    lines = [f"Full name: {personal.get('full_name') or ''}"]
    preferred = answers.get("preferred_name")
    if preferred:
        lines.append(f"Preferred name: {preferred}")
    lines.append(f"Email: {personal.get('email') or ''}")
    return "\n".join(lines)


def build_agent_system_prompt(
    *,
    job: dict,
    profile: dict,
    answers: AnswerBank,
    resume_text: str,
    cover_letter_text: str = "",
    dry_run: bool,
    has_resume_file: bool,
    has_cover_file: bool,
) -> str:
    mode = ("DRY RUN: fill the form completely but never submit and never create an account; "
            "finish with status='dry_run_ready'." if dry_run else
            "LIVE: submit the application when it is complete and honest.")
    uploads = [w for w, ok in (("resume", has_resume_file), ("cover_letter", has_cover_file)) if ok]
    parts = [
        "You fill in one job application in a real browser for the person below, using only the tools given. "
        "You act for them, so accuracy matters more than speed.",
        f"MODE: {mode}",
        RULES.format(categories=", ".join(ATTESTATION_CATEGORIES)),
        "== APPLICANT ==\n" + _identity_block(profile, answers),
        "== SAVED ANSWERS (use these exactly) ==\n" + answers.summary_for_prompt(),
        "== JOB ==\n" + _job_block(job),
        "== RESUME (the only source for experience) ==\n" + (resume_text or "(no resume text)")[:MAX_RESUME_CHARS],
    ]
    if cover_letter_text:
        parts.append("== COVER LETTER ==\n" + cover_letter_text[:4000])
    parts.append("Files you can upload: " + (", ".join(uploads) if uploads else "none"))
    return "\n\n".join(parts)


def build_prompt(job: dict, tailored_resume: str, dry_run: bool = True, worker_id: int = 0,
                 ats_context: str = "") -> str:
    """Legacy (MCP) providers: same rules, no secrets, dry runs only."""
    from jobwright import config
    from jobwright.apply.answers import load_answers

    try:
        profile = config.load_profile()
    except FileNotFoundError:
        profile = {}
    text = build_agent_system_prompt(
        job=job, profile=profile, answers=load_answers(), resume_text=tailored_resume, dry_run=True,
        has_resume_file=False, has_cover_file=False,
    )
    legacy = (
        "LEGACY PROVIDER: you are using Playwright MCP tools. You have no fill_secret or ask_human tool, so: "
        "never type a password, never create an account, never solve a CAPTCHA, and never submit. "
        "End with exactly one line: RESULT:DRYRUN, or RESULT:FAILED:<reason>."
    )
    return "\n\n".join(p for p in (text, ats_context, legacy) if p)


def open_question_prompt(job: dict, resume_text: str, cover_text: str = "") -> str:
    """System prompt for one open question asked by a deterministic filler."""
    return "\n\n".join(p for p in [
        "Write the applicant's answer to one open question on a job application form, in the first person.",
        "Use only facts from the resume (and the cover letter). Never invent experience, tools, numbers, "
        "titles or dates. 2-5 sentences unless the question asks for a length; plain language.",
        "If the question is an attestation (work authorization, sponsorship, criminal history, background "
        "check, demographics, age, certification, salary, start date, relocation, prior employment here) or "
        "cannot be answered truthfully from the resume, reply exactly NO_ANSWER.",
        "Reply with the answer text only.",
        "== JOB ==\n" + _job_block(job),
        "== RESUME ==\n" + (resume_text or "")[:MAX_RESUME_CHARS],
        ("== COVER LETTER ==\n" + cover_text[:4000]) if cover_text else "",
    ] if p)
