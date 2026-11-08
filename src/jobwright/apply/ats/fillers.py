"""Deterministic Playwright form fillers for Greenhouse, Lever and Ashby.

Each class implements ``jobwright.apply.fill.FormFiller`` (``fill``) plus
``submit(page)`` and ``verify(page) -> (ok, confidence, evidence)``. The
answer rules, the ``answers`` / ``materials`` keys and the open-question
callback are documented in ``apply/ats/forms.py``.

- Greenhouse (job-boards.greenhouse.io / boards.greenhouse.io hosted form):
  fields come from the public boards-api questions schema
  (``greenhouse.fetch_greenhouse_schema``): standard identity fields, location,
  resume / cover uploads, custom questions (text, textarea, single selects
  rendered as native selects or comboboxes, multi-select checkbox groups) and
  the EEO compliance block. Confirmation: ``/confirmation`` URL or thank-you text.
- Lever (jobs.lever.co/<co>/<id>/apply): one page, read from the DOM: name,
  email, phone, location, current company, link fields, resume upload,
  "Additional information" (cover letter text), custom cards (text, textarea,
  radio, checkboxes, select) and the EEO selects. Confirmation: ``/thanks``.
- Ashby (jobs.ashbyhq.com/<org>/<id>/application): fields from the posting's
  application-form schema (``ashby.fetch_ashby_form``) when given, else read
  from the DOM: system fields (name, email, resume, location), String /
  LongText / Email / Phone / Date / Number, ValueSelect (radios or combobox),
  MultiValueSelect (checkboxes), Boolean (Yes / No buttons), File, EEO survey.
  Confirmation: success container / thank-you text.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Callable

from jobwright.apply.ats.detect import detect_ats
from jobwright.apply.ats.forms import AnswerFn, BaseFiller, FieldSpec, css_attr

log = logging.getLogger(__name__)


def _sel_by_name(name: str) -> str:
    n = css_attr(name)
    return f'[id="{n}"], [name="{n}"]'


# -- Greenhouse -------------------------------------------------------------------

_GH_STD = {"first_name": "first_name", "last_name": "last_name", "email": "email", "phone": "phone",
           "preferred_name": "preferred_name", "resume": "resume", "cover_letter": "cover_letter",
           "location": "location"}
_GH_EEO = {"gender": "eeo_gender", "race": "eeo_race", "hispanic_ethnicity": "eeo_hispanic",
           "veteran_status": "eeo_veteran", "disability_status": "eeo_disability"}
_GH_KIND = {"input_text": "text", "textarea": "textarea", "input_file": "file",
            "multi_value_single_select": "select", "multi_value_multi_select": "multiselect"}


def greenhouse_specs(schema: dict) -> list[FieldSpec]:
    """FieldSpecs from a boards-api ``?questions=true`` job payload."""
    specs: list[FieldSpec] = []

    def add(q: dict, key: str | None = None) -> None:
        fields = [f for f in (q.get("fields") or []) if f.get("type") != "input_hidden"]
        if not fields:
            return
        files = [f for f in fields if f.get("type") == "input_file"]
        f = files[0] if files else fields[0]  # resume/cover: upload, not the paste box
        name = str(f.get("name") or "")
        kind = _GH_KIND.get(f.get("type"), "text")
        values = f.get("values") or []
        options = [str(v.get("label")) for v in values if v.get("label") is not None]
        label = " ".join(str(q.get("label") or name).split())
        std = _GH_STD.get(name)
        selector = _sel_by_name(name)
        container = None
        if kind == "multiselect":
            container = f'fieldset:has([name="{css_attr(name)}[]"]), fieldset:has([name="{css_attr(name)}"])'
        if name == "location":
            selector = '[id="candidate-location"], [name="location"], [id="location"]'
        if kind == "file":
            selector = f'input[type=file][id="{css_attr(name)}"], input[type=file][name="{css_attr(name)}"]'
        specs.append(FieldSpec(
            label=label, kind=kind, required=bool(q.get("required")), options=options,
            selector=selector, container=container, std=std, key=key or _GH_EEO.get(name),
            option_values={str(v.get("label")): str(v.get("value")) for v in values if v.get("label") is not None},
        ))

    for q in schema.get("questions") or []:
        add(q)
    for q in schema.get("location_questions") or []:
        add(q)
    for block in schema.get("compliance") or []:
        for q in (block or {}).get("questions") or []:
            add(q)
    demo = schema.get("demographic_questions")
    if isinstance(demo, dict):
        for q in demo.get("questions") or []:
            opts = [str(o.get("label")) for o in q.get("answer_options") or [] if o.get("label")]
            kind = "multiselect" if q.get("type") == "multi_value_multi_select" else "select"
            specs.append(FieldSpec(label=" ".join(str(q.get("label") or "").split()), kind=kind,
                                   required=bool(q.get("required")), options=opts))
    return specs


class GreenhouseFiller(BaseFiller):
    ats = "greenhouse"
    SUBMIT_SELECTORS = (
        "#application-form button[type=submit]", "#application_form #submit_app",
        "#application_form [type=submit]", "button:has-text('Submit application')", "button[type=submit]",
    )
    SUCCESS_URL = re.compile(r"/confirmation\b|[?&]submitted=true", re.I)
    SUCCESS_TEXT = re.compile(r"thank you for applying|thanks for applying|application (has been |was )?"
                              r"(submitted|received)|we(?: have|'ve) received your application", re.I)

    def __init__(self, answer_open_question: AnswerFn | None = None, *, schema: dict | None = None,
                 schema_fetcher: Callable[[str, str], dict] | None = None):
        super().__init__(answer_open_question)
        self.schema = schema
        self.schema_fetcher = schema_fetcher

    def _schema(self, page, job: dict) -> dict:
        if self.schema is not None:
            return self.schema
        from jobwright.apply.ats.greenhouse import fetch_greenhouse_schema, parse_greenhouse_url

        for url in (job.get("application_url"), page.url, job.get("url")):
            parsed = parse_greenhouse_url(url or "")
            if parsed:
                self.schema = (self.schema_fetcher or fetch_greenhouse_schema)(*parsed)
                return self.schema
        raise ValueError("not a Greenhouse job URL")

    def fields(self, page, job: dict) -> list[FieldSpec]:
        return greenhouse_specs(self._schema(page, job))


# -- DOM scanning (Lever, Ashby fallback) ---------------------------------------------

_SCAN_JS = r"""
([questionSel, labelSel]) => {
  const out = [];
  const seen = new Set();
  const txt = (el) => (el ? (el.innerText || el.textContent || '') : '').replace(/[✱*]/g, '').replace(/\s+/g, ' ').trim();
  const optLabel = (inp) => {
    const wrap = inp.closest('label');
    if (wrap) return txt(wrap);
    if (inp.id) { const l = document.querySelector(`label[for="${CSS.escape(inp.id)}"]`); if (l) return txt(l); }
    return inp.value;
  };
  for (const q of document.querySelectorAll(questionSel)) {
    if (q.parentElement && q.parentElement.closest(questionSel)) continue;
    const label = txt(q.querySelector(labelSel)) || txt(q.querySelector('label'));
    const required = !!q.querySelector('.required, [required], [aria-required="true"]')
      || /[✱*]\s*$/.test((q.querySelector(labelSel) || {}).innerText || '');
    const file = q.querySelector('input[type=file]');
    const radios = [...q.querySelectorAll('input[type=radio]')];
    const checks = [...q.querySelectorAll('input[type=checkbox]')];
    const sel = q.querySelector('select');
    const ta = q.querySelector('textarea');
    const combo = q.querySelector('input[role=combobox]');
    const buttons = [...q.querySelectorAll('button')].map(b => txt(b)).filter(t => /^(yes|no)$/i.test(t));
    const text = q.querySelector('input[type=text], input[type=email], input[type=tel], input[type=url], '
                                 + 'input[type=number], input[type=date], input:not([type])');
    let kind = null, name = '', options = [], values = {};
    if (file) { kind = 'file'; name = file.name || file.id; }
    else if (radios.length) {
      kind = 'radio'; name = radios[0].name;
      for (const r of radios) { const l = optLabel(r); options.push(l); values[l] = r.value; }
    } else if (buttons.length >= 2) {
      kind = 'boolean'; options = buttons;
      const hidden = q.querySelector('input[type=checkbox], input[type=hidden]');
      name = hidden ? (hidden.name || hidden.id) : '';
    } else if (checks.length > 1) {
      kind = 'multiselect'; name = checks[0].name;
      for (const c of checks) { const l = optLabel(c); options.push(l); values[l] = c.value; }
    } else if (checks.length === 1) { kind = 'checkbox'; name = checks[0].name || checks[0].id; }
    else if (sel) { kind = 'select'; name = sel.name || sel.id;
      options = [...sel.options].filter(o => o.value !== '').map(o => o.text.trim()); }
    else if (combo) { kind = 'combobox'; name = combo.name || combo.id; }
    else if (ta) { kind = 'textarea'; name = ta.name || ta.id; }
    else if (text) { kind = 'text'; name = text.name || text.id; }
    if (!kind || seen.has(kind + name + label)) continue;
    seen.add(kind + name + label);
    out.push({label, required, kind, name, options, values});
  }
  return out;
}
"""


def scan_dom(page, question_sel: str, label_sel: str) -> list[dict]:
    return page.evaluate(_SCAN_JS, [question_sel, label_sel])


# -- Lever --------------------------------------------------------------------------

_LEVER_STD = {"name": "full_name", "email": "email", "phone": "phone", "location": "location",
              "org": "current_company", "resume": "resume", "comments": "cover_letter",
              "urls[LinkedIn]": "linkedin_url", "urls[GitHub]": "github_url", "urls[Github]": "github_url",
              "urls[Portfolio]": "website_url", "urls[Website]": "website_url", "urls[Personal Website]": "website_url"}
_LEVER_EEO = {"eeo[gender]": "eeo_gender", "eeo[race]": "eeo_race", "eeo[veteran]": "eeo_veteran",
              "eeo[disability]": "eeo_disability"}


class LeverFiller(BaseFiller):
    ats = "lever"
    SUBMIT_SELECTORS = ("#btn-submit", "button[data-qa=btn-submit]", "button[type=submit]")
    SUCCESS_URL = re.compile(r"/thanks/?(?:[?#]|$)", re.I)
    SUCCESS_TEXT = re.compile(r"application submitted|thanks for applying|thank you for applying|"
                              r"we(?: have|'ve) received your application", re.I)

    def fields(self, page, job: dict) -> list[FieldSpec]:
        specs = []
        for raw in scan_dom(page, ".application-question", ".application-label .text, .application-label"):
            name = raw["name"]
            std = _LEVER_STD.get(name)
            if std is None and name.startswith("urls["):
                std = "skip"
            container = f'.application-question:has([name="{css_attr(name)}"])' if name else None
            specs.append(FieldSpec(
                label=raw["label"] or name, kind=raw["kind"], required=raw["required"], options=raw["options"],
                selector=_sel_by_name(name) if name else None, container=container, std=std,
                key=_LEVER_EEO.get(name), option_values=raw["values"],
            ))
        return specs


# -- Ashby --------------------------------------------------------------------------

_ASHBY_STD = {"_systemfield_name": "full_name", "_systemfield_email": "email", "_systemfield_phone": "phone",
              "_systemfield_resume": "resume", "_systemfield_location": "location",
              "_systemfield_cover_letter": "cover_letter"}
_ASHBY_EEO = {"_systemfield_eeoc_gender": "eeo_gender", "_systemfield_eeoc_race": "eeo_race",
              "_systemfield_eeoc_veteran_status": "eeo_veteran",
              "_systemfield_eeoc_disability_status": "eeo_disability"}
_ASHBY_KIND = {"String": "text", "Email": "text", "Phone": "text", "Date": "text", "Number": "text",
               "LongText": "textarea", "File": "file", "ValueSelect": "radio", "MultiValueSelect": "multiselect",
               "Boolean": "boolean", "Location": "combobox", "SocialLink": "text"}
_ASHBY_ENTRY = ".ashby-application-form-field-entry"


def ashby_specs(form: list[dict]) -> list[FieldSpec]:
    """FieldSpecs from ``ashby.fetch_ashby_form`` entries
    ({path, title, type, required, options})."""
    specs = []
    for e in form:
        path, ftype = str(e.get("path") or ""), str(e.get("type") or "String")
        kind = _ASHBY_KIND.get(ftype)
        if not path or kind is None:
            continue
        options = [str(o) for o in e.get("options") or []]
        if kind == "boolean" and not options:
            options = ["Yes", "No"]
        p = css_attr(path)
        container = (f'{_ASHBY_ENTRY}:has([for="{p}"]), {_ASHBY_ENTRY}:has([id="{p}"]), '
                     f'{_ASHBY_ENTRY}:has([name="{p}"])')
        selector = (f'input[type=file][id="{p}"], input[type=file][name="{p}"]' if kind == "file"
                    else _sel_by_name(path))
        specs.append(FieldSpec(
            label=" ".join(str(e.get("title") or path).split()), kind=kind, required=bool(e.get("required")),
            options=options, selector=selector, container=container,
            std=_ASHBY_STD.get(path), key=_ASHBY_EEO.get(path),
        ))
    return specs


class AshbyFiller(BaseFiller):
    ats = "ashby"
    SUBMIT_SELECTORS = ("button.ashby-application-form-submit-button", "button:has-text('Submit Application')",
                        "button[type=submit]")
    SUCCESS_SELECTOR = ".ashby-application-form-success-container"
    SUCCESS_TEXT = re.compile(r"thanks for applying|thank you for applying|application (was |has been )?"
                              r"(successfully )?(submitted|received)", re.I)

    def __init__(self, answer_open_question: AnswerFn | None = None, *, form: list[dict] | None = None,
                 form_fetcher: Callable[[str, str], list[dict]] | None = None):
        super().__init__(answer_open_question)
        self.form = form
        self.form_fetcher = form_fetcher

    def fields(self, page, job: dict) -> list[FieldSpec]:
        form = self.form
        if form is None and self.form_fetcher is not None:
            from jobwright.apply.ats.ashby import parse_ashby_url

            for url in (job.get("application_url"), page.url, job.get("url")):
                parsed = parse_ashby_url(url or "")
                if parsed:
                    try:
                        form = self.form = self.form_fetcher(*parsed)
                    except Exception as e:  # noqa: BLE001 - fall back to reading the page
                        log.info("ashby: form schema fetch failed (%s); reading the page", e)
                    break
        if form:
            return ashby_specs(form)
        specs = []
        for raw in scan_dom(page, _ASHBY_ENTRY, ".ashby-application-form-question-title, label"):
            name = raw["name"]
            container = (f'{_ASHBY_ENTRY}:has([name="{css_attr(name)}"]), {_ASHBY_ENTRY}:has([id="{css_attr(name)}"])'
                         if name else None)
            specs.append(FieldSpec(
                label=raw["label"] or name, kind=raw["kind"], required=raw["required"], options=raw["options"],
                selector=_sel_by_name(name) if name else None, container=container,
                std=_ASHBY_STD.get(name), key=_ASHBY_EEO.get(name), option_values=raw["values"],
            ))
        return specs


FILLERS: dict[str, type[BaseFiller]] = {"greenhouse": GreenhouseFiller, "lever": LeverFiller, "ashby": AshbyFiller}


def filler_for(url: str | None, answer_open_question: AnswerFn | None = None, **kw: Any) -> BaseFiller | None:
    """The deterministic filler for ``url``'s ATS, or None (no filler for that ATS)."""
    cls = FILLERS.get(detect_ats(url) or "")
    return cls(answer_open_question, **kw) if cls else None
