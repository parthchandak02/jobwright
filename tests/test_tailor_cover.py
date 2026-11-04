"""Offline tests for resume tailoring, cover letters, validation and DOCX export.

The LLM is a fake client with canned replies; PDF conversion is stubbed out.
All data is placeholder (Alex Rivera, Example Org, example.com).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from jobwright import config
from jobwright.database import get_connection, init_db
from jobwright.scoring import cover_letter as cl
from jobwright.scoring import tailor
from jobwright.scoring import validator as val

PROFILE = {
    "personal": {
        "full_name": "Alex Rivera",
        "preferred_name": "Alex",
        "email": "user1@example.com",
    },
    "skills_boundary": {"languages": ["Python", "SQL"], "tools": ["Excel", "Tableau"]},
    "resume_facts": {
        "preserved_companies": ["Example Org"],
        "preserved_school": "Example State University",
        "real_metrics": ["40%"],
        "preserved_projects": ["Grant Tracker"],
    },
    "experience": {"education_level": "BA Economics"},
}

BASE_RESUME = """# Alex Rivera
Program Manager

## SUMMARY
Program manager for grant-funded community programs.

## TECHNICAL SKILLS
Tools: Python, SQL, Excel

## EXPERIENCE
Program Lead at Example Org
2021 - Present
- Cut grant reporting time 40% with Python scripts

## PROJECTS
Grant Tracker
- Built a grant tracker in Excel

## EDUCATION
Example State University | BA Economics
"""

GOOD_RESUME_JSON = {
    "title": "Program Manager",
    "summary": "Program manager who runs grant reporting and partner programs — end to end.",
    "skills": {"Tools": "Python, SQL, Excel", "Ops": "Trust and Safety, scalable processes"},
    "experience": [{
        "header": "Program Lead at Example Org",
        "subtitle": "2021 - Present",
        "bullets": ["Cut grant reporting time 40% with Python scripts",
                    "Ran quarterly planning for five program teams"],
    }],
    "projects": [{"header": "Grant Tracker", "subtitle": "Excel", "bullets": ["Built a grant tracker"]}],
    "education": "Example State University | BA Economics",
}

GOOD_LETTER = (
    "Dear Hiring Manager,\n\n"
    "I cut grant reporting time 40% at Example Org with Python scripts. "
    "Your climate grants team has the same reporting load.\n\n"
    "I also ran quarterly planning for five program teams and built a grant tracker in Excel.\n\n"
    "Happy to walk through any of this in more detail.\n\nAlex"
)


class FakeLLM:
    """Pops canned replies in order; records every message list it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls: list[list[dict]] = []
        self.kwargs: list[dict] = []

    def chat(self, messages, **kw):
        self.calls.append(messages)
        self.kwargs.append(kw)
        if not self.replies:
            raise AssertionError("FakeLLM ran out of replies")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def _resume_reply(**overrides) -> str:
    data = json.loads(json.dumps(GOOD_RESUME_JSON))
    data.update(overrides)
    return json.dumps(data)


