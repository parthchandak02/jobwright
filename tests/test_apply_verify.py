"""The page, not the agent's claim, decides whether an application was received.

``verify_confirmation`` is what marks a job Applied (high or medium only).
The server runner reads a live page through ``verify_page``; the Claude
connector reports a URL and text into the same function. These tests pin
that decision table.
"""

from __future__ import annotations

import pytest

from jobwright.apply.verify import SUCCESS_SELECTORS, Verification, verify_confirmation, verify_page

# url, text, success element, form still present, url before, verified, confidence, evidence fragment
_DECISIONS = [
    # high: a known confirmation URL together with confirmation text
    (
        "https://boards.greenhouse.io/example/jobs/1001/confirmation",
        "Thank you for applying",
        False, False, "",
        True, "high", "confirmation URL",
    ),
    # high even if a submit button is still in the DOM: the URL is the signal
    (
        "https://boards.greenhouse.io/example/jobs/1001/confirmation",
        "Thank you for applying",
        False, True, "",
        True, "high", "confirmation URL",
    ),
    # high: success element plus confirmation text
    (
        "https://jobs.example.com/apply",
        "Your application has been received",
        True, False, "",
        True, "high", "success element",
    ),
    # high wins over a form that is still on the page
    (
        "https://jobs.example.com/apply",
        "Application was submitted",
        True, True, "",
        True, "high", "success element",
    ),
    # high: confirmation URL alone, no error text
    ("https://jobs.lever.co/example/thanks", "", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.ashbyhq.com/example/application/success", " ", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.ashbyhq.com/example/123/success", "", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.example.com/done?submitted=true", "", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.example.com/done?x=1&success=1", "", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.example.com/application-submitted", "", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.example.com/application_submitted", "", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.example.com/thank-you", "", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.example.com/thank_you", "", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.example.com/thanks", "", False, False, "", True, "high", "confirmation URL"),
    ("https://jobs.example.com/applied", "", False, False, "", True, "high", "confirmation URL"),
    # medium: clear confirmation text, form gone, no error
    (
        "https://jobs.example.com/apply",
        "We've received your application.",
        False, False, "",
        True, "medium", "confirmation text",
    ),
    (
        "https://jobs.example.com/apply",
        "THANK   YOU\nFOR   APPLYING",
        False, False, "",
        True, "medium", "THANK YOU FOR APPLYING",
    ),
    # low: the same kind of sentence while the form is still on screen
    (
        "https://jobs.example.com/apply",
        "Thank you for your interest",
        False, True, "",
        False, "low", "form is still shown",
    ),
    # low: confirmation wording plus an error, and no confirmation URL
    (
        "https://jobs.example.com/apply",
        "Thank you for applying. Email is required.",
        False, False, "",
        False, "low", "form is still shown",
    ),
    # none: error text, including on a URL that would otherwise look done
    (
        "https://jobs.example.com/apply",
        "Please correct the required fields",
        False, False, "",
        False, "none", "error text",
    ),
    (
        "https://jobs.example.com/apply",
        "Something went wrong. Try again.",
        False, False, "",
        False, "none", "error text",
    ),
    (
        "https://jobs.example.com/confirmation",
        "There was an error. Please try again.",
        False, False, "",
        False, "none", "error text",
    ),
    # low: the page moved and never said the application was received
    (
        "https://jobs.example.com/step-2",
        "Review your answers",
        False, False, "https://jobs.example.com/apply",
        False, "low", "without confirmation text",
    ),
    # none: an ordinary job page, a success flag with no sentence, a false query flag
    (
        "https://jobs.example.com/jobs/123",
        "Software Engineer. Apply now.",
        False, False, "",
        False, "none", "no confirmation found",
    ),
    (
        "https://boards.greenhouse.io/example/jobs/1001",
        "Apply",
        False, False, "",
        False, "none", "no confirmation found",
    ),
    (
        "https://jobs.example.com/apply",
        "Next step",
        True, False, "",
        False, "none", "no confirmation found",
    ),
    (
        "https://jobs.example.com/done?submitted=false",
        "",
        False, False, "",
        False, "none", "no confirmation found",
    ),
    (
        "https://jobs.example.com/done?success=0",
        "",
        False, False, "",
        False, "none", "no confirmation found",
    ),
    # staying on the same URL is not a navigation
    (
        "https://jobs.example.com/apply",
        "Still here",
        False, False, "https://jobs.example.com/apply",
        False, "none", "no confirmation found",
    ),
]

_CONFIRM_PHRASES = [
    "Thanks for applying",
    "Thank you for your application",
    "Thank you for your interest",
    "Thank you for submitting your materials",
    "Your application has been received",
    "Your application was submitted",
    "Application sent",
    "Application complete",
    "We have received your application",
    "Successfully submitted",
    "Successfully applied",
    "Your application is on its way",
    "Your application is in our system",
    "You've applied",
    "You have successfully applied",
]

_ERROR_PHRASES = [
    "There was an error on the form",
    "There were errors in your submission",
    "Please fix the highlighted questions",
    "Please complete the application",
    "Phone is required",
    "Required field missing",
    "Could not submit your application",
    "Could not be submitted",
    "Submission failed",
    "Something went wrong",
    "Please try again",
]


@pytest.mark.parametrize(
    ("url", "text", "success", "form", "before", "verified", "confidence", "evidence"),
    _DECISIONS,
    ids=[f"{'yes' if row[5] else 'no'}-{row[6]}-{i}" for i, row in enumerate(_DECISIONS)],
)
def test_confirmation_decision(url, text, success, form, before, verified, confidence, evidence):
    found = verify_confirmation(
        url=url, text=text, success_element=success, form_still_present=form, url_before=before,
    )
    assert found.verified is verified
    assert found.confidence == confidence
    assert evidence in found.evidence
    # Only high and medium are allowed to mark a job Applied.
    assert found.verified is (found.confidence in {"high", "medium"})


@pytest.mark.parametrize("phrase", _CONFIRM_PHRASES)
def test_confirmation_phrases_are_medium_when_the_form_is_gone(phrase):
    found = verify_confirmation(url="https://jobs.example.com/apply", text=phrase)
    assert found.verified is True
    assert found.confidence == "medium"
    assert found.evidence.startswith("confirmation text:")


@pytest.mark.parametrize("phrase", _ERROR_PHRASES)
def test_error_phrases_are_not_a_confirmation(phrase):
    found = verify_confirmation(url="https://jobs.example.com/apply", text=phrase)
    assert found.verified is False
    assert found.confidence == "none"
    assert found.evidence.startswith("error text:")


def test_blank_page_is_not_a_confirmation():
    assert verify_confirmation(url="", text="") == Verification(False, "none", "no confirmation found")
    assert verify_confirmation(url="", text=None) == Verification(False, "none", "no confirmation found")


def test_open_form_blocks_text_that_passes_once_the_form_is_gone():
    text = "Thank you for your interest in Example Co."
    url = "https://jobs.example.com/apply"
    still_open = verify_confirmation(url=url, text=text, form_still_present=True)
    gone = verify_confirmation(url=url, text=text, form_still_present=False)
    assert still_open.verified is False and still_open.confidence == "low"
    assert "form is still shown" in still_open.evidence
    assert gone.verified is True and gone.confidence == "medium"


class _Locator:
    def __init__(self, count: int = 0, exc: Exception | None = None):
        self._count = count
        self._exc = exc

    def count(self) -> int:
        if self._exc is not None:
            raise self._exc
        return self._count


class _Page:
    """The slice of a Playwright page that verify_page actually reads."""

    def __init__(self, url: str, text: str, *, counts: dict[str, int] | None = None,
                 errors: set[str] | None = None, fail: str | None = None):
        self.url = url
        self._text = text
        self._counts = counts or {}
        self._errors = errors or set()
        self._fail = fail

    def wait_for_load_state(self, _state: str, timeout: int = 0) -> None:
        if self._fail == "wait":
            raise TimeoutError("slow page")

    def inner_text(self, _selector: str, timeout: int = 0) -> str:
        if self._fail == "text":
            raise RuntimeError("body detached")
        return self._text

    def locator(self, selector: str) -> _Locator:
        if self._fail == "locator":
            raise RuntimeError("selector engine down")
        if selector in self._errors:
            return _Locator(exc=RuntimeError(selector))
        return _Locator(self._counts.get(selector, 0))


_SUBMIT = "button[type=submit], input[type=submit]"


def test_verify_page_reads_confirmation_text_when_the_form_is_gone():
    page = _Page("https://jobs.example.com/apply", "We've received your application.")
    found = verify_page(page)
    assert found.verified is True and found.confidence == "medium"


def test_verify_page_rejects_confirmation_text_while_the_form_is_still_there():
    page = _Page(
        "https://jobs.example.com/apply",
        "Thank you for applying",
        counts={"form": 1, _SUBMIT: 1},
    )
    found = verify_page(page)
    assert found.verified is False and found.confidence == "low"
    assert "form is still shown" in found.evidence


def test_verify_page_treats_a_success_element_plus_text_as_high():
    page = _Page(
        "https://jobs.example.com/apply",
        "Your application has been received",
        counts={SUCCESS_SELECTORS[0]: 1, "form": 1, _SUBMIT: 1},
    )
    found = verify_page(page)
    assert found.verified is True and found.confidence == "high"
    assert "success element" in found.evidence


def test_verify_page_skips_a_broken_success_selector_and_uses_the_next():
    page = _Page(
        "https://jobs.example.com/apply",
        "Your application has been received",
        counts={SUCCESS_SELECTORS[1]: 1},
        errors={SUCCESS_SELECTORS[0]},
    )
    found = verify_page(page)
    assert found.verified is True and found.confidence == "high"


def test_verify_page_trusts_a_confirmation_url_with_an_empty_body():
    page = _Page("https://jobs.lever.co/example/thanks", "")
    found = verify_page(page)
    assert found.verified is True and found.confidence == "high"
    assert "jobs.lever.co/example/thanks" in found.evidence


def test_verify_page_custom_submit_selector_is_what_counts_as_the_form():
    text = "Thank you for applying"
    url = "https://jobs.example.com/apply"
    custom_present = _Page(url, text, counts={"form": 1, "button.apply": 1, _SUBMIT: 0})
    custom_absent = _Page(url, text, counts={"form": 1, _SUBMIT: 1})
    blocked = verify_page(custom_present, submit_selector="button.apply")
    ignored_default = verify_page(custom_absent, submit_selector="button.apply")
    assert blocked.verified is False and blocked.confidence == "low"
    assert ignored_default.verified is True and ignored_default.confidence == "medium"


def test_verify_page_reports_a_navigation_with_no_confirmation():
    page = _Page("https://jobs.example.com/next", "Still working")
    found = verify_page(page, url_before="https://jobs.example.com/apply")
    assert found.verified is False and found.confidence == "low"
    assert "without confirmation text" in found.evidence


def test_verify_page_survives_a_page_that_throws():
    slow = verify_page(_Page("https://jobs.example.com/apply", "We've received your application.", fail="wait"))
    assert slow.verified is True and slow.confidence == "medium"

    unreadable = verify_page(_Page("https://jobs.example.com/apply", "Thank you for applying", fail="text"))
    assert unreadable == Verification(False, "none", "no confirmation found")

    blind = verify_page(_Page("https://jobs.example.com/apply", "We've received your application.", fail="locator"))
    assert blind.verified is True and blind.confidence == "medium"
