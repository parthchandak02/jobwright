"""Decide from the page itself whether an application was received.

The agent's own claim ("I submitted it") is never enough. After the final
submit the runner reads the page and calls ``verify_confirmation``:

- ``high``: a known ATS confirmation URL, or a success element (e.g.
  ``[data-testid=application-confirmation]``, ``.application-confirmation``)
  together with confirmation text.
- ``medium``: clear confirmation text on a page that no longer shows the
  form's submit button.
- ``low``: confirmation-like text but the form still looks present, or the
  URL changed without text: not enough; reported as ``unverified``.
- ``none``: error text or nothing.

Only ``high`` and ``medium`` mark a job Applied.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

CONFIRM_TEXT = re.compile(
    r"thank(s| you) for (applying|your application|your interest|submitting)|"
    r"application (has been |was )?(received|submitted|sent|complete)|"
    r"we('ve| have) received your application|successfully (submitted|applied)|"
    r"your application (is|has been) (on its way|in)|you('ve| have) (successfully )?applied",
    re.I,
)
ERROR_TEXT = re.compile(
    r"(there (was|were) (an )?errors?|please (correct|fix|complete) the|is required|required field|"
    r"could not (be )?submit|submission failed|something went wrong|try again)",
    re.I,
)
CONFIRM_URL = re.compile(
    r"(/confirmation\b|/thank[-_]?you|/thanks\b|/application[-_]?submitted|/applied\b|"
    r"[?&](submitted|success)=(true|1)|greenhouse\.io/.*/confirmation|jobs\.lever\.co/.*/thanks|"
    r"ashbyhq\.com/.*/(application/)?success)",
    re.I,
)
SUCCESS_SELECTORS = (
    "[data-testid*='confirmation' i]",
    "[data-qa*='confirmation' i]",
    "[class*='application-confirmation' i]",
    "[id*='application-confirmation' i]",
    "[class*='thank-you' i]",
    "[id*='thank-you' i]",
    "[role='status'][class*='success' i]",
)


@dataclass
class Verification:
    verified: bool
    confidence: str  # high | medium | low | none
    evidence: str


def verify_confirmation(
    *,
    url: str,
    text: str,
    success_element: bool = False,
    form_still_present: bool = False,
    url_before: str = "",
) -> Verification:
    text = " ".join((text or "").split())
    text_hit = CONFIRM_TEXT.search(text)
    error_hit = ERROR_TEXT.search(text)
    url_hit = CONFIRM_URL.search(url or "")
    if url_hit and (text_hit or success_element):
        return Verification(True, "high", f"confirmation URL {url} and text/element")
    if success_element and text_hit:
        return Verification(True, "high", f"success element + text: {text_hit.group(0)!r}")
    if url_hit and not error_hit:
        return Verification(True, "high", f"confirmation URL {url}")
    if text_hit and not form_still_present and not error_hit:
        return Verification(True, "medium", f"confirmation text: {text_hit.group(0)!r}")
    if text_hit:
        return Verification(False, "low", f"confirmation-like text but the form is still shown: "
                                          f"{text_hit.group(0)!r}")
    if error_hit:
        return Verification(False, "none", f"error text: {error_hit.group(0)!r}")
    if url_before and url and url != url_before:
        return Verification(False, "low", f"page changed to {url} without confirmation text")
    return Verification(False, "none", "no confirmation found")


def verify_page(page, *, url_before: str = "", submit_selector: str | None = None) -> Verification:
    """Read a live Playwright page and verify it."""
    try:
        page.wait_for_load_state("domcontentloaded", timeout=10_000)
    except Exception:  # noqa: BLE001
        pass
    try:
        text = page.inner_text("body", timeout=5_000)
    except Exception:  # noqa: BLE001
        text = ""
    success = False
    for sel in SUCCESS_SELECTORS:
        try:
            if page.locator(sel).count() > 0:
                success = True
                break
        except Exception:  # noqa: BLE001
            continue
    form_present = False
    try:
        sel = submit_selector or "button[type=submit], input[type=submit]"
        form_present = page.locator(sel).count() > 0 and page.locator("form").count() > 0
    except Exception:  # noqa: BLE001
        pass
    return verify_confirmation(url=page.url, text=text, success_element=success,
                               form_still_present=form_present, url_before=url_before)