@pytest.fixture()
def user_files(monkeypatch):
    """Profile + base resume markdown in the hermetic sandbox; PDFs stubbed."""
    Path(config.PROFILE_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(config.PROFILE_PATH).write_text(json.dumps(PROFILE), encoding="utf-8")
    md = Path(config.RESUME_MD_PATH)
    md.parent.mkdir(parents=True, exist_ok=True)
    md.write_text(BASE_RESUME, encoding="utf-8")

    def no_pdf(*_a, **_k):
        raise RuntimeError("pdf disabled in tests")

    monkeypatch.setattr("jobwright.scoring.pdf.convert_to_pdf", no_pdf)
    init_db()
    return Path(config.APP_DIR)


def _add_examples(texts: list[str]) -> None:
    """Fake example letters: a placeholder PDF plus a fresher .md cache."""
    d = Path(config.COVER_LETTER_EXAMPLES_DIR)
    d.mkdir(parents=True, exist_ok=True)
    for i, text in enumerate(texts):
        pdf = d / f"example_{i}.pdf"
        pdf.write_bytes(b"%PDF-1.4 placeholder")
        md = pdf.with_suffix(".md")
        md.write_text(text, encoding="utf-8")
        later = time.time() + 5
        os.utime(md, (later, later))


def _add_job(url="https://jobs.example.com/example-org/101", title="Program Manager, Climate (Remote)",
             company="Example Org", description="Run climate grant programs and partner reporting.",
             **cols):
    conn = get_connection()
    keys = ["url", "title", "company", "site", "full_description", *cols]
    vals = [url, title, company, "ExampleBoard", description, *cols.values()]
    conn.execute(
        f"INSERT INTO jobs ({', '.join(keys)}) VALUES ({', '.join('?' for _ in keys)})", vals
    )
    conn.commit()
    return url


def _row(url):
    return dict(get_connection().execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone())


# ---------------------------------------------------------------------------
# validator
# ---------------------------------------------------------------------------

def test_watchlist_is_whole_word_regression():
    data = json.loads(_resume_reply(skills={"Ops": "Trust and Safety, scalable processes, Springboard"}))
    assert val.validate_json_fields(data, PROFILE, mode="normal")["passed"] is True
    data["skills"] = {"Languages": "Python, Rust"}
    res = val.validate_json_fields(data, PROFILE, mode="normal")
    assert res["passed"] is False and "Fabricated skill: 'rust'" in res["errors"]
    data["skills"] = {"Certs": "PMP certification"}
    errs = val.validate_json_fields(data, PROFILE, mode="normal")["errors"]
    assert any("certif" in e for e in errs) and any("pmp" in e for e in errs)


def test_watchlist_allowed_by_profile():
    profile = {**PROFILE, "skills_boundary": {"languages": ["Python", "Rust"]}}
    data = json.loads(_resume_reply(skills={"Languages": "Python, Rust"}))
    assert val.validate_json_fields(data, profile)["passed"] is True


def test_validate_json_fields_modes_and_leaks():
    data = json.loads(_resume_reply(summary="A passionate operator."))
    assert val.validate_json_fields(data, PROFILE, mode="strict")["passed"] is False
    normal = val.validate_json_fields(data, PROFILE, mode="normal")
    assert normal["passed"] is True and normal["warnings"]
    assert val.validate_json_fields(data, PROFILE, mode="lenient")["warnings"] == []

    leak = json.loads(_resume_reply(summary="Here is the revised resume you asked for."))
    for mode in ("strict", "normal", "lenient"):
        assert val.validate_json_fields(leak, PROFILE, mode=mode)["passed"] is False

    missing = json.loads(_resume_reply())
    del missing["education"]
    assert "Missing required field: education" in val.validate_json_fields(missing, PROFILE)["errors"]

    no_school = json.loads(_resume_reply(education="Other College"))
    assert val.validate_json_fields(no_school, PROFILE)["passed"] is False
    assert val.validate_json_fields(no_school, PROFILE, mode="lenient")["passed"] is True


def test_validate_tailored_resume_text():
    ok = val.validate_tailored_resume(BASE_RESUME.replace("Program Lead", "Program Lead"), PROFILE, BASE_RESUME)
    assert ok["passed"] is True
    assert "Email missing -- will be injected" in ok["warnings"]

    bad = BASE_RESUME.replace("Tools: Python, SQL, Excel", "Tools: Python, Golang — Excel")
    bad = bad.replace("Example Org", "Other Co") + "\nI apologize for the delay.\n"
    res = val.validate_tailored_resume(bad, PROFILE, BASE_RESUME)
    errs = " | ".join(res["errors"])
    assert "golang" in errs and "Example Org" in errs and "em dash" in errs and "self-talk" in errs
    assert any("New tool/skill appeared: 'golang'" in w for w in res["warnings"])

    assert any("Missing required section" in e for e in val.validate_tailored_resume("hello", PROFILE)["errors"])


def test_validate_cover_letter_modes():
    assert val.validate_cover_letter(GOOD_LETTER)["passed"] is True
    assert "Must start with 'Dear Hiring Manager,'" in val.validate_cover_letter("Hi there")["errors"]
    long = GOOD_LETTER + " word" * 300
    assert val.validate_cover_letter(long, mode="strict")["passed"] is False
    assert val.validate_cover_letter(long, mode="normal")["warnings"]
    assert val.validate_cover_letter(long, mode="lenient") == {"passed": True, "errors": [], "warnings": []}
    banned = GOOD_LETTER.replace("I also", "Additionally, I")
    assert val.validate_cover_letter(banned, mode="strict")["passed"] is False
    assert val.validate_cover_letter(banned, mode="normal")["passed"] is True
    assert val.validate_cover_letter(GOOD_LETTER + " — x")["passed"] is False


def test_sanitize_text():
    assert val.sanitize_text(" a — b–c “q” ‘s’ ") == "a, b-c \"q\" 's'"


# ---------------------------------------------------------------------------
# tailor prompts + tailor_resume
# ---------------------------------------------------------------------------

def test_tailor_prompt_from_profile_and_examples(user_files):
    prompt = tailor._build_tailor_prompt(PROFILE)
    assert "Languages: Python, SQL" in prompt and "Tools: Excel, Tableau" in prompt
    assert "Preserved companies: Example Org" in prompt
    assert "Preserved school: Example State University" in prompt
    assert "(40%)" in prompt
    assert "spearheaded" in prompt  # banned words are spelled out
    assert "SENT COVER LETTERS" not in prompt

    _add_examples(["Dear team, I built the grant tracker that cut reporting in half."])
    with_examples = tailor._build_tailor_prompt(PROFILE)
    assert "SENT COVER LETTERS" in with_examples
    assert "EXAMPLE 1:\nDear team, I built the grant tracker" in with_examples

    judge = tailor._build_judge_prompt(PROFILE)
    assert "Python, SQL, Excel, Tableau" in judge and "40%" in judge


def _job():
    return {"url": "https://jobs.example.com/x", "title": "Program Manager", "company": "Example Org",
            "location": "Remote", "full_description": "Run climate grant programs."}


def test_tailor_resume_happy_path(monkeypatch):
    llm = FakeLLM([_resume_reply(), "VERDICT: PASS\nISSUES: none"])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    text, report = tailor.tailor_resume(BASE_RESUME, _job(), PROFILE)
    assert report["status"] == "approved" and report["attempts"] == 1
    assert report["judge"]["passed"] is True
    assert text.startswith("# Alex Rivera\nProgram Manager\nuser1@example.com")
    assert "—" not in text  # em dash auto-fixed
    system, user = llm.calls[0]
    assert system["role"] == "system" and "Example Org" in system["content"]
    assert "ORIGINAL RESUME:\n# Alex Rivera" in user["content"]
    assert "TITLE: Program Manager\nCOMPANY: Example Org\nLOCATION: Remote" in user["content"]
    assert llm.kwargs[0]["json_mode"] is True
    judge_msgs = llm.calls[1]
    assert "TAILORED RESUME:\n# Alex Rivera" in judge_msgs[1]["content"]


def test_tailor_resume_retries_bad_json_with_fresh_prompt(monkeypatch):
    llm = FakeLLM(["Sure! here you go", _resume_reply(), "VERDICT: PASS\nISSUES: none"])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    _, report = tailor.tailor_resume(BASE_RESUME, _job(), PROFILE)
    assert report["status"] == "approved" and report["attempts"] == 2
    assert "AVOID THESE ISSUES" not in llm.calls[0][0]["content"]
    assert "Output was not valid JSON" in llm.calls[1][0]["content"]
    assert len(llm.calls[1]) == 2  # fresh conversation, no history


def test_tailor_resume_validator_blocks_fabrication(monkeypatch):
    fake = _resume_reply(skills={"Languages": "Python, Golang"})
    llm = FakeLLM([fake, fake])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    text, report = tailor.tailor_resume(BASE_RESUME, _job(), PROFILE, max_retries=1)
    assert report["status"] == "failed_validation"
    assert "Fabricated skill: 'golang'" in report["validator"]["errors"]
    assert "Fabricated skill: 'golang'" in llm.calls[1][0]["content"]
    assert text  # last attempt is still assembled for inspection


def test_tailor_resume_judge_fail_then_pass_and_last_attempt_warning(monkeypatch):
    llm = FakeLLM([_resume_reply(), "VERDICT: FAIL\nISSUES: invented a degree",
                   _resume_reply(), "VERDICT: PASS\nISSUES: none"])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    _, report = tailor.tailor_resume(BASE_RESUME, _job(), PROFILE)
    assert report["status"] == "approved" and report["attempts"] == 2
    assert "Judge rejected: invented a degree" in llm.calls[2][0]["content"]

    llm = FakeLLM([_resume_reply(), "VERDICT: FAIL\nISSUES: stretch"])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    _, report = tailor.tailor_resume(BASE_RESUME, _job(), PROFILE, max_retries=0)
    assert report["status"] == "approved_with_judge_warning"


def test_tailor_resume_lenient_skips_judge_and_exhausts(monkeypatch):
    llm = FakeLLM([_resume_reply()])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    _, report = tailor.tailor_resume(BASE_RESUME, _job(), PROFILE, validation_mode="lenient")
    assert report["status"] == "approved" and report["judge"]["verdict"] == "SKIPPED"
    assert len(llm.calls) == 1

    llm = FakeLLM(["nope", "still nope"])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    text, report = tailor.tailor_resume(BASE_RESUME, _job(), PROFILE, max_retries=1)
    assert report["status"] == "exhausted_retries" and text == ""


def test_tailor_resume_dashboard_instructions_prompt(monkeypatch):
    llm = FakeLLM([_resume_reply(), "VERDICT: PASS"])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    tailor.tailor_resume(BASE_RESUME, _job(), PROFILE, extra_instructions="Only reorder bullets.")
    system = llm.calls[0][0]["content"]
    assert "USER INSTRUCTIONS:\nOnly reorder bullets." in system
    assert "RECRUITER SCAN" not in system


def test_tailor_resume_includes_selected_portfolio_projects(monkeypatch):
    profile = {**PROFILE, "portfolio": [{"id": "gt", "name": "Grant Tracker", "stack": ["Excel"],
                                         "bullets": ["Tracked 40 grants"]}]}
    job = {**_job(), "portfolio_project_ids": json.dumps(["gt"])}
    llm = FakeLLM([_resume_reply(), "VERDICT: PASS"])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    tailor.tailor_resume(BASE_RESUME, job, profile)
    user = llm.calls[0][1]["content"]
    assert "PRIORITY PORTFOLIO PROJECTS" in user and "- Grant Tracker: Excel\n  * Tracked 40 grants" in user


# ---------------------------------------------------------------------------
# tailor_one_job / run_tailoring: files, naming, DB
# ---------------------------------------------------------------------------

def test_tailor_one_job_writes_named_files_and_db(user_files, monkeypatch):
    from jobwright.database import job_id_for_url

    url = _add_job()
    llm = FakeLLM([_resume_reply(), "VERDICT: PASS\nISSUES: none"])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    result = tailor.tailor_one_job(url)

    prefix = f"Example_Org_Program_Manager_Climate_Remote_{job_id_for_url(url)}"
    md = Path(config.TAILORED_DIR) / f"{prefix}.md"
    assert result["status"] == "approved" and result["path"] == str(md)
    assert result["pdf_path"] is None  # PDF stubbed to fail; tailoring still succeeds
    assert md.read_text(encoding="utf-8").startswith("# Alex Rivera")
    job_txt = (Path(config.TAILORED_DIR) / f"{prefix}_JOB.txt").read_text(encoding="utf-8")
    assert "Company: Example Org" in job_txt and f"URL: {url}" in job_txt
    report = json.loads((Path(config.TAILORED_DIR) / f"{prefix}_REPORT.json").read_text(encoding="utf-8"))
    assert report["status"] == "approved"

    row = _row(url)
    assert row["tailored_resume_path"] == str(md)
    assert row["tailor_attempts"] == 1
    assert row["funnel_stage"] == "prepare"


def test_material_prefix_slugging_is_unique_per_url():
    from jobwright.job_identity import material_prefix

    a = material_prefix({"url": "https://e.example.com/1", "title": "Sr. Analyst / Data (NYC)!",
                         "company": "Sample & Co."})
    b = material_prefix({"url": "https://e.example.com/2", "title": "Sr. Analyst / Data (NYC)!",
                         "company": "Sample & Co."})
    assert a.startswith("Sample_Co_Sr_Analyst_Data_NYC_")
    assert a != b
    assert material_prefix({"url": "https://e.example.com/3", "title": None, "site": "linkedin"}).startswith(
        "company_untitled_")


def test_tailor_one_job_errors_and_failed_status(user_files, monkeypatch):
    with pytest.raises(ValueError, match="job not found"):
        tailor.tailor_one_job("https://jobs.example.com/missing")
    url = _add_job(url="https://jobs.example.com/nodesc", description=None)
    with pytest.raises(ValueError, match="description required"):
        tailor.tailor_one_job(url)

    url = _add_job(url="https://jobs.example.com/bad")
    bad = _resume_reply(skills={"Languages": "Golang"})
    monkeypatch.setattr(tailor, "get_client", lambda: FakeLLM([bad] * 4))
    result = tailor.tailor_one_job(url)
    assert result["status"] == "failed_validation" and result["path"] is None
    assert _row(url)["tailor_attempts"] == 1 and _row(url)["tailored_resume_path"] is None

    # subtle (dashboard) mode saves the last attempt anyway
    monkeypatch.setattr(tailor, "get_client", lambda: FakeLLM([bad] * 4))
    result = tailor.tailor_one_job(url, subtle=True)
    assert result["status"] == "approved_with_judge_warning" and result["path"]


def test_tailor_one_job_uses_short_description_when_no_full(user_files, monkeypatch):
    url = _add_job(url="https://jobs.example.com/short", description=None)
    get_connection().execute("UPDATE jobs SET description = 'Short listing text' WHERE url = ?", (url,))
    llm = FakeLLM([_resume_reply()])
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    tailor.tailor_one_job(url, validation_mode="lenient")
    assert "DESCRIPTION:\nShort listing text" in llm.calls[0][1]["content"]


def test_run_tailoring_batch_counts_and_none_title(user_files, monkeypatch):
    """A scored job with no title must not crash the batch (regression)."""
    _add_job(url="https://jobs.example.com/a", fit_score=9)
    _add_job(url="https://jobs.example.com/b", title=None, fit_score=8)
    _add_job(url="https://jobs.example.com/low", fit_score=3)
    bad = _resume_reply(skills={"Languages": "Golang"})
    llm = FakeLLM([_resume_reply(), "VERDICT: PASS"] + [bad] * 4)
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    stats = tailor.run_tailoring(min_score=7, limit=5)
    assert stats["approved"] == 1 and stats["failed"] == 1 and stats["errors"] == 0
    assert _row("https://jobs.example.com/low")["tailored_resume_path"] is None


def test_run_tailoring_nothing_pending(user_files):
    assert tailor.run_tailoring(min_score=7)["approved"] == 0


def test_run_tailoring_llm_crash_is_counted(user_files, monkeypatch):
    _add_job(url="https://jobs.example.com/crash", title=None, fit_score=9)
    monkeypatch.setattr(tailor, "get_client", lambda: FakeLLM([RuntimeError("provider down")]))
    stats = tailor.run_tailoring(min_score=7)
    assert stats["errors"] == 1
    assert _row("https://jobs.example.com/crash")["tailor_attempts"] == 1


# ---------------------------------------------------------------------------
# cover letters
# ---------------------------------------------------------------------------

def test_cover_prompt_from_profile_template_and_examples(user_files):
    prompt = cl._build_cover_letter_prompt(PROFILE)
    assert prompt.startswith("Write a cover letter for Alex.")
    assert 'Sign off: just "Alex"' in prompt
    assert "Python, SQL, Excel, Tableau" in prompt
    assert "Known projects to reference: Grant Tracker" in prompt
    assert "Real metrics to use: 40%" in prompt
    assert '"i apologize"' in prompt
    assert "RESUME RULE" not in prompt and "COVER LETTER TEMPLATE" not in prompt

    full = cl._build_cover_letter_prompt(
        {**PROFILE, "cover_letter_mode": "template"},
        template="Dear [Company] team,", examples=["Dear team, sample letter body."])
    assert "COVER LETTER TEMPLATE" in full and "Dear [Company] team," in full
    assert "EXAMPLE 1:\nDear team, sample letter body." in full
    assert "RESUME RULE" in full and "strategy/impact operator" in full


def test_strip_preamble():
    assert cl._strip_preamble("Here is the letter:\n\nDear Hiring Manager,\nHi") == "Dear Hiring Manager,\nHi"
    assert cl._strip_preamble("Dear X") == "Dear X"
    assert cl._strip_preamble("No greeting") == "No greeting"


def test_generate_cover_letter_sanitizes_and_retries(user_files, monkeypatch):
    _add_examples(["Dear team, I built the grant tracker that cut reporting in half."])
    llm = FakeLLM([
        "Dear Hiring Manager,\n\nI apologize, here is my attempt.\n\nAlex",
        "Here is the cover letter:\n\n" + GOOD_LETTER.replace("Python scripts.", "Python scripts — fast."),
    ])
    monkeypatch.setattr(cl, "get_client", lambda: llm)
    letter = cl.generate_cover_letter(BASE_RESUME, _job(), PROFILE)
    assert letter.startswith("Dear Hiring Manager,")
    assert "—" not in letter and "Python scripts, fast." in letter
    assert "EXAMPLE 1:\nDear team, I built the grant tracker" in llm.calls[0][0]["content"]
    assert "AVOID THESE ISSUES" in llm.calls[1][0]["content"]
    assert "self-talk" in llm.calls[1][0]["content"]


def test_generate_cover_letter_returns_last_attempt(monkeypatch):
    llm = FakeLLM(["Hello", "Hello again"])
    monkeypatch.setattr(cl, "get_client", lambda: llm)
    assert cl.generate_cover_letter(BASE_RESUME, _job(), PROFILE, max_retries=1) == "Hello again"


def test_generate_cover_letter_dashboard_instructions(user_files, monkeypatch):
    llm = FakeLLM([GOOD_LETTER])
    monkeypatch.setattr(cl, "get_client", lambda: llm)
    cl.generate_cover_letter(BASE_RESUME, _job(), PROFILE, extra_instructions="Keep it short.")
    assert "Keep it short." in llm.calls[0][0]["content"]


def test_cover_one_job_persists_and_records_errors(user_files, monkeypatch):
    from jobwright.database import job_id_for_url

    url = _add_job()
    monkeypatch.setattr(cl, "get_client", lambda: FakeLLM([GOOD_LETTER]))
    result = cl.cover_one_job(url)
    expected = Path(config.COVER_LETTER_DIR) / f"Example_Org_Program_Manager_Climate_Remote_{job_id_for_url(url)}_CL.md"
    assert result["path"] == str(expected)
    assert expected.read_text(encoding="utf-8").startswith("Dear Hiring Manager,")
    row = _row(url)
    assert row["cover_letter_path"] == str(expected) and row["cover_attempts"] == 1

    monkeypatch.setattr(cl, "get_client", lambda: FakeLLM([RuntimeError("provider down")]))
    failed = cl.cover_one_job(url)
    assert failed["path"] is None and failed["error"] == "provider down"
    assert _row(url)["cover_attempts"] == 2

    with pytest.raises(ValueError, match="job not found"):
        cl.cover_one_job("https://jobs.example.com/missing")


def test_run_cover_letters_only_tailored_jobs_and_none_title(user_files, monkeypatch):
    """Batch picks tailored, unlettered jobs; a None title must not crash it (regression)."""
    _add_job(url="https://jobs.example.com/t1", fit_score=9, tailored_resume_path="/tmp/x.md")
    _add_job(url="https://jobs.example.com/t2", title=None, fit_score=8, tailored_resume_path="/tmp/y.md")
    _add_job(url="https://jobs.example.com/untailored", fit_score=9)
    llm = FakeLLM([GOOD_LETTER, RuntimeError("provider down")])
    monkeypatch.setattr(cl, "get_client", lambda: llm)
    stats = cl.run_cover_letters(min_score=7)
    assert stats["generated"] == 1 and stats["errors"] == 1
    assert _row("https://jobs.example.com/untailored")["cover_letter_path"] is None


def test_run_cover_letters_nothing_pending(user_files):
    assert cl.run_cover_letters()["generated"] == 0


# ---------------------------------------------------------------------------
# per-job single runs + DOCX export
# ---------------------------------------------------------------------------

def _docx_text(path: str) -> list[str]:
    from docx import Document

    return [p.text for p in Document(path).paragraphs]


def test_run_single_job_materials_end_to_end(user_files, monkeypatch):
    url = _add_job(fit_score=9)
    llm = FakeLLM([_resume_reply(), GOOD_LETTER])  # lenient: no judge call
    monkeypatch.setattr(tailor, "get_client", lambda: llm)
    monkeypatch.setattr(cl, "get_client", lambda: llm)
    assert tailor.run_single_job_materials(url) == 0

    row = _row(url)
    resume_docx, cover_docx = row["tailored_resume_docx_path"], row["cover_letter_docx_path"]
    assert resume_docx.endswith(".docx") and Path(resume_docx).is_file()
    assert cover_docx.endswith("_CL.docx") and Path(cover_docx).is_file()
    resume_paras = _docx_text(resume_docx)
    assert resume_paras[0] == "Alex Rivera"
    assert "Summary" in resume_paras and "Cut grant reporting time 40% with Python scripts" in resume_paras
    assert any(p.startswith("Dear Hiring Manager") for p in _docx_text(cover_docx))
    # the cover letter was written from the tailored resume, not the base one
    assert "Ran quarterly planning" in llm.calls[1][1]["content"]


def test_run_single_job_resume_and_cover(user_files, monkeypatch):
    url = _add_job(fit_score=9)
    monkeypatch.setattr(tailor, "get_client", lambda: FakeLLM([_resume_reply()]))
    assert tailor.run_single_job_resume(url) == 0
    assert Path(_row(url)["tailored_resume_docx_path"]).is_file()

    llm = FakeLLM([GOOD_LETTER])
    monkeypatch.setattr(cl, "get_client", lambda: llm)
    assert tailor.run_single_job_cover(url, cover_instructions="Name the company.") == 0
    assert Path(_row(url)["cover_letter_docx_path"]).is_file()
    assert "## SUMMARY" in llm.calls[0][1]["content"]  # tailored resume fed to the cover
    assert "Name the company." in llm.calls[0][0]["content"]


def test_run_single_job_failures_return_rc1(user_files, monkeypatch):
    missing = "https://jobs.example.com/missing"
    assert tailor.run_single_job_resume(missing) == 1
    assert tailor.run_single_job_cover(missing) == 1
    assert tailor.run_single_job_materials(missing) == 1

    url = _add_job(fit_score=9)
    monkeypatch.setattr(cl, "get_client", lambda: FakeLLM([RuntimeError("provider down")]))
    assert tailor.run_single_job_cover(url) == 1

    monkeypatch.setattr(tailor, "get_client", lambda: FakeLLM(["not json"] * 4))
    assert tailor.run_single_job_resume(url) == 1


def test_docx_export_structured_and_batch(user_files, tmp_path):
    from jobwright.scoring import docx_export

    with pytest.raises(FileNotFoundError):
        docx_export.material_to_docx(tmp_path / "nope.md")

    md = Path(config.TAILORED_DIR)
    md.mkdir(parents=True, exist_ok=True)
    resume_md = md / "r.md"
    resume_md.write_text(tailor.assemble_resume_text(GOOD_RESUME_JSON, PROFILE), encoding="utf-8")
    cover_md = md / "c_CL.md"
    cover_md.write_text(GOOD_LETTER, encoding="utf-8")

    url = _add_job(fit_score=9, tailored_resume_path=str(resume_md), cover_letter_path=str(cover_md))
    _add_job(url="https://jobs.example.com/low", fit_score=2, tailored_resume_path=str(resume_md))
    stats = docx_export.batch_convert_docx(min_score=5)
    assert stats == {"status": "ok", "converted": 1, "errors": 0}
    row = _row(url)
    paras = _docx_text(row["tailored_resume_docx_path"])
    assert "Technical Skills" in paras and "Experience" in paras and "Education" in paras
    assert any(p.startswith("Tools: ") for p in paras)
    assert "Program Lead at Example Org" in paras

    from docx import Document

    bullets = [p for p in Document(row["tailored_resume_docx_path"]).paragraphs if p.style.name == "List Bullet"]
    assert any("40%" in p.text for p in bullets)

    # second run: everything already converted
    assert docx_export.batch_convert_docx(min_score=5)["converted"] == 0
    assert docx_export.convert_job_materials({"url": None})["resume_docx"] is None
