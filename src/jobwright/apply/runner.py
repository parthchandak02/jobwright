"""Run one application end to end, safely, and record the evidence.

``apply_job(job, dry_run=...)``:

1. Safety gates (``apply/safety.py``): kill switch, apply_enabled (live),
   paused, daily cap, score, dedupe, employer cap, LinkedIn.
2. Opens the person's own browser profile with the job's domain allowlist.
3. Tries a registered deterministic ``FormFiller`` for the ATS family
   (``apply/fill.py``); falls back to the Claude agent (``apply/agent.py``).
4. CAPTCHA / email code: pauses, asks the person (``apply/hitl.py``), keeps the
   browser open up to the wait limit.
5. Missing attestation: stops, records ``needs_answer``, posts the question.
6. Live submit → reads the confirmation page (``apply/verify.py``). Applied
   only when verified (high/medium); else ``unverified``.
7. Writes the ``submissions`` row + run folder; auto-pauses the profile after
   consecutive failures.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from jobwright import config
from jobwright.apply import evidence, hitl, safety
from jobwright.apply.answers import load_answers
from jobwright.apply.browser import ATS_HOSTS, BrowserSession, allowed_hosts_for, registrable_domain
from jobwright.apply.fill import FieldRecord, FillResult, Need
from jobwright.apply.materials import Materials
from jobwright.apply.secret_store import SecretStore, default_store
from jobwright.apply.tools import ApplyTools
from jobwright.apply.verify import Verification, verify_page
from jobwright.database import get_connection

log = logging.getLogger(__name__)

TERMINAL_OUTCOMES = ("applied", "unverified", "dry_run", "needs_answer", "captcha_timeout", "expired",
                     "blocked", "failed", "error", "skipped")


@dataclass
class ApplyOutcome:
    outcome: str
    job_url: str
    title: str = ""
    company: str = ""
    submission_id: int | None = None
    run_id: str | None = None
    reasons: list[str] = field(default_factory=list)
    verification_confidence: str | None = None
    questions: list[str] = field(default_factory=list)
    cost_usd: float = 0.0
    screenshots: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def detect_family(url: str) -> str | None:
    try:
        from jobwright.apply.ats import detect_ats

        return detect_ats(url)
    except Exception:  # noqa: BLE001
        return None


def _resolve(path: str | None) -> Path | None:
    if not path:
        return None
    try:
        from jobwright.scoring.materials_format import resolve_material_path

        resolved = resolve_material_path(path)
    except Exception:  # noqa: BLE001
        resolved = Path(path)
    return Path(resolved) if resolved and Path(resolved).is_file() else None


def materials_for(job: dict) -> Materials:
    resume_file = _resolve(job.get("tailored_resume_docx_path")) or _resolve(job.get("tailored_resume_path"))
    if resume_file and resume_file.suffix.lower() in (".md", ".txt"):
        resume_file = None
    if resume_file is None and Path(config.RESUME_PDF_PATH).is_file():
        resume_file = Path(config.RESUME_PDF_PATH)
    cover_file = _resolve(job.get("cover_letter_docx_path"))
    resume_text = ""
    src = _resolve(job.get("tailored_resume_path"))
    if src and src.suffix.lower() in (".md", ".txt"):
        resume_text = src.read_text(encoding="utf-8")
    if not resume_text:
        try:
            from jobwright.resume import load_resume_text

            resume_text = load_resume_text()
        except Exception:  # noqa: BLE001
            resume_text = ""
    cover_text = ""
    csrc = _resolve(job.get("cover_letter_path"))
    if csrc and csrc.suffix.lower() in (".md", ".txt"):
        cover_text = csrc.read_text(encoding="utf-8")
    return Materials(resume_path=resume_file, cover_letter_path=cover_file, resume_text=resume_text,
                     cover_letter_text=cover_text)


def _set_job_status(url: str, outcome: str, *, error: str | None, confidence: str | None,
                    duration_ms: int, run_id: str) -> None:
    from jobwright.database import advance_funnel

    conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    if outcome == "applied":
        conn.execute(
            "UPDATE jobs SET apply_status = 'applied', applied_at = ?, apply_error = NULL, agent_id = NULL, "
            "apply_duration_ms = ?, apply_task_id = ?, verification_confidence = ? WHERE url = ?",
            (now, duration_ms, run_id, confidence, url),
        )
        advance_funnel(url, "applied", "system", note=f"auto apply (verified {confidence})", conn=conn)
    elif outcome == "dry_run":
        conn.execute("UPDATE jobs SET apply_status = NULL, agent_id = NULL WHERE url = ?", (url,))
    elif outcome in ("unverified", "needs_answer", "captcha_timeout"):
        conn.execute(
            "UPDATE jobs SET apply_status = ?, apply_error = ?, agent_id = NULL, apply_duration_ms = ?, "
            "apply_task_id = ?, verification_confidence = ? WHERE url = ?",
            (outcome, (error or outcome)[:300], duration_ms, run_id, confidence, url),
        )
    else:
        permanent = outcome in ("expired", "blocked")
        attempts = "99" if permanent else "COALESCE(apply_attempts, 0) + 1"
        conn.execute(
            f"UPDATE jobs SET apply_status = 'failed', apply_error = ?, apply_attempts = {attempts}, "
            "agent_id = NULL, apply_duration_ms = ?, apply_task_id = ? WHERE url = ?",
            (f"{outcome}: {error or ''}"[:300], duration_ms, run_id, url),
        )
    conn.commit()


def _claim(url: str, run_id: str) -> bool:
    conn = get_connection()
    cur = conn.execute(
        "UPDATE jobs SET apply_status = 'in_progress', agent_id = ?, last_attempted_at = ? "
        "WHERE url = ? AND (apply_status IS NULL OR apply_status NOT IN ('in_progress', 'applied'))",
        (f"run-{run_id}", datetime.now(timezone.utc).isoformat(), url),
    )
    conn.commit()
    return cur.rowcount == 1


class _Human:
    """ask_human implementation: pending input + WhatsApp + wait with live screenshot."""

    def __init__(self, job: dict, run_id: str, session: BrowserSession, user_id: str | None,
                 wait_s: float | None, poll_s: float) -> None:
        self.job, self.run_id, self.session, self.user_id = job, run_id, session, user_id
        self.wait_s, self.poll_s = wait_s, poll_s
        self.asked: list[dict] = []

    def __call__(self, kind: str, prompt: str) -> str | None:
        company = self.job.get("company") or self.job.get("site") or "the employer"
        if kind == "email_code" and company.lower() not in prompt.lower():
            prompt = f"Please paste the code from {company}. {prompt}".strip()
        row = hitl.create_pending(kind, prompt, job=self.job, run_id=self.run_id)
        self.asked.append(row)
        shot_path = hitl.live_screenshot_path(row["id"])

        def tick() -> None:
            if kind == "captcha":
                self.session.screenshot(shot_path)

        tick()
        hitl.notify(row, self.user_id, title=self.job.get("title") or "")
        return hitl.wait_for(row["id"], timeout_s=self.wait_s, poll_s=self.poll_s, on_tick=tick)


# Filler needs whose detail starts with these are the filler's own trouble
# (could not read / fill the form), not a question for the person: the agent
# takes over instead.
_FILLER_TROUBLE = ("form", "field", "cv/cover")


def _need_head(need: Need) -> str:
    head, sep, _rest = need.detail.partition(": ")
    return head.strip() if sep else ""


def get_filler(apply_url: str, open_answer: Callable[[str, dict], str] | None = None):
    """The deterministic filler for this URL's ATS (apply/ats/fillers.py), or None."""
    if os.environ.get("JOBWRIGHT_APPLY_FILLERS", "on").strip().lower() in ("0", "off", "false", "no"):
        return None
    try:
        from jobwright.apply.ats.fillers import filler_for
    except ImportError:
        return None
    return filler_for(apply_url, open_answer)


