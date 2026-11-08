"""Shared engine for the deterministic ATS form fillers (Greenhouse, Lever, Ashby).

A filler turns the page (or the ATS's public form schema) into ``FieldSpec``s,
then ``BaseFiller.fill`` decides a value for each one and types / selects /
uploads it with Playwright. No LLM is called here: open-ended questions go to
the injected ``answer_open_question(question, job) -> str`` callback.
``fill`` never clicks the final submit button: it reports
``ready_to_submit``; ``submit(page)`` and ``verify(page)`` are separate.

Inputs
------
``materials``::

    {"resume_path": "/abs/resume.pdf",          # required for a resume upload
     "cover_letter_path": "/abs/cover.pdf",     # optional upload
     "cover_letter_text": "Dear ...",           # optional, for cover-letter text boxes
     "profile": {                               # contact fields (source "resume")
        "first_name", "last_name", "full_name", "preferred_name", "email", "phone",
        "location", "linkedin_url", "github_url", "website_url",
        "current_company", "current_title"}}

``contact_from_profile(profile_json)`` builds ``profile`` from profile.json.

``answers`` (the answer bank; source "answer_bank"). Attestation questions are
answered ONLY from these keys; a required one that is missing becomes
``Need("answer", "<key>: <question>")`` and is left blank::

    work_authorized        "Yes"/"No"  legally authorized to work in the job's country
    requires_sponsorship   "Yes"/"No"  needs visa sponsorship now or later
    criminal_record        "Yes"/"No"  convicted of a felony / crime
    background_check       "Yes"/"No"  consents to a background check / drug screen
    age_18_plus            "Yes"/"No"
    certify                "Yes"       certify / acknowledge / agree / consent boxes
    salary_expectation     text        e.g. "USD 120,000"
    start_date             text        e.g. "Two weeks after an offer"
    relocation             "Yes"/"No"  willing to relocate
    onsite                 "Yes"/"No"  able to work on-site / in office / hybrid
    previously_worked_here "Yes"/"No"
    how_heard              text        e.g. "LinkedIn" (matched onto the options)
    referral               "Yes"/"No"  referred by an employee
    eeo_gender, eeo_race, eeo_hispanic, eeo_veteran, eeo_disability, eeo_lgbtq
                           option text, e.g. "Decline to self-identify"
    questions              {question label: answer} exact per-question answers
                           (normalized label match; wins over everything)

Booleans are accepted (True -> "Yes"). Answers are matched onto select /
radio options (exact, yes/no, "decline" synonyms, prefix, word containment);
an answer that matches no option becomes a Need too.

Other choice questions without a bank answer: required -> Need, optional ->
skipped. Other text questions -> the callback (source "ai"); no callback or an
empty reply: required -> Need, optional -> skipped.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from jobwright.apply.fill import FieldRecord, FillResult, Need

log = logging.getLogger(__name__)

AnswerFn = Callable[[str, dict], str]

TEXT_KINDS = ("text", "textarea", "combobox")
CHOICE_KINDS = ("select", "radio", "multiselect", "checkbox", "boolean")

ANSWER_KEYS = (
    "work_authorized", "requires_sponsorship", "criminal_record", "background_check", "age_18_plus",
    "certify", "salary_expectation", "start_date", "relocation", "onsite", "previously_worked_here",
    "how_heard", "referral", "eeo_gender", "eeo_race", "eeo_hispanic", "eeo_veteran", "eeo_disability",
    "eeo_lgbtq",
)

_Q = [
    ("previously_worked_here", r"\b(previously|ever|formerly|before|past)\b.{0,40}\b(work|employ)|"
                               r"former (employee|contractor)|worked (here|for us)"),
    ("requires_sponsorship", r"\b(require|need)s?\b.{0,60}\bsponsor"),
    ("work_authorized", r"(authori[sz]ed|eligible|permitted|legally able|right) to work|work authori[sz]ation|"
                        r"work permit|employment eligibility"),
    ("requires_sponsorship", r"sponsor|\bvisa\b|h-?1b|immigration status"),
    ("criminal_record", r"convicted|felony|criminal|misdemeanou?r"),
    ("background_check", r"background (check|screen|investigation)|drug (test|screen)"),
    ("age_18_plus", r"\b(18|eighteen)\b.{0,30}\b(years|older|age)|at least 18|legal (working )?age|\bage\b"),
    ("salary_expectation", r"salary|compensation|pay (expectation|range|requirement)|desired pay|expected pay"),
    ("start_date", r"start date|when can you start|earliest.{0,20}start|notice period|available to start"),
    ("relocation", r"relocat"),
    ("onsite", r"\b(on-?site|in[- ]office|in[- ]person|commut\w*|hybrid)\b"),
    ("eeo_hispanic", r"hispanic|latin[oax]"),
    ("eeo_race", r"\brace\b|ethnicity"),
    ("eeo_gender", r"\bgender\b|\bsex\b"),
    ("eeo_veteran", r"veteran"),
    ("eeo_disability", r"disabilit"),
    ("eeo_lgbtq", r"sexual orientation|transgender|lgbt"),
    ("how_heard", r"how did you (hear|learn|find)|where did you (hear|find|see)|source of (this )?application"),
    ("referral", r"\breferr(ed|al)\b"),
    ("certify", r"\b(certify|acknowledge|attest|i agree|i consent|consent to|agree to)\b|privacy (policy|notice)|"
                r"true and (complete|accurate)|accurate and complete"),
]
_Q_RES = [(k, re.compile(p, re.I)) for k, p in _Q]

_STD = [
    ("cover_letter", r"cover letter"),
    ("resume", r"resume|résumé|\bcv\b"),
    ("preferred_name", r"preferred (first )?name"),
    ("first_name", r"^\s*(legal )?first name|given name|^first$"),
    ("last_name", r"^\s*(legal )?last name|surname|family name|^last$"),
    ("full_name", r"^\s*(full |legal |your )?name\s*\*?$|^full legal name"),
    ("email", r"e-?mail"),
    ("phone", r"phone|mobile"),
    ("linkedin_url", r"linkedin"),
    ("github_url", r"github"),
    ("website_url", r"website|portfolio|personal (site|url)|other url"),
    ("current_company", r"current (company|employer)|^\s*company\s*$|^\s*organi[sz]ation\s*$"),
    ("current_title", r"current (job )?title|^\s*title\s*$"),
    ("location", r"^\s*location|current (city|location)|^\s*city\b|where are you (located|based)"),
]
_STD_RES = [(k, re.compile(p, re.I)) for k, p in _STD]


def classify_question(label: str | None) -> str | None:
    """Answer-bank key for an attestation / screening question label, or None."""
    text = " ".join((label or "").split())
    for key, rx in _Q_RES:
        if rx.search(text):
            return key
    return None


def standard_field(label: str | None) -> str | None:
    text = " ".join((label or "").split())
    for key, rx in _STD_RES:
        if rx.search(text):
            return key
    return None


def norm_label(text: str | None) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def contact_from_profile(profile: dict) -> dict:
    """materials['profile'] from a jobwright profile.json."""
    personal = (profile or {}).get("personal") or {}
    exp = (profile or {}).get("experience") or {}
    full = (personal.get("full_name") or "").strip()
    parts = full.split()
    loc = ", ".join(p for p in (personal.get("city"), personal.get("province_state"), personal.get("country")) if p)
    return {
        "full_name": full,
        "first_name": parts[0] if parts else "",
        "last_name": parts[-1] if len(parts) > 1 else "",
        "preferred_name": personal.get("preferred_name") or "",
        "email": personal.get("email") or "",
        "phone": personal.get("phone") or "",
        "location": loc,
        "linkedin_url": personal.get("linkedin_url") or "",
        "github_url": personal.get("github_url") or "",
        "website_url": personal.get("website_url") or personal.get("portfolio_url") or "",
        "current_company": exp.get("current_company") or "",
        "current_title": exp.get("current_job_title") or "",
    }


def _as_text(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "" if value is None else str(value).strip()


_YES = {"yes", "y", "true", "i do", "i am", "agree", "i agree", "accept"}
_NO = {"no", "n", "false", "i do not", "i am not"}
_AFFIRM = re.compile(r"\b(yes|agree|acknowledge|accept|certify|confirm|consent|understand)\b")
_NEGATE = re.compile(r"\b(no|not|don t|do not|disagree|decline)\b")
_DECLINE = ("decline", "prefer not", "don t wish", "do not wish", "not wish", "choose not", "rather not")


def choose_option(value: Any, options: list[str]) -> str | None:
    """The option ``value`` means, or None when it matches none (or several)."""
    v = norm_label(_as_text(value))
    if not v or not options:
        return None
    normed = [(o, norm_label(o)) for o in options]
    for o, n in normed:
        if n == v:
            return o
    first = lambda n: n.split(" ")[0] if n else ""  # noqa: E731
    if v in _YES:
        hits = [o for o, n in normed if first(n) == "yes"]
        if len(hits) == 1:
            return hits[0]
    if v in _NO:
        hits = [o for o, n in normed if first(n) == "no"]
        if len(hits) == 1:
            return hits[0]
    if v in _YES:  # "I acknowledge", "I agree", "Accept" ...
        hits = [o for o, n in normed if _AFFIRM.search(n) and not _NEGATE.search(n)]
        if len(hits) == 1:
            return hits[0]
    if any(d in v for d in _DECLINE):
        hits = [o for o, n in normed if any(d in n for d in _DECLINE)]
        if len(hits) == 1:
            return hits[0]
    hits = [o for o, n in normed if len(v) >= 3 and (n.startswith(v) or v.startswith(n) and len(n) >= 3)]
    if len(hits) == 1:
        return hits[0]
    vt = set(v.split())
    hits = [o for o, n in normed if vt and vt <= set(n.split())]
    if len(hits) == 1:
        return hits[0]
    # Closest wording ("I am not a protected veteran" -> "I am not a veteran"): a unique best >= 0.75.
    scored = sorted(((len(vt & set(n.split())) / len(vt | set(n.split())), o) for o, n in normed if n),
                    reverse=True)
    if scored and scored[0][0] >= 0.75 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
        return scored[0][1]
    return None


@dataclass
class FieldSpec:
    """One form question. ``selector`` finds its input; ``container`` its wrapper."""

    label: str
    kind: str  # text | textarea | combobox | select | radio | multiselect | checkbox | boolean | file
    required: bool = False
    options: list[str] = field(default_factory=list)
    selector: str | None = None
    container: str | None = None
    std: str | None = None  # standard field key (first_name, resume, ...) when known
    key: str | None = None  # answer-bank key when known (eeo_gender, ...)
    option_values: dict[str, str] = field(default_factory=dict)  # option label -> input value


def css_attr(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


# -- CAPTCHA -------------------------------------------------------------------

_CAPTCHA_JS = r"""
() => {
  const kinds = [];
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width >= 10 && r.height >= 10 && st.visibility !== 'hidden' && st.display !== 'none'
      && parseFloat(st.opacity || '1') > 0.05;
  };
  for (const f of document.querySelectorAll('iframe')) {
    const src = f.getAttribute('src') || '';
    let kind = null;
    if (/recaptcha\/(api2|enterprise)\/(anchor|bframe)/.test(src)) kind = 'recaptcha';
    else if (/hcaptcha\.com/.test(src)) kind = 'hcaptcha';
    else if (/challenges\.cloudflare\.com/.test(src)) kind = 'turnstile';
    if (!kind || /size=invisible/.test(src) || !visible(f)) continue;
    kinds.push(kind);
  }
  const widgets = [['.g-recaptcha', 'recaptcha'], ['.h-captcha', 'hcaptcha'], ['.cf-turnstile', 'turnstile']];
  for (const [sel, kind] of widgets) {
    for (const el of document.querySelectorAll(sel)) {
      if ((el.getAttribute('data-size') || '') === 'invisible') continue;
      if (visible(el) && !kinds.includes(kind)) kinds.push(kind);
    }
  }
  return kinds;
}
"""


def detect_captcha(page) -> list[str]:
    """Visible CAPTCHA challenges on the page: 'recaptcha' | 'hcaptcha' | 'turnstile'."""
    try:
        return list(dict.fromkeys(page.evaluate(_CAPTCHA_JS)))
    except Exception as e:  # noqa: BLE001 - a detached frame must not crash a fill
        log.debug("captcha probe failed: %s", e)
        return []


# -- filler ----------------------------------------------------------------------

class BaseFiller:
    """Decide + apply values for FieldSpecs. Subclasses implement ``fields``."""

    ats = "other"
    SUBMIT_SELECTORS: tuple[str, ...] = ("button[type=submit]", "input[type=submit]")
    SUCCESS_URL: re.Pattern[str] | None = None
    SUCCESS_SELECTOR: str | None = None
    SUCCESS_TEXT: re.Pattern[str] = re.compile(r"thank you for applying|application (was |has been )?(submitted|"
                                               r"received)|thanks for applying", re.I)
    ERROR_TEXT: re.Pattern[str] = re.compile(r"(is|are) required|please (complete|fill|correct)|"
                                             r"there was (an|a problem)|error", re.I)

    def __init__(self, answer_open_question: AnswerFn | None = None):
        self.answer_open_question = answer_open_question

    # subclasses
    def fields(self, page, job: dict) -> list[FieldSpec]:
        raise NotImplementedError

    # -- decisions --------------------------------------------------------------
    def decide(self, spec: FieldSpec, job: dict, answers: dict, materials: dict):
        """(value, source) to fill, (None, Need) when blocked, (None, None) to skip."""
        label = spec.label
        per_q = {norm_label(k): v for k, v in ((answers or {}).get("questions") or {}).items()}
        if norm_label(label) in per_q and _as_text(per_q[norm_label(label)]):
            return self._choice_or_need(spec, per_q[norm_label(label)], "answer_bank", "question")

        std = spec.std
        if std == "skip":  # a field we deliberately leave alone (e.g. a Twitter URL)
            return None, (Need("answer", f"question: {label}") if spec.required else None)
        if spec.kind == "file":
            std = std or standard_field(label) or "resume"
            path = (materials or {}).get("resume_path" if std == "resume" else "cover_letter_path")
            if path and Path(path).exists():
                return str(path), "file"
            return None, (Need("answer", f"{std}: {label} (no file)") if spec.required else None)

        key = spec.key or classify_question(label)
        if key:
            value = (answers or {}).get(key)
            if not _as_text(value) and not isinstance(value, list):
                return None, (Need("answer", f"{key}: {label}") if spec.required else None)
            return self._choice_or_need(spec, value, "answer_bank", key)

        if spec.kind in TEXT_KINDS:
            std = std or standard_field(label)
            if std == "cover_letter":
                text = (materials or {}).get("cover_letter_text")
                if text:
                    return text, "file"
                return None, (Need("answer", f"cover_letter: {label}") if spec.required else None)
            if std == "resume":  # "paste your resume" box next to the upload: the upload covers it
                return None, None
            if std:
                value = _as_text(((materials or {}).get("profile") or {}).get(std))
                if value:
                    return value, "resume"
                return None, (Need("answer", f"{std}: {label}") if spec.required else None)
            if self.answer_open_question is not None:
                try:
                    reply = _as_text(self.answer_open_question(label, job))
                except Exception as e:  # noqa: BLE001
                    log.warning("open-question callback failed for %r: %s", label, e)
                    reply = ""
                if reply:
                    return reply, "ai"
            return None, (Need("answer", f"question: {label}") if spec.required else None)

        # Choice question nobody has a bank answer for.
        return None, (Need("answer", f"question: {label} [{' | '.join(spec.options)}]") if spec.required else None)

    def _choice_or_need(self, spec: FieldSpec, value: Any, source: str, key: str):
        if spec.kind in ("select", "radio", "boolean", "combobox") and spec.options:
            choice = choose_option(value, spec.options)
            if choice is None:
                return None, Need("answer", f"{key}: {spec.label} (answer {_as_text(value)!r} matches none of "
                                            f"[{' | '.join(spec.options)}])")
            return choice, source
        if spec.kind == "multiselect":
            wanted = value if isinstance(value, list) else re.split(r"\s*[;|]\s*", _as_text(value))
            picks = [choose_option(w, spec.options) for w in wanted if _as_text(w)]
            if not picks or None in picks:
                return None, Need("answer", f"{key}: {spec.label} (answer {value!r} matches none of "
                                            f"[{' | '.join(spec.options)}])")
            return picks, source
        if spec.kind == "checkbox":
            text = norm_label(_as_text(value))
            if text in _YES or text.startswith("yes"):
                return "Yes", source
            if text in _NO:
                return None, (Need("answer", f"{key}: {spec.label} (answered No)") if spec.required else None)
            return None, Need("answer", f"{key}: {spec.label} (answer {_as_text(value)!r} is not yes/no)")
        return _as_text(value), source

    # -- playwright ---------------------------------------------------------------
    def _locator(self, page, spec: FieldSpec):
        if spec.selector:
            loc = page.locator(spec.selector)
            if loc.count():
                return loc.first
        try:
            loc = page.get_by_label(spec.label, exact=True)
            if loc.count():
                return loc.first
        except Exception:  # noqa: BLE001
            pass
        return None

    def _container(self, page, spec: FieldSpec):
        if spec.container:
            loc = page.locator(spec.container)
            if loc.count():
                return loc.first
        return page

    def apply(self, page, spec: FieldSpec, value) -> bool:
        """Put ``value`` into the field. True when it took."""
        kind = spec.kind
        if kind in ("radio", "boolean"):
            return self._pick_radio(page, spec, value)
        if kind == "multiselect":
            box = self._container(page, spec)
            ok = True
            for v in value:
                ok = self._check_option(box, spec, v) and ok
            return ok
        loc = self._locator(page, spec)
        if loc is None:
            log.info("%s: no input found for %r", self.ats, spec.label)
            return False
        if kind == "file":
            loc.set_input_files(value)
            return True
        if kind == "checkbox":
            loc.check()
            return loc.is_checked()
        tag = loc.evaluate("e => e.tagName.toLowerCase()")
        role = (loc.get_attribute("role") or "").lower()
        if tag == "select":
            loc.select_option(label=value)
            return True
        if role == "combobox" or kind == "combobox":
            return self._pick_combobox(page, loc, value)
        loc.fill(value)
        return True

    def _pick_combobox(self, page, loc, value: str) -> bool:
        loc.click()
        loc.fill(value)
        listbox_id = loc.get_attribute("aria-controls")
        scope = page.locator(f'[id="{css_attr(listbox_id)}"]') if listbox_id else page
        options = scope.locator("[role=option]")
        try:
            options.first.wait_for(state="visible", timeout=1500)
        except Exception:  # noqa: BLE001 - free-text combobox: the typed value stays
            return True
        texts = [t.strip() for t in options.all_inner_texts()]
        choice = choose_option(value, texts) or (texts[0] if len(texts) == 1 else None)
        if choice is None and texts:
            choice = texts[0]  # autocomplete (e.g. location): best suggestion first
        if choice is None:
            return False
        options.nth(texts.index(choice)).click()
        return True

    def _check_option(self, box, spec: FieldSpec, option: str) -> bool:
        inp_value = spec.option_values.get(option)
        if inp_value is not None:
            loc = box.locator(f'input[value="{css_attr(inp_value)}"]')
            if loc.count():
                loc.first.check()
                return True
        loc = box.get_by_label(option, exact=True)
        if loc.count():
            loc.first.check()
            return True
        return False

    def _pick_radio(self, page, spec: FieldSpec, option: str) -> bool:
        box = self._container(page, spec)
        if self._check_option(box, spec, option):
            return True
        btn = box.get_by_role("button", name=option, exact=True)
        if btn.count():
            btn.first.click()
            return True
        loc = self._locator(page, spec)
        if loc is not None:
            if loc.evaluate("e => e.tagName.toLowerCase()") == "select":
                loc.select_option(label=option)
                return True
            if (loc.get_attribute("role") or "").lower() == "combobox":
                return self._pick_combobox(page, loc, option)
        return False

    # -- protocol --------------------------------------------------------------------
    def fill(self, page, job: dict, answers: dict, materials: dict) -> FillResult:
        result = FillResult()
        for kind in detect_captcha(page):
            result.needs.append(Need("captcha", f"{kind} challenge on {self.ats} form"))
        try:
            specs = self.fields(page, job)
        except Exception as e:  # noqa: BLE001
            log.warning("%s: could not read the form: %s", self.ats, e)
            result.needs.append(Need("answer", f"form: could not read the {self.ats} form ({e})"))
            return result
        if not specs:
            result.needs.append(Need("answer", f"form: no {self.ats} application fields found"))
        for spec in specs:
            value, outcome = self.decide(spec, job, answers or {}, materials or {})
            if value is None:
                if isinstance(outcome, Need):
                    result.needs.append(outcome)
                continue
            try:
                ok = self.apply(page, spec, value)
            except Exception as e:  # noqa: BLE001
                log.info("%s: filling %r failed: %s", self.ats, spec.label, e)
                ok = False
            if not ok:
                if spec.required:
                    result.needs.append(Need("answer", f"field: could not fill {spec.label}"))
                continue
            shown = ", ".join(value) if isinstance(value, list) else str(value)
            if outcome == "file":
                shown = Path(shown).name if spec.kind == "file" else shown
            result.fields.append(FieldRecord(spec.label, shown, outcome, spec.required))
        result.ready_to_submit = not result.needs
        return result

    def submit(self, page) -> bool:
        """Click the form's final submit button (call only after a human/core approves)."""
        for sel in self.SUBMIT_SELECTORS:
            loc = page.locator(sel)
            if loc.count():
                loc.first.click()
                return True
        return False

    def verify(self, page, timeout_ms: int = 8000) -> tuple[bool, str, str]:
        """(ok, confidence 'high'|'medium'|'low', evidence) after ``submit``."""
        try:
            page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        except Exception:  # noqa: BLE001
            pass
        deadline_checks = max(1, timeout_ms // 250)
        url_ok = text_ok = False
        text = ""
        for _ in range(deadline_checks):
            url_ok = bool(self.SUCCESS_URL and self.SUCCESS_URL.search(page.url or ""))
            if not url_ok and self.SUCCESS_SELECTOR:
                try:
                    url_ok = page.locator(self.SUCCESS_SELECTOR).first.is_visible()
                except Exception:  # noqa: BLE001
                    url_ok = False
            try:
                text = page.locator("body").inner_text(timeout=1000)
            except Exception:  # noqa: BLE001
                text = ""
            m = self.SUCCESS_TEXT.search(text)
            text_ok = bool(m)
            if url_ok or text_ok:
                break
            page.wait_for_timeout(250)
        if url_ok and text_ok:
            return True, "high", f"confirmation page {page.url}; text {m.group(0)!r}"
        if url_ok:
            return True, "medium", f"confirmation page {page.url}"
        if text_ok:
            return True, "medium", f"text {m.group(0)!r}"
        captchas = detect_captcha(page)
        if captchas:
            return False, "low", f"captcha shown after submit: {', '.join(captchas)}"
        err = self.ERROR_TEXT.search(text)
        return False, "low", (f"form error: {err.group(0)!r}" if err else f"no confirmation at {page.url}")
