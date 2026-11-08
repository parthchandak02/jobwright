"""Browser tools the apply agent may call, with the safety rules in code.

The model only ever sees what these return. Rules enforced here (not just in
the prompt):

- Attestation questions (keyword list or the model's own ``category``) are
  filled ONLY with the person's saved answer; a missing one records a
  ``Need`` and the tool refuses. A value that does not match the saved answer
  is refused.
- Passwords and one-time codes are typed by ``fill_secret``; the value is
  never returned to the model and is scrubbed from the transcript.
- Dry run: clicking the final submit or an account-creation control is
  refused, ``fill_secret`` is refused, and (in ``BrowserSession``) every
  non-GET request is aborted.
- Live: the final submit takes the "filled" and "review" screenshots first
  and refuses while an attestation is unanswered.
- ``navigate`` only goes to the job's own hosts.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from jobwright.apply import answers as answers_mod
from jobwright.apply.browser import BrowserSession, host_allowed
from jobwright.apply.evidence import Transcript
from jobwright.apply.fill import FieldRecord, Need
from jobwright.apply.materials import Materials
from jobwright.apply.secret_store import MemorySecretStore, SecretStore, account_password

log = logging.getLogger(__name__)

AGENT_SOURCES = ("answer_bank", "profile", "resume_ai")
FINISH_STATUSES = ("submitted", "dry_run_ready", "needs_answer", "captcha_timeout", "expired", "blocked", "failed")

_NAV_WORDS = re.compile(r"^\s*(next|continue|back|previous|save( and continue)?|search|upload|add|remove|"
                        r"cancel|close|edit|sign in|log ?in|start|begin)\b", re.I)
_SUBMIT_WORDS = re.compile(r"\b(submit|send (my )?application|complete (my )?application|finish( application)?|"
                           r"confirm and submit)\b", re.I)
_ACCOUNT_WORDS = re.compile(r"\b(create (an )?account|sign ?up|register|create profile|join now)\b", re.I)
_CAPTCHA_HINT = ("recaptcha", "hcaptcha", "turnstile", "challenges.cloudflare", "captcha")

# JS: tag interactive elements with data-jw-ref and describe them.
_SNAPSHOT_JS = r"""
(prefix) => {
  const sel = 'input, select, textarea, button, a[href], [role=button], [role=checkbox], [role=radio], ' +
              '[role=combobox], [role=option], [contenteditable=true]';
  const vis = (el) => {
    if (el.type === 'hidden') return false;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    if (el.type === 'file') return true;
    return (r.width > 0 || r.height > 0) && st.visibility !== 'hidden' && st.display !== 'none';
  };
  const txt = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const labelOf = (el) => {
    let t = el.getAttribute('aria-label');
    if (t) return txt(t);
    const lb = el.getAttribute('aria-labelledby');
    if (lb) { const parts = lb.split(/\s+/).map(id => document.getElementById(id)).filter(Boolean);
      if (parts.length) return txt(parts.map(p => p.innerText).join(' ')); }
    if (el.id) { const l = document.querySelector(`label[for="${CSS.escape(el.id)}"]`); if (l) return txt(l.innerText); }
    const wrap = el.closest('label'); if (wrap) return txt(wrap.innerText);
    if (el.placeholder) return txt(el.placeholder);
    if (['BUTTON', 'A'].includes(el.tagName) || el.getAttribute('role') === 'button') return txt(el.innerText || el.value);
    if (el.type === 'submit' || el.type === 'button') return txt(el.value);
    return txt(el.name || el.title || '');
  };
  const groupOf = (el) => {
    const fs = el.closest('fieldset');
    if (fs) { const lg = fs.querySelector('legend'); if (lg) return txt(lg.innerText); }
    const g = el.closest('[role=radiogroup], [role=group]');
    if (g) { const l = g.getAttribute('aria-label') || (g.getAttribute('aria-labelledby') &&
              (document.getElementById(g.getAttribute('aria-labelledby')) || {}).innerText); if (l) return txt(l); }
    return '';
  };
  const out = [];
  let n = 0;
  for (const el of document.querySelectorAll(sel)) {
    if (!vis(el)) continue;
    n += 1;
    const ref = prefix + 'e' + n;
    el.setAttribute('data-jw-ref', ref);
    const type = (el.getAttribute('type') || '').toLowerCase();
    const item = { ref, tag: el.tagName.toLowerCase(), type, role: el.getAttribute('role') || '',
                   label: labelOf(el).slice(0, 300), group: groupOf(el).slice(0, 300),
                   name: el.name || '', required: !!(el.required || el.getAttribute('aria-required') === 'true'),
                   in_form: !!el.closest('form') };
    if (el.tagName === 'SELECT') item.options = Array.from(el.options).map(o => txt(o.text)).slice(0, 60);
    if (type === 'checkbox' || type === 'radio') item.checked = el.checked;
    else if (type !== 'password' && type !== 'file' && 'value' in el && el.tagName !== 'BUTTON')
      item.value = String(el.value || '').slice(0, 200);
    if (el.tagName === 'A') item.href = el.getAttribute('href');
    out.push(item);
  }
  const captcha = !!document.querySelector('.g-recaptcha, .h-captcha, .cf-turnstile, [data-sitekey], ' +
      'iframe[src*="recaptcha"], iframe[src*="hcaptcha"], iframe[src*="turnstile"], iframe[title*="captcha" i]');
  const body = txt(document.body ? document.body.innerText : '').slice(0, 2500);
  return { elements: out, captcha, text: body, title: document.title };
}
"""


@dataclass
class ElementInfo:
    ref: str
    frame_index: int
    data: dict

    @property
    def label(self) -> str:
        return self.data.get("label") or ""

    @property
    def question(self) -> str:
        group = self.data.get("group") or ""
        return group or self.label


def is_final_submit(el: dict) -> bool:
    text = (el.get("label") or "").strip()
    tag, typ, role = el.get("tag"), el.get("type"), el.get("role")
    clickable = tag == "button" or role == "button" or (tag == "input" and typ in ("submit", "button")) or tag == "a"
    if not clickable:
        return False
    if _NAV_WORDS.search(text):
        return False
    if _SUBMIT_WORDS.search(text):
        return True
    if typ == "submit" or (tag == "button" and typ in ("", "submit") and el.get("in_form")):
        return bool(re.search(r"\bapply\b", text, re.I)) or not text
    return False


def is_account_control(el: dict) -> bool:
    return bool(_ACCOUNT_WORDS.search(el.get("label") or ""))


@dataclass
class ToolState:
    fields: list[FieldRecord] = field(default_factory=list)
    needs: list[Need] = field(default_factory=list)
    screenshots: dict[str, str] = field(default_factory=dict)
    submitted: bool = False
    submit_selector: str | None = None
    url_before_submit: str = ""
    finished: dict | None = None
    captcha_seen: bool = False
    filler_submitted: bool = False
    steps: int = 0


HumanCallback = Callable[[str, str], "str | None"]


class ApplyTools:
    def __init__(
        self,
        session: BrowserSession,
        *,
        job: dict,
        answers: answers_mod.AnswerBank,
        materials: Materials,
        secret_store: SecretStore,
        dry_run: bool,
        run_dir: Path,
        transcript: Transcript,
        nav_hosts: set[str],
        ask_human: HumanCallback | None = None,
    ) -> None:
        self.session = session
        self.job = job
        self.answers = answers
        self.materials = materials
        self.secret_store = secret_store
        self.dry_run = dry_run
        self.run_dir = run_dir
        self.transcript = transcript
        self.nav_hosts = nav_hosts
        self._ask_human = ask_human
        self.session_secrets = MemorySecretStore()
        self.state = ToolState()
        self._elements: dict[str, ElementInfo] = {}
        self._shot_n = 0

    # ------------------------------------------------------------------ util
    @property
    def page(self):
        return self.session.page

    def _frames(self) -> list:
        frames = [self.page.main_frame]
        for fr in self.page.frames:
            if fr is self.page.main_frame:
                continue
            if fr.url and host_allowed(fr.url, self.nav_hosts):
                frames.append(fr)
        return frames

    def _locator(self, ref: str):
        info = self._elements.get(ref)
        if info is None:
            raise KeyError(f"Unknown ref {ref!r}: take a new snapshot first")
        frames = self._frames()
        frame = frames[info.frame_index] if info.frame_index < len(frames) else self.page.main_frame
        return frame.locator(f'[data-jw-ref="{ref}"]').first, info

    def shot(self, name: str, full_page: bool = False) -> str | None:
        saved = self.session.screenshot(self.run_dir / f"{name}.png", full_page=full_page)
        if saved:
            self.state.screenshots[name] = saved
        return saved

    def _need(self, kind: str, prompt: str, key: str | None = None, category: str | None = None) -> Need:
        for n in self.state.needs:
            if n.kind == kind and n.detail == prompt:
                return n
        need = Need(kind=kind, detail=prompt, key=key, category=category)
        self.state.needs.append(need)
        return need

    def open_answer_needs(self) -> list[Need]:
        return [n for n in self.state.needs if n.kind == "answer"]

    def _attestation_check(self, question: str, value: str, model_category: str | None) -> tuple[str | None, str]:
        """(error, key). error None = OK to use ``value`` for this question."""
        category = model_category if model_category in answers_mod.ATTESTATION_CATEGORIES else None
        if not answers_mod.is_attestation(question, category):
            return None, ""
        key, saved = self.answers.lookup(question, company=self.job.get("company") or "", model_category=category)
        cat = category or answers_mod.classify_question(question)
        if saved is None:
            self._need("answer", question, key=key, category=cat)
            return (f"NEEDS_ANSWER: '{question}' is an attestation ({cat}) and the person has not saved an "
                    "answer. Do not answer it. Call finish(status='needs_answer')."), key or ""
        if not answers_mod.value_agrees(saved, value):
            return (f"REFUSED: the saved answer for '{question}' is {saved!r}. Use exactly that "
                    "(or the option that means the same)."), key or ""
        return None, key or ""

    def _record(self, label: str, value: str, source: str, key: str | None = None, attestation: bool = False,
                ref: str | None = None) -> None:
        # Replace an earlier record for the same element.
        self.state.fields = [f for f in self.state.fields if not (ref and f.selector == ref)]
        self.state.fields.append(FieldRecord(label=label, value=value, source=source, key=key or None,
                                             attestation=attestation, selector=ref))

    # ----------------------------------------------------------------- tools
    def snapshot(self) -> str:
        self._elements = {}
        lines: list[str] = []
        captcha = False
        texts = []
        for i, frame in enumerate(self._frames()):
            try:
                data = frame.evaluate(_SNAPSHOT_JS, f"f{i}" if i else "")
            except Exception as exc:  # noqa: BLE001
                log.debug("snapshot frame %d failed: %s", i, exc)
                continue
            captcha = captcha or bool(data.get("captcha"))
            if i == 0:
                texts.append(data.get("text") or "")
            for el in data.get("elements", []):
                self._elements[el["ref"]] = ElementInfo(el["ref"], i, el)
                lines.append(self._describe(el))
        self.state.captcha_seen = self.state.captcha_seen or captcha
        head = [f"URL: {self.page.url}", f"Title: {self.page.title()}"]
        if captcha:
            head.append("CAPTCHA_DETECTED: do not try to solve it. Call ask_human(kind='captcha').")
        if self.dry_run:
            head.append("MODE: dry run (final submit and account creation are blocked).")
        head.append("Page text: " + (texts[0] if texts else "")[:2500])
        head.append("Elements:")
        return "\n".join(head + lines[:250])

    @staticmethod
    def _describe(el: dict) -> str:
        bits = [el["ref"], el["tag"] + (f"[{el['type']}]" if el.get("type") else ""),
                (f"role={el['role']}" if el.get("role") else "")]
        if el.get("group"):
            bits.append(f"group={el['group']!r}")
        bits.append(f"label={el.get('label')!r}")
        if el.get("required"):
            bits.append("required")
        if "checked" in el:
            bits.append(f"checked={el['checked']}")
        if el.get("value"):
            bits.append(f"value={el['value']!r}")
        if el.get("options"):
            bits.append(f"options={el['options'][:30]}")
        if el.get("href"):
            bits.append(f"href={el['href'][:120]}")
        if is_final_submit(el):
            bits.append("FINAL_SUBMIT")
        if is_account_control(el):
            bits.append("ACCOUNT_CREATION")
        return " ".join(b for b in bits if b)

    def navigate(self, url: str) -> str:
        if not host_allowed(url, self.nav_hosts):
            return f"BLOCKED: {url} is outside this application's sites. Stay on the employer's application."
        self.session.goto(url)
        return f"Opened {self.page.url}. Take a snapshot."

    def click(self, ref: str) -> str:
        loc, info = self._locator(ref)
        el = info.data
        if is_account_control(el) and self.dry_run:
            return "DRY RUN: account creation is blocked. Call finish(status='dry_run_ready') with what you filled."
        typ = el.get("type")
        if typ in ("checkbox", "radio") or el.get("role") in ("checkbox", "radio"):
            question = info.question
            option = info.label
            if typ == "checkbox" and not info.data.get("group"):
                # A single box ("I certify ...") answers its own label with Yes.
                err, key = self._attestation_check(option, "Yes", None)
                answer_value = "Yes" if not el.get("checked") else "No"
            else:
                err, key = self._attestation_check(question, option, None)
                answer_value = option
            if err:
                return err
            loc.click(timeout=10_000)
            self._record(question, answer_value, "answer_bank" if key else "profile", key=key,
                         attestation=bool(key and key in answers_mod.ATTESTATION_KEYS) or key.startswith("custom:"),
                         ref=ref)
            return f"Clicked {option!r}."
        if is_final_submit(el):
            if self.dry_run:
                self.shot("filled", full_page=True)
                self.shot("review")
                return ("DRY RUN: final submit is blocked (nothing was sent). "
                        "Call finish(status='dry_run_ready').")
            open_needs = self.open_answer_needs()
            if open_needs:
                return ("REFUSED: unanswered attestation(s): " + "; ".join(n.question for n in open_needs)
                        + ". Call finish(status='needs_answer').")
            if "filled" not in self.state.screenshots:
                self.shot("filled", full_page=True)
            self.shot("review")
            self.state.url_before_submit = self.page.url
            self.state.submit_selector = f'[data-jw-ref="{ref}"]'
            loc.click(timeout=15_000)
            self.state.submitted = True
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=15_000)
            except Exception:  # noqa: BLE001
                pass
            return "Submit clicked. Take a snapshot to see the result (confirmation, errors, or a code request)."
        loc.click(timeout=10_000)
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:  # noqa: BLE001
            pass
        return f"Clicked {info.label!r}."

    def fill(self, ref: str, value: str, source: str = "resume_ai", category: str | None = None) -> str:
        loc, info = self._locator(ref)
        el = info.data
        if el.get("type") == "password":
            return "REFUSED: use fill_secret for password fields."
        if el.get("type") == "file":
            return "REFUSED: use upload_file for file inputs."
        if source not in AGENT_SOURCES:
            return f"REFUSED: source must be one of {AGENT_SOURCES}."
        question = info.question
        err, key = self._attestation_check(question, value, category)
        if err:
            return err
        attestation = bool(key)
        if not attestation:
            bank_key, bank_value = self.answers.lookup(question, company=self.job.get("company") or "")
            if source == "answer_bank" and bank_value is None:
                return f"REFUSED: there is no saved answer for {question!r}; say where the value comes from."
            if bank_value is not None and source == "answer_bank":
                key = bank_key or ""
        loc.fill(str(value), timeout=10_000)
        self._record(question, str(value), "answer_bank" if attestation else source, key=key or None,
                     attestation=attestation, ref=ref)
        return f"Filled {question!r}."

    def select(self, ref: str, option: str, source: str = "answer_bank", category: str | None = None) -> str:
        loc, info = self._locator(ref)
        options = info.data.get("options") or []
        question = info.question
        err, key = self._attestation_check(question, option, category)
        if err:
            return err
        chosen = answers_mod.match_option(option, options) if options else option
        if options and chosen is None:
            return f"No option matches {option!r}. Options: {options[:30]}"
        if source not in AGENT_SOURCES:
            source = "answer_bank"
        try:
            loc.select_option(label=chosen, timeout=10_000)
        except Exception as exc:  # noqa: BLE001
            return f"Could not select {chosen!r}: {str(exc)[:120]}"
        self._record(question, chosen, "answer_bank" if key else source, key=key or None,
                     attestation=bool(key), ref=ref)
        return f"Selected {chosen!r} for {question!r}."

    def upload_file(self, ref: str, which: str) -> str:
        loc, info = self._locator(ref)
        path = self.materials.resume_path if which == "resume" else (
            self.materials.cover_letter_path if which == "cover_letter" else None)
        if path is None or not Path(path).is_file():
            return f"No {which} file is available."
        loc.set_input_files(str(path), timeout=15_000)
        self._record(info.question or which, f"[file] {Path(path).name}", "materials", ref=ref)
        return f"Uploaded {which} ({Path(path).name})."

    def fill_secret(self, ref: str, name: str) -> str:
        loc, info = self._locator(ref)
        if name == "account_password":
            if self.dry_run:
                return ("DRY RUN: signing in or creating an account is blocked. "
                        "Call finish(status='dry_run_ready').")
            url = self.page.url
            value = account_password(self.secret_store, url, create=True)
        elif name == "email_code":
            value = self.session_secrets.get("email_code")
            if not value:
                return "No code yet. Call ask_human(kind='email_code') first."
        else:
            return "Unknown secret. Use account_password or email_code."
        self.transcript.forbid(value)
        loc.fill(value, timeout=10_000)
        self._record(info.question or name, "[secret]", "secret", ref=ref)
        return f"Filled {info.question or name!r} with the saved {name.replace('_', ' ')} (hidden)."

    def screenshot(self, name: str = "") -> str:
        self._shot_n += 1
        safe = re.sub(r"[^a-z0-9_-]+", "-", (name or "").lower())[:30].strip("-")
        saved = self.shot(f"step-{self._shot_n:02d}{'-' + safe if safe else ''}")
        return "Saved screenshot." if saved else "Screenshot failed."

    def ask_human(self, kind: str, prompt: str) -> str:
        if kind == "answer":
            self._need("answer", prompt, key=answers_mod.key_for_question(prompt),
                       category=answers_mod.classify_question(prompt))
            return "Recorded the question for the person. Call finish(status='needs_answer')."
        if kind not in ("captcha", "email_code"):
            return "kind must be captcha, email_code or answer."
        if self._ask_human is None:
            return "Nobody can be asked right now. Call finish(status='captcha_timeout')."
        self._need(kind, prompt)
        value = self._ask_human(kind, prompt)
        if value is None:
            return ("No reply in time. Call finish(status='captcha_timeout')." if kind == "captcha"
                    else "No code arrived in time. Call finish(status='failed') with reason 'no email code'.")
        self.state.needs = [n for n in self.state.needs if not (n.kind == kind and n.detail == prompt)]
        if kind == "email_code":
            self.session_secrets.put("email_code", value)
            self.transcript.forbid(value)
            return "Code received. Fill it with fill_secret(ref, name='email_code'), then continue."
        return "The person says the CAPTCHA is done. Take a snapshot and continue."

    def finish(self, status: str, summary: str = "", questions: list[str] | None = None) -> str:
        if status not in FINISH_STATUSES:
            return f"status must be one of {FINISH_STATUSES}"
        for q in questions or []:
            self._need("answer", q, key=answers_mod.key_for_question(q), category=answers_mod.classify_question(q))
        self.state.finished = {"status": status, "summary": (summary or "")[:1000]}
        return "Done."

    # ------------------------------------------------------------- dispatch
    def call(self, name: str, args: dict[str, Any]) -> str:
        self.state.steps += 1
        fn = {
            "snapshot": self.snapshot, "navigate": self.navigate, "click": self.click, "fill": self.fill,
            "select": self.select, "upload_file": self.upload_file, "fill_secret": self.fill_secret,
            "screenshot": self.screenshot, "ask_human": self.ask_human, "finish": self.finish,
        }.get(name)
        if fn is None:
            return f"Unknown tool {name}"
        try:
            # Belt and braces: no secret value can reach the model, even if a
            # page echoes it back into a field or its text.
            return self.transcript.scrub(fn(**args))
        except TypeError as exc:
            return f"Bad arguments for {name}: {exc}"
        except KeyError as exc:
            return str(exc).strip("'\"")
        except PermissionError as exc:
            return f"BLOCKED: {exc}"
        except Exception as exc:  # noqa: BLE001 - surface page errors to the model
            return f"{name} failed: {str(exc).splitlines()[0][:200]}"


def tool_definitions() -> list[dict]:
    """Anthropic tool schemas (strict) for ApplyTools."""

    def obj(props: dict, required: list[str]) -> dict:
        return {"type": "object", "properties": props, "required": required, "additionalProperties": False}

    ref = {"type": "string", "description": "Element ref from the latest snapshot, e.g. e12"}
    category = {"type": ["string", "null"], "enum": [*answers_mod.ATTESTATION_CATEGORIES, None],
                "description": "Your own classification if this question is an attestation, else null."}
    tools = [
        ("snapshot", "Read the current page: URL, text and every interactive element with a ref.", obj({}, [])),
        ("navigate", "Open a URL on this employer's application site.", obj({"url": {"type": "string"}}, ["url"])),
        ("click", "Click a button, link, checkbox or radio option.", obj({"ref": ref}, ["ref"])),
        ("fill", "Type into a text field. Say where the value comes from.",
         obj({"ref": ref, "value": {"type": "string"},
              "source": {"type": "string", "enum": list(AGENT_SOURCES)}, "category": category},
             ["ref", "value", "source", "category"])),
        ("select", "Choose an option in a dropdown.",
         obj({"ref": ref, "option": {"type": "string"},
              "source": {"type": "string", "enum": list(AGENT_SOURCES)}, "category": category},
             ["ref", "option", "source", "category"])),
        ("upload_file", "Attach the tailored resume or cover letter to a file input.",
         obj({"ref": ref, "which": {"type": "string", "enum": ["resume", "cover_letter"]}}, ["ref", "which"])),
        ("fill_secret", "Type a hidden value (employer account password, or the email code the person sent).",
         obj({"ref": ref, "name": {"type": "string", "enum": ["account_password", "email_code"]}}, ["ref", "name"])),
        ("screenshot", "Save a screenshot for the evidence record.", obj({"name": {"type": "string"}}, ["name"])),
        ("ask_human", "Ask the person: captcha (wait for them to solve it), email_code (they paste a code "
                      "the employer emailed them), or answer (a question only they can answer; you then finish).",
         obj({"kind": {"type": "string", "enum": ["captcha", "email_code", "answer"]},
              "prompt": {"type": "string"}}, ["kind", "prompt"])),
        ("finish", "End the session with an honest status.",
         obj({"status": {"type": "string", "enum": list(FINISH_STATUSES)}, "summary": {"type": "string"},
              "questions": {"type": "array", "items": {"type": "string"}}},
             ["status", "summary", "questions"])),
    ]
    return [{"name": n, "description": d, "input_schema": s, "strict": True} for n, d, s in tools]


def summarize_args(name: str, args: dict) -> str:
    return json.dumps({"tool": name, **args}, ensure_ascii=False)[:500]