def _run_filler(filler, session: BrowserSession, job: dict, answers, materials: Materials,
                profile: dict) -> FillResult:
    res = filler.fill(session.page, job, answers.as_filler_dict(), materials.as_filler_dict(profile, answers))
    # Re-check the filler's work with our own classifier: an attestation must
    # come from the answer bank, whatever the filler's own rules said.
    from jobwright.apply.answers import is_attestation, key_for_question

    for f in res.fields:
        if f.source != "answer_bank" and f.source != "file" and is_attestation(f.label):
            res.needs.append(Need(kind="answer", detail=f"question: {f.label}", key=key_for_question(f.label)))
            res.ready_to_submit = False
        if f.source == "answer_bank":
            f.attestation = is_attestation(f.label)
            f.key = f.key or key_for_question(f.label)
    return res


def make_open_answer(agent: Any, resume_text: str, cover_text: str = "") -> Callable[[str, dict], str]:
    """Open questions for the fillers, written by the model from the resume.

    Refuses attestations outright (empty answer = the filler records a Need).
    """
    from jobwright.apply.answers import is_attestation

    def answer(question: str, job: dict) -> str:
        if is_attestation(question) or agent is None or not hasattr(agent, "answer_open_question"):
            return ""
        try:
            return agent.answer_open_question(question, job, resume_text, cover_text)
        except Exception as exc:  # noqa: BLE001
            log.warning("open question failed: %s", exc)
            return ""

    return answer


