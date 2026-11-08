"""Deterministic ATS fillers (apply/ats/fillers.py) against offline fixture forms.

Real Playwright Chromium; every request is answered by route interception from
tests/fixtures/ats_forms (anything else gets an empty 204), so nothing leaves
the machine. No LLM: open questions go to a fake callback.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobwright.apply.ats.forms import choose_option, classify_question, contact_from_profile
from jobwright.apply.fill import FillResult

pw = pytest.importorskip("playwright.sync_api")

FIX = Path(__file__).parent / "fixtures" / "ats_forms"
GH_URL = "https://job-boards.greenhouse.io/exampleorg/jobs/4001"
LEVER_URL = "https://jobs.lever.co/exampleorg/0d1c2b3a-4f5e-6789-abcd-ef0123456789/apply"
ASHBY_URL = "https://jobs.ashbyhq.com/exampleorg/9c1d2e3f/application"

PAGES = {
    GH_URL: "greenhouse_form.html",
    GH_URL + "/confirmation": "greenhouse_confirmation.html",
    LEVER_URL: "lever_form.html",
    LEVER_URL.replace("/apply", "/thanks"): "lever_thanks.html",
    ASHBY_URL: "ashby_form.html",
}

PROFILE = {
    "first_name": "Test", "last_name": "Applicant", "full_name": "Test Applicant",
    "email": "applicant@example.com", "phone": "555-0100", "location": "Austin, Texas",
    "linkedin_url": "https://www.linkedin.com/in/test-applicant-example", "github_url": "https://github.com/example-applicant",
    "website_url": "https://applicant.example.com", "current_company": "Sample Works",
}
FULL_ANSWERS = {
    "work_authorized": "Yes", "requires_sponsorship": False, "criminal_record": "No", "certify": True,
    "salary_expectation": "USD 120,000", "how_heard": "LinkedIn", "eeo_gender": "Decline to self-identify",
    "eeo_hispanic": "Decline to self-identify", "eeo_veteran": "I am not a protected veteran",
    "eeo_disability": "I do not want to answer", "eeo_race": "Decline to self-identify",
}


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    ctx = browser.new_context()
    log: list[tuple[str, str]] = []

    def route(r):
        url = r.request.url
        log.append((r.request.method, url))
        if url.endswith("/static/combobox.js"):
            return r.fulfill(status=200, content_type="application/javascript",
                             body=(FIX / "combobox.js").read_text())
        key = url.split("?")[0].rstrip("/")
        name = PAGES.get(key)
        if name:
            return r.fulfill(status=200, content_type="text/html; charset=utf-8", body=(FIX / name).read_text())
        return r.fulfill(status=204, body="")

    ctx.route("**/*", route)
    pg = ctx.new_page()
    pg.requests = log
    yield pg
    ctx.close()


@pytest.fixture()
def materials(tmp_path):
    resume = tmp_path / "Test_Applicant_Resume.pdf"
    resume.write_bytes(b"%PDF-1.4 fake resume")
    cover = tmp_path / "Test_Applicant_Cover.pdf"
    cover.write_bytes(b"%PDF-1.4 fake cover")
    return {"resume_path": str(resume), "cover_letter_path": str(cover),
            "cover_letter_text": "Dear Example Org team, ...", "profile": dict(PROFILE)}


class OpenAnswers:
    def __init__(self):
        self.asked: list[str] = []

    def __call__(self, question, job):
        self.asked.append(question)
        return f"Answer for {job['company']}: {question[:30]}"


JOB = {"company": "Example Org", "title": "Operations Analyst", "url": GH_URL, "application_url": GH_URL}


def _posted(page) -> list[str]:
    return [u for m, u in page.requests if m == "POST"]


def _by_label(result: FillResult) -> dict:
    return {f.label: f for f in result.fields}


def _value(page, sel):
    return page.locator(sel).first.input_value()


# -- pure helpers -------------------------------------------------------------------

def test_classify_attestation_questions():
    cases = {
        "Are you legally authorized to work in the United States?": "work_authorized",
        "Will you now or in the future require sponsorship for employment visa status?": "requires_sponsorship",
        "Are you legally authorized to work in the US without requiring sponsorship?": "work_authorized",
        "Have you ever been convicted of a felony?": "criminal_record",
        "Do you consent to a background check?": "background_check",
        "Are you at least 18 years of age?": "age_18_plus",
        "I certify that the information I have provided is true and complete.": "certify",
        "What are your salary expectations?": "salary_expectation",
        "What is your earliest start date?": "start_date",
        "Are you willing to relocate to Denver?": "relocation",
        "Are you able to work on-site three days a week?": "onsite",
        "Have you previously worked for Example Org?": "previously_worked_here",
        "Veteran Status": "eeo_veteran", "Disability Status": "eeo_disability", "Gender": "eeo_gender",
        "Are you Hispanic/Latino?": "eeo_hispanic", "How did you hear about this job?": "how_heard",
        "Why do you want to work here?": None, "LinkedIn Profile": None,
    }
    for label, key in cases.items():
        assert classify_question(label) == key, label


def test_choose_option():
    assert choose_option(True, ["Yes", "No"]) == "Yes"
    assert choose_option("no", ["Yes, I will", "No, I won't"]) == "No, I won't"
    assert choose_option("Decline to self-identify", ["Male", "Female", "I don't wish to answer"]) == \
        "I don't wish to answer"
    assert choose_option("Yes", ["I acknowledge"]) == "I acknowledge"
    assert choose_option("Maybe", ["Yes", "No"]) is None


def test_contact_from_profile():
    c = contact_from_profile({"personal": {"full_name": "Test Middle Applicant", "email": "a@example.com",
                                           "city": "Austin", "province_state": "Texas"},
                              "experience": {"current_company": "Sample Works"}})
    assert (c["first_name"], c["last_name"], c["location"], c["current_company"]) == \
        ("Test", "Applicant", "Austin, Texas", "Sample Works")


# -- Greenhouse -----------------------------------------------------------------------

def _gh_filler(cb=None):
    from jobwright.apply.ats.fillers import GreenhouseFiller

    return GreenhouseFiller(cb, schema=json.loads((FIX / "greenhouse_schema.json").read_text()))


def test_greenhouse_fills_every_field_and_does_not_submit(page, materials):
    page.goto(GH_URL)
    cb = OpenAnswers()
    res = _gh_filler(cb).fill(page, JOB, FULL_ANSWERS, materials)
    assert res.needs == [] and res.ready_to_submit
    f = _by_label(res)
    assert f["First Name"].source == "resume" and _value(page, "#first_name") == "Test"
    assert _value(page, "#last_name") == "Applicant"
    assert _value(page, "#email") == "applicant@example.com"
    assert _value(page, "#candidate-location") == "Austin, Texas, United States"
    assert _value(page, "#question_1001") == PROFILE["linkedin_url"]
    assert _value(page, "#question_1002") == PROFILE["website_url"]
    assert _value(page, "#question_1003") == "Yes" and f[
        "Are you legally authorized to work in the United States?"].source == "answer_bank"
    assert page.locator("#question_1004 option:checked").inner_text() == "No"
    assert _value(page, "#question_1007") == "USD 120,000"
    assert page.locator("#question_1008 option:checked").inner_text() == "I acknowledge"
    assert page.locator("#gender option:checked").inner_text() == "Decline To Self Identify"
    assert page.locator("#veteran_status option:checked").inner_text() == "I am not a protected veteran"
    assert page.locator("#disability_status option:checked").inner_text() == "I do not want to answer"
    # Uploads
    assert page.eval_on_selector("#resume", "e => e.files[0].name") == "Test_Applicant_Resume.pdf"
    assert page.eval_on_selector("#cover_letter", "e => e.files[0].name") == "Test_Applicant_Cover.pdf"
    assert f["Resume/CV"].source == "file" and f["Resume/CV"].value == "Test_Applicant_Resume.pdf"
    # Open-ended question went to the callback; nothing else did.
    assert cb.asked == ["Why do you want to work at Example Org?"]
    assert f["Why do you want to work at Example Org?"].source == "ai"
    assert _value(page, "#question_1005").startswith("Answer for Example Org")
    # Optional multi-select with no bank answer stays empty.
    assert page.locator("input[name='question_1006[]']:checked").count() == 0
    # Never submitted; the invisible reCAPTCHA is not a captcha need.
    assert _posted(page) == [] and page.evaluate("window.__submitted || 0") == 0


def test_greenhouse_multiselect_from_question_answers(page, materials):
    page.goto(GH_URL)
    answers = dict(FULL_ANSWERS, questions={"Which of these tools have you used?": ["SQL", "Python"]})
    res = _gh_filler(OpenAnswers()).fill(page, JOB, answers, materials)
    assert res.ready_to_submit
    checked = page.eval_on_selector_all("input[name='question_1006[]']:checked", "els => els.map(e => e.value)")
    assert checked == ["502", "503"]


def test_greenhouse_missing_attestations_become_needs(page, materials):
    page.goto(GH_URL)
    answers = {k: v for k, v in FULL_ANSWERS.items() if k not in ("work_authorized", "certify", "salary_expectation")}
    res = _gh_filler(None).fill(page, JOB, answers, materials)
    details = [n.detail for n in res.needs]
    assert all(n.kind == "answer" for n in res.needs)
    assert any(d.startswith("work_authorized:") for d in details)
    assert any(d.startswith("certify:") for d in details)
    assert any(d.startswith("salary_expectation:") for d in details)
    # No callback: the required open question is a need too, and nothing was guessed.
    assert any(d.startswith("question: Why do you want") for d in details)
    assert not res.ready_to_submit
    assert _value(page, "#question_1003") == "" and _value(page, "#question_1007") == ""
    assert _posted(page) == []


def test_greenhouse_answer_matching_no_option_is_a_need(page, materials):
    page.goto(GH_URL)
    res = _gh_filler(OpenAnswers()).fill(page, JOB, dict(FULL_ANSWERS, work_authorized="Maybe"), materials)
    assert [n.detail.split(":")[0] for n in res.needs] == ["work_authorized"]


def test_greenhouse_visible_recaptcha_is_a_captcha_need(page, materials):
    page.goto(GH_URL)
    page.evaluate("""() => { const f = document.createElement('iframe');
        f.src = 'https://www.google.com/recaptcha/api2/anchor?ar=1&k=test&size=normal';
        f.width = 304; f.height = 78; document.querySelector('form').appendChild(f); }""")
    res = _gh_filler(OpenAnswers()).fill(page, JOB, FULL_ANSWERS, materials)
    assert [n for n in res.needs if n.kind == "captcha"][0].detail.startswith("recaptcha")
    assert not res.ready_to_submit
    assert _posted(page) == []


def test_greenhouse_submit_and_verify(page, materials):
    page.goto(GH_URL)
    filler = _gh_filler(OpenAnswers())
    assert filler.fill(page, JOB, FULL_ANSWERS, materials).ready_to_submit
    ok, conf, _ = filler.verify(page, timeout_ms=300)
    assert not ok and conf == "low"  # still on the form
    assert filler.submit(page)
    page.wait_for_url("**/confirmation")
    ok, conf, evidence = filler.verify(page)
    assert ok and conf == "high" and "/confirmation" in evidence
    assert _posted(page) == [GH_URL + "/confirmation"]


def test_greenhouse_schema_fetcher_from_url(page, materials):
    from jobwright.apply.ats.fillers import GreenhouseFiller

    seen = []

    def fetch(board, job_id):
        seen.append((board, job_id))
        return json.loads((FIX / "greenhouse_schema.json").read_text())

    page.goto(GH_URL)
    res = GreenhouseFiller(OpenAnswers(), schema_fetcher=fetch).fill(page, JOB, FULL_ANSWERS, materials)
    assert seen == [("exampleorg", "4001")] and res.ready_to_submit


# -- Lever ------------------------------------------------------------------------------

LEVER_JOB = {"company": "Example Org", "title": "Program Manager", "url": LEVER_URL, "application_url": LEVER_URL}
LEVER_ANSWERS = dict(FULL_ANSWERS, questions={"Which time zones can you work in?": "Pacific; Eastern"})


def test_lever_fills_single_page_form(page, materials):
    from jobwright.apply.ats.fillers import LeverFiller

    page.goto(LEVER_URL)
    cb = OpenAnswers()
    res = LeverFiller(cb).fill(page, LEVER_JOB, LEVER_ANSWERS, materials)
    assert res.needs == [] and res.ready_to_submit
    assert _value(page, "input[name=name]") == "Test Applicant"
    assert _value(page, "input[name=email]") == "applicant@example.com"
    assert _value(page, "input[name=phone]") == "555-0100"
    assert _value(page, "input[name=location]") == "Austin, Texas"
    assert _value(page, "input[name=org]") == "Sample Works"
    assert _value(page, "input[name='urls[LinkedIn]']") == PROFILE["linkedin_url"]
    assert _value(page, "input[name='urls[GitHub]']") == PROFILE["github_url"]
    assert _value(page, "input[name='urls[Portfolio]']") == PROFILE["website_url"]
    assert _value(page, "input[name='urls[Twitter]']") == ""  # unknown link fields are left alone
    assert page.eval_on_selector("input[name=resume]", "e => e.files[0].name") == "Test_Applicant_Resume.pdf"
    assert page.locator("input[name='cards[c1][field0]'][value=Yes]").is_checked()
    assert page.locator("input[name='cards[c1][field1]'][value=No]").is_checked()
    zones = page.eval_on_selector_all("input[name='cards[c2][field1]']:checked", "els => els.map(e => e.value)")
    assert zones == ["Pacific", "Eastern"]
    assert page.locator("select[name='cards[c3][field0]'] option:checked").inner_text() == "No"
    assert _value(page, "textarea[name=comments]") == "Dear Example Org team, ..."
    assert page.locator("select[name='eeo[gender]'] option:checked").inner_text() == "Decline to self-identify"
    assert page.locator("select[name='eeo[race]'] option:checked").inner_text() == "Decline to self-identify"
    assert cb.asked == ["What excites you about this role?"]
    assert _posted(page) == [] and page.evaluate("window.__submitted || 0") == 0


def test_lever_missing_answers_and_hcaptcha(page, materials):
    from jobwright.apply.ats.fillers import LeverFiller

    page.goto(LEVER_URL)
    page.evaluate("""() => { const f = document.createElement('iframe');
        f.src = 'https://newassets.hcaptcha.com/captcha/v1/abc/static/hcaptcha.html#frame=checkbox';
        f.style.width = '300px'; f.style.height = '80px'; document.getElementById('h-captcha').appendChild(f); }""")
    answers = {k: v for k, v in FULL_ANSWERS.items() if k not in ("criminal_record", "requires_sponsorship")}
    res = LeverFiller(OpenAnswers()).fill(page, LEVER_JOB, answers, materials)
    kinds = sorted({n.kind for n in res.needs})
    assert kinds == ["answer", "captcha"]
    keys = {n.detail.split(":")[0] for n in res.needs if n.kind == "answer"}
    assert keys == {"criminal_record", "requires_sponsorship", "question"}  # time zones: no bank answer
    assert not res.ready_to_submit
    assert page.locator("select[name='cards[c3][field0]']").input_value() == ""


def test_lever_submit_and_verify(page, materials):
    from jobwright.apply.ats.fillers import LeverFiller

    page.goto(LEVER_URL)
    filler = LeverFiller(OpenAnswers())
    assert filler.fill(page, LEVER_JOB, LEVER_ANSWERS, materials).ready_to_submit
    assert filler.submit(page)
    page.wait_for_url("**/thanks")
    ok, conf, evidence = filler.verify(page)
    assert ok and conf == "high" and "Application submitted" in evidence


# -- Ashby ------------------------------------------------------------------------------

ASHBY_JOB = {"company": "Example Org", "title": "Data Engineer", "url": ASHBY_URL, "application_url": ASHBY_URL}


def _ashby_form():
    from jobwright.apply.ats.ashby import normalize_form

    return normalize_form(json.loads((FIX / "ashby_form.json").read_text()))


@pytest.mark.parametrize("mode", ["schema", "dom"])
def test_ashby_fills_form(page, materials, mode):
    from jobwright.apply.ats.fillers import AshbyFiller

    page.goto(ASHBY_URL)
    cb = OpenAnswers()
    filler = AshbyFiller(cb, form=_ashby_form()) if mode == "schema" else AshbyFiller(cb)
    materials["profile"]["location"] = "Denver"
    res = filler.fill(page, ASHBY_JOB, FULL_ANSWERS, materials)
    assert res.needs == [] and res.ready_to_submit
    assert _value(page, "#_systemfield_name") == "Test Applicant"
    assert _value(page, "#_systemfield_email") == "applicant@example.com"
    assert page.eval_on_selector("#_systemfield_resume", "e => e.files[0].name") == "Test_Applicant_Resume.pdf"
    assert _value(page, "#_systemfield_location") == "Denver, Colorado, United States"
    assert _value(page, "[id='5b0f6c1e-0d0e-4b7a-9a51-3f1f3c2d1a01']") == "555-0100"
    assert page.locator("._yesno").get_attribute("data-answer") == "Yes"
    assert page.locator("input[value=LinkedIn]").is_checked()
    assert page.locator("input[name='5b0f6c1e-0d0e-4b7a-9a51-3f1f3c2d1a04']:checked").count() == 0
    assert _value(page, "[id='5b0f6c1e-0d0e-4b7a-9a51-3f1f3c2d1a06']") == "USD 120,000"
    assert _value(page, "#_systemfield_eeoc_gender") == "Decline to self-identify"
    assert cb.asked == ["Tell us about a data pipeline you are proud of."]
    assert page.evaluate("window.__submitted || 0") == 0 and _posted(page) == []


def test_ashby_missing_work_authorization_is_a_need(page, materials):
    from jobwright.apply.ats.fillers import AshbyFiller

    page.goto(ASHBY_URL)
    answers = {k: v for k, v in FULL_ANSWERS.items() if k != "work_authorized"}
    res = AshbyFiller(OpenAnswers(), form=_ashby_form()).fill(page, ASHBY_JOB, answers, materials)
    assert [n.detail.split(":")[0] for n in res.needs] == ["work_authorized"]
    assert page.locator("._yesno").get_attribute("data-answer") is None


def test_ashby_turnstile_submit_and_verify(page, materials):
    from jobwright.apply.ats.fillers import AshbyFiller

    page.goto(ASHBY_URL)
    filler = AshbyFiller(OpenAnswers(), form=_ashby_form())
    assert filler.fill(page, ASHBY_JOB, FULL_ANSWERS, materials).ready_to_submit
    assert filler.submit(page)
    ok, conf, evidence = filler.verify(page)
    assert ok and conf == "high"

    page.goto(ASHBY_URL)
    page.evaluate("""() => { const d = document.createElement('div'); d.className = 'cf-turnstile';
        d.style.width = '300px'; d.style.height = '65px'; document.body.appendChild(d); }""")
    res = filler.fill(page, ASHBY_JOB, FULL_ANSWERS, materials)
    assert any(n.kind == "captcha" and n.detail.startswith("turnstile") for n in res.needs)


def test_filler_for_and_ashby_url():
    from jobwright.apply.ats.ashby import parse_ashby_url
    from jobwright.apply.ats.fillers import AshbyFiller, GreenhouseFiller, LeverFiller, filler_for

    assert isinstance(filler_for(GH_URL), GreenhouseFiller)
    assert isinstance(filler_for(LEVER_URL), LeverFiller)
    assert isinstance(filler_for(ASHBY_URL), AshbyFiller)
    assert filler_for("https://exampleorg.wd1.myworkdayjobs.com/x") is None
    assert parse_ashby_url(ASHBY_URL) == ("exampleorg", "9c1d2e3f")


def test_fetch_ashby_form_posts_graphql():
    import httpx

    from jobwright.apply.ats.ashby import fetch_ashby_form

    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=json.loads((FIX / "ashby_form.json").read_text()))

    form = fetch_ashby_form("exampleorg", "9c1d2e3f", client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert seen[0]["variables"] == {"organizationHostedJobsPageName": "exampleorg", "jobPostingId": "9c1d2e3f"}
    assert [e["path"] for e in form][:3] == ["_systemfield_name", "_systemfield_email", "_systemfield_resume"]
    assert form[-1]["path"] == "_systemfield_eeoc_gender" and form[-1]["options"][-1] == "Decline to self-identify"
