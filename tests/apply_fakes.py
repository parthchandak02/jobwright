"""Offline fakes for the apply tests: a local fake ATS site and a scripted Claude client.

Nothing here touches the network beyond 127.0.0.1, and no real model is called.
"""

from __future__ import annotations

import copy
import json
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs

BASE_FIELDS = """
<label for="name">Full name</label><input id="name" name="name" required>
<label for="email">Email</label><input id="email" name="email" type="email" required>
<label for="phone">Phone</label><input id="phone" name="phone">
<label for="resume">Resume</label><input id="resume" name="resume" type="file">
<label for="why">Why do you want to work here?</label><textarea id="why" name="why"></textarea>
<label for="auth">Are you legally authorized to work in the United States?</label>
<select id="auth" name="auth"><option value="">Select</option><option>Yes</option><option>No</option></select>
<fieldset><legend>Will you now or in the future require visa sponsorship?</legend>
<label><input type="radio" name="spon" value="yes">Yes</label>
<label><input type="radio" name="spon" value="no">No</label></fieldset>
"""

FELONY = """
<label for="felony">Have you ever been convicted of a felony?</label>
<select id="felony" name="felony"><option value="">Select</option><option>Yes</option><option>No</option></select>
"""

CAPTCHA = '<div class="g-recaptcha" data-sitekey="test-site-key" style="width:300px;height:80px"></div>'


def page(title: str, body: str) -> str:
    return f"<!doctype html><html><head><title>{title}</title></head><body>{body}</body></html>"


def form_page(jid: str, extra: str = "", button: str = "Submit application", novalidate: bool = False) -> str:
    nv = " novalidate" if novalidate else ""
    return page("Apply - Example Co", f"""<h1>Data Analyst</h1>
<form method="post" action="/submit/{jid}" enctype="multipart/form-data"{nv}>{BASE_FIELDS}{extra}
<button type="submit">{button}</button></form>""")