def apply_job(
    job: dict,
    *,
    dry_run: bool = True,
    user_id: str | None = None,
    agent: Any = None,
    secret_store: SecretStore | None = None,
    headless: bool | None = None,
    min_score: int | None = None,
    wait_s: float | None = None,
    poll_s: float = 2.0,
    session_factory: Callable[..., BrowserSession] | None = None,
) -> ApplyOutcome:
    user_id = user_id if user_id is not None else config.get_active_user_id()
    live = not dry_run
    url = job["url"]
    base = ApplyOutcome("skipped", url, title=job.get("title") or "", company=job.get("company") or "")

    gate = safety.check_profile(user_id, live=live)
    job_gate = safety.check_job(job, user_id, live=live, min_score=min_score)
    reasons = gate.reasons + job_gate.reasons
    if reasons:
        base.reasons = reasons
        return base

    apply_url = job.get("application_url") or url
    family = detect_family(apply_url)
    run_id = evidence.new_run_id()
    if not _claim(url, run_id):
        base.reasons = ["another run is applying to this job"]
        return base
    rdir = evidence.run_dir(run_id)
    transcript = evidence.Transcript(rdir / "transcript.jsonl")
    answers = load_answers()
    materials = materials_for(job)
    try:
        profile = config.load_profile()
    except FileNotFoundError:
        profile = {}
    if agent is None:
        from jobwright.apply.agent import AnthropicApplyAgent

        agent = AnthropicApplyAgent()
    filler = get_filler(apply_url, make_open_answer(agent, materials.resume_text, materials.cover_letter_text))
    provider = f"filler:{family}" if filler is not None else getattr(agent, "provider_name", "agent")
    model = getattr(agent, "model", None)
    sub_id = evidence.start_submission(job, run_id, ats=family, provider=provider, model=model, dry_run=dry_run)
    out = ApplyOutcome("failed", url, title=base.title, company=base.company, submission_id=sub_id, run_id=run_id)

    store = secret_store or default_store()
    apply_host = (urlparse(apply_url).hostname or "").lower()
    allowed = allowed_hosts_for(apply_url, family)
    # navigate() may only go to the employer's own / ATS hosts (not CDNs).
    nav_hosts = {apply_host, registrable_domain(apply_host), *ATS_HOSTS.get(family or "", ())} - {""}
    if headless is None:
        headless = os.environ.get("JOBWRIGHT_APPLY_HEADLESS", "1" if dry_run else "0") not in ("0", "false", "no")
    factory = session_factory or BrowserSession
    session = factory(allowed_hosts=allowed, dry_run=dry_run, headless=headless)
    fields: list[FieldRecord] = []
    needs: list[Need] = []
    screenshots: dict[str, str] = {}
    error: str | None = None
    confidence = evidence_text = None
    steps = tin = tout = 0
    cost = 0.0
    started = time.monotonic()
    human = None
    try:
        session.start()
        session.goto(apply_url)
        human = _Human(job, run_id, session, user_id, wait_s, poll_s)
        tools = ApplyTools(session, job=job, answers=answers, materials=materials, secret_store=store,
                           dry_run=dry_run, run_dir=rdir, transcript=transcript, nav_hosts=nav_hosts,
                           ask_human=human)
        status = None
        if filler is not None:
            transcript.write("filler", {"family": family})
            try:
                res = _run_filler(filler, session, job, answers, materials, profile)
            except Exception as exc:  # noqa: BLE001 - the agent takes over
                log.warning("filler %s failed: %s", family, exc)
                transcript.write("filler_error", str(exc)[:300])
                res = None
            if res is not None:
                fields.extend(res.fields)
                transcript.write("filler_result", {"fields": len(res.fields),
                                                   "needs": [n.detail for n in res.needs],
                                                   "ready": res.ready_to_submit})
                status = _finish_filler(res, filler, session, tools, human, dry_run)
                if status is not None:
                    needs.extend(n for n in res.needs if n.kind == "answer"
                                 and _need_head(n) not in _FILLER_TROUBLE)
        if status is None:
            from jobwright.apply.prompt import build_agent_system_prompt

            system = build_agent_system_prompt(
                job=job, profile=profile, answers=answers, resume_text=materials.resume_text,
                cover_letter_text=materials.cover_letter_text, dry_run=dry_run,
                has_resume_file=materials.resume_path is not None,
                has_cover_file=materials.cover_letter_path is not None)
            result = agent.run(tools, system, transcript)
            steps, tin, tout, cost = result.steps, result.input_tokens, result.output_tokens, result.cost_usd
            status = result.status
            error = result.error or (result.summary if status not in ("submitted", "dry_run_ready") else None)
            fields.extend(tools.state.fields)
            needs.extend(tools.state.needs)
        screenshots.update(tools.state.screenshots)

        # ---- decide the outcome from what actually happened ----------------
        answer_needs = [n for n in needs if n.kind == "answer"]
        if tools.state.submitted and not dry_run:
            v = verify_page(session.page, url_before=tools.state.url_before_submit,
                            submit_selector=tools.state.submit_selector)
            if not v.verified and filler is not None and getattr(tools.state, "filler_submitted", False):
                ok, conf, ev = filler.verify(session.page)
                if ok and conf in ("high", "medium"):
                    v = Verification(True, conf, ev)
            shot = session.screenshot(rdir / "confirmation.png", full_page=True)
            if shot:
                screenshots["confirmation"] = shot
            confidence, evidence_text = v.confidence, v.evidence
            outcome = "applied" if v.verified else "unverified"
        elif answer_needs or status == "needs_answer":
            outcome = "needs_answer"
        elif dry_run and status in ("dry_run_ready", "submitted"):
            outcome = "dry_run"
            for name, full in (("filled", True), ("review", False)):
                if name not in screenshots:
                    shot = session.screenshot(rdir / f"{name}.png", full_page=full)
                    if shot:
                        screenshots[name] = shot
        elif status == "submitted":
            outcome, error = "failed", "the agent said it submitted, but no final submit was clicked"
        elif status in ("captcha_timeout", "expired", "blocked"):
            outcome = status
        else:
            outcome = "failed"
            error = error or status
        if session.blocked:
            transcript.write("blocked_requests", session.blocked[:100])
    except Exception as exc:  # noqa: BLE001
        log.exception("apply run %s crashed", run_id)
        outcome, error = "error", str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__
        needs = needs or []
    finally:
        session.close()
        try:
            from jobwright.llm import flush_active_usage

            flush_active_usage(run_id)
        except Exception:  # noqa: BLE001
            pass

    duration_ms = int((time.monotonic() - started) * 1000)
    questions = [n.question for n in needs if n.kind == "answer"]
    if outcome == "needs_answer":
        error = "needs answer: " + "; ".join(questions)[:250]
        for q, n in zip(questions, [n for n in needs if n.kind == "answer"]):
            row = hitl.create_pending("answer", q, job=job, run_id=run_id, question_key=n.key)
            if not row.get("notified_at"):
                hitl.notify(row, user_id, title=job.get("title") or "")
    evidence.finish_submission(
        sub_id, outcome=outcome, fields=fields, needs=needs, screenshots=screenshots,
        transcript_path=str(transcript.path), verification_confidence=confidence,
        verification_evidence=evidence_text, steps=steps, input_tokens=tin, output_tokens=tout,
        cost_usd=round(cost, 6), error=error)
    _set_job_status(url, outcome, error=error, confidence=confidence, duration_ms=duration_ms, run_id=run_id)
    if live and outcome in safety.FAILURE_OUTCOMES:
        safety.maybe_auto_pause(user_id)
    out.outcome = outcome
    out.verification_confidence = confidence
    out.questions = questions
    out.cost_usd = round(cost, 6)
    out.screenshots = screenshots
    if error and outcome not in ("applied", "dry_run"):
        out.reasons = [error]
    return out