class FakeATS:
    """Serves application forms under /apply/<jid> and records every POST."""

    def __init__(self) -> None:
        self.posts: list[tuple[str, bytes]] = []
        self.pages: dict[str, str] = {
            "std": form_page("std"),
            "felony": form_page("felony", FELONY),
            "captcha": form_page("captcha", CAPTCHA),
            "code": form_page("code"),
            "bad": form_page("bad"),
            "go": form_page("go", button="Go", novalidate=True),
            "acct": page("Sign up - Example Co", """<h1>Create your candidate account</h1>
<form method="post" action="/account"><label for="em">Email</label><input id="em" name="email" type="email">
<label for="pw">Password</label><input id="pw" name="password" type="password">
<button type="submit">Create account</button></form>"""),
        }
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def _send(self, code: int, body: str = "", location: str | None = None) -> None:
                data = body.encode()
                self.send_response(code)
                if location:
                    self.send_header("Location", location)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):  # noqa: N802
                m = re.match(r"^/apply/(\w+)$", self.path)
                if m and m.group(1) in fake.pages:
                    return self._send(200, fake.pages[m.group(1)])
                m = re.match(r"^/done/(\w+)$", self.path)
                if m:
                    return self._send(200, page("Application received",
                                                "<h1>Thank you for applying!</h1><p>We have received your application.</p>"))
                if self.path == "/favicon.ico":
                    return self._send(404)
                return self._send(404, page("Not found", "<p>Not found</p>"))

            def do_POST(self):  # noqa: N802
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length)
                fake.posts.append((self.path, body))
                m = re.match(r"^/submit/(\w+)$", self.path)
                if m:
                    jid = m.group(1)
                    if jid == "code":
                        return self._send(200, page("Verify your email", """<p>Enter the verification code we emailed you.</p>
<form method="post" action="/verify/code"><label for="code">Verification code</label><input id="code" name="code">
<button type="submit">Verify</button></form>"""))
                    if jid == "bad":
                        return self._send(200, page("Error", "<p>Something went wrong, please try again later.</p>"))
                    return self._send(303, location=f"/done/{jid}")
                if self.path == "/verify/code":
                    code = parse_qs(body.decode()).get("code", [""])[0]
                    if code == "123456":
                        return self._send(303, location="/done/code")
                    return self._send(200, page("Wrong code", "<p>That code is not valid.</p>"))
                if self.path == "/account":
                    return self._send(303, location="/apply/std")
                return self._send(404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "FakeATS":
        self.thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self.server.shutdown()
        self.server.server_close()

    def url(self, jid: str) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/apply/{jid}"

    def post_paths(self) -> list[str]:
        return [p for p, _ in self.posts]


# ---------------------------------------------------------------------------
# Scripted Claude client
# ---------------------------------------------------------------------------


def find_ref(snapshot: str, spec: str) -> str:
    """Resolve "@label" or "@group>label" against snapshot element lines."""
    group, _, label = spec.lstrip("@").rpartition(">")
    for line in snapshot.splitlines():
        m = re.match(r"^(f?\d*e\d+) ", line)
        if not m:
            continue
        lab = re.search(r"label='([^']*)'|label=\"([^\"]*)\"", line)
        text = (lab.group(1) or lab.group(2) or "") if lab else ""
        if label.lower() not in text.lower():
            continue
        if group and group.lower() not in line.lower():
            continue
        return m.group(1)
    raise AssertionError(f"no element matching {spec!r} in snapshot:\n{snapshot}")


class ScriptedClient:
    """Fake ``anthropic.Anthropic``: each ``beta.messages.create`` returns the next scripted tool call.

    Script items: ``(tool_name, input_dict)``; string values starting with "@"
    are element refs resolved against the latest snapshot result.
    """

    def __init__(self, script: list[tuple[str, dict]]) -> None:
        self.script = list(script)
        self.requests: list[dict] = []
        self.results: list[str] = []
        self._n = 0
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _latest_snapshot(self, messages: list[dict]) -> str:
        for msg in reversed(messages):
            if msg["role"] != "user" or not isinstance(msg["content"], list):
                continue
            for block in msg["content"]:
                if block.get("type") == "tool_result" and str(block.get("content", "")).startswith("URL:"):
                    return block["content"]
        return ""

    def _create(self, **kw):
        self.requests.append(copy.deepcopy({k: v for k, v in kw.items() if k != "tools"}))
        messages = kw["messages"]
        last = messages[-1]
        if last["role"] == "user" and isinstance(last["content"], list):
            self.results.extend(str(b.get("content", "")) for b in last["content"] if b.get("type") == "tool_result")
        usage = {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 0,
                 "cache_creation_input_tokens": 0}
        if not self.script:
            return {"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn", "usage": usage,
                    "model": "claude-sonnet-5-5"}
        name, args = self.script.pop(0)
        snap = self._latest_snapshot(messages)
        resolved = {k: (find_ref(snap, v) if isinstance(v, str) and v.startswith("@") else v)
                    for k, v in args.items()}
        self._n += 1
        return {"content": [{"type": "tool_use", "id": f"tu_{self._n}", "name": name, "input": resolved}],
                "stop_reason": "tool_use", "usage": usage, "model": "claude-sonnet-5-5"}

    def all_text(self) -> str:
        return json.dumps(self.requests, default=str)


def fill_form_steps(*, phone: str = "+1 415 555 0100") -> list[tuple[str, dict]]:
    return [
        ("fill", {"ref": "@Full name", "value": "Alex Rivera", "source": "profile", "category": None}),
        ("fill", {"ref": "@Email", "value": "user1@example.com", "source": "profile", "category": None}),
        ("fill", {"ref": "@Phone", "value": phone, "source": "answer_bank", "category": None}),
        ("upload_file", {"ref": "@Resume", "which": "resume"}),
        ("fill", {"ref": "@Why do you want", "value": "I have built reporting for small teams and like your "
                  "focus on clear data.", "source": "resume_ai", "category": None}),
        ("select", {"ref": "@legally authorized", "option": "Yes", "source": "answer_bank",
                    "category": "work_authorization"}),
        ("click", {"ref": "@sponsorship>No"}),
    ]


def provide_when_open(kind: str, value: str, *, timeout: float = 20.0, by: str = "test") -> threading.Thread:
    """Background 'person': provides the first open pending input of ``kind``."""
    from jobwright.apply import hitl

    def run():
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            rows = [r for r in hitl.list_pending("open") if r["kind"] == kind]
            if rows:
                hitl.provide(rows[0]["id"], value, by=by)
                return
            time.sleep(0.05)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t