def _finish_filler(res: FillResult, filler, session: BrowserSession, tools: ApplyTools, human: _Human,
                   dry_run: bool) -> str | None:
    """Act on a deterministic filler's result. None = hand over to the agent."""
    for need in [n for n in res.needs if n.kind == "captcha"]:
        if human("captcha", need.detail) is None:
            return "captcha_timeout"
    if any(n.kind == "account" for n in res.needs):
        return "dry_run_ready" if dry_run else None  # dry runs stop before accounts
    if any(n.kind == "email_code" for n in res.needs):
        return None  # the agent can ask for the code and type it with fill_secret
    questions = [n for n in res.needs if n.kind == "answer" and _need_head(n) not in _FILLER_TROUBLE]
    if questions:
        return "needs_answer"
    if any(n.kind == "answer" for n in res.needs):
        return None  # the filler could not read / fill something: the agent tries
    if not res.ready_to_submit:
        return None
    tools.shot("filled", full_page=True)
    tools.shot("review")
    if dry_run:
        return "dry_run_ready"
    tools.state.url_before_submit = session.page.url
    if not filler.submit(session.page):
        return None
    tools.state.submitted = True
    tools.state.filler_submitted = True
    try:
        session.page.wait_for_load_state("domcontentloaded", timeout=15_000)
    except Exception:  # noqa: BLE001
        pass
    return "submitted"
