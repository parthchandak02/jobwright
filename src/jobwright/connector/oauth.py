"""OAuth 2.1 for the Claude connector, with the dashboard's own sign-in.

What Claude's custom connectors need: protected-resource and authorization-
server metadata, dynamic client registration, the authorization-code flow
with S256 PKCE, refresh tokens (rotated), and a 401 with
``WWW-Authenticate: Bearer resource_metadata=...`` from ``/mcp``.

The person is identified exactly like on the dashboard: ``/oauth/authorize``
stays behind Cloudflare Access, so it carries the Access JWT and
``web.auth.identify`` verifies it. Their login email picks the jobwright
profile(s) whose ``emails`` list it (users.yaml); with several, the consent
page asks which. Admins may pick any profile, as on the dashboard; everyone else
can only connect a profile that lists their own login.

Public (must bypass Access): ``/.well-known/oauth-*``, ``/oauth/register``,
``/oauth/token``, ``/oauth/revoke`` and ``/mcp`` (bearer-protected).
"""

from __future__ import annotations

import base64
import hashlib
import html
import logging
import os
import threading
import time
from collections import deque
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from jobwright.connector import store

log = logging.getLogger(__name__)

router = APIRouter(include_in_schema=False)

HOSTED_CALLBACKS = (
    "https://claude.ai/api/mcp/auth_callback",
    "https://claude.com/api/mcp/auth_callback",
)
_AUTHORIZE_FIELDS = ("client_id", "redirect_uri", "state", "code_challenge", "code_challenge_method",
                     "response_type", "resource", "scope")


def base_url() -> str:
    from jobwright.notify import DEFAULT_BASE_URL

    return os.environ.get("JOBWRIGHT_PUBLIC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def resource_url() -> str:
    return f"{base_url()}/mcp"


def resource_metadata_url() -> str:
    return f"{base_url()}/.well-known/oauth-protected-resource"


def _no_store(resp: Response) -> Response:
    resp.headers["Cache-Control"] = "no-store"
    resp.headers["Pragma"] = "no-cache"
    return resp


def _json(data: dict, status: int = 200) -> JSONResponse:
    return _no_store(JSONResponse(data, status_code=status))  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Rate limits (in memory, per client IP; one process serves the dashboard)
# ---------------------------------------------------------------------------


class RateLimiter:
    def __init__(self, limit: int, window_s: float) -> None:
        self.limit, self.window = limit, window_s
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Record one event; False when ``key`` is over the limit."""
        t = time.monotonic()
        with self._lock:
            q = self._hits.setdefault(key, deque())
            while q and t - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(t)
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if v}
            return True

    def blocked(self, key: str) -> bool:
        """True when ``key`` is over the limit (without recording anything)."""
        t = time.monotonic()
        with self._lock:
            q = self._hits.get(key)
            while q and t - q[0] > self.window:
                q.popleft()
            return bool(q) and len(q) >= self.limit

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


REGISTER_LIMIT = RateLimiter(30, 3600)
TOKEN_FAILURE_LIMIT = RateLimiter(30, 600)
AUTHORIZE_LIMIT = RateLimiter(60, 600)


def client_ip(request: Request) -> str:
    return (request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "") or "?")


def _too_many() -> JSONResponse:
    resp = _json({"error": "slow_down", "error_description": "Too many requests. Try again later."}, 429)
    resp.headers["Retry-After"] = "600"
    return resp


# ---------------------------------------------------------------------------
# Redirect URIs
# ---------------------------------------------------------------------------


def _loopback(uri: str):
    try:
        u = urlsplit(uri)
    except ValueError:
        return None
    if u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1", "::1") and not u.username:
        return u
    return None


def _extra_callbacks() -> set[str]:
    return {u.strip() for u in os.environ.get("JOBWRIGHT_CONNECTOR_REDIRECTS", "").split(",") if u.strip()}


def allowed_redirect(uri: str) -> bool:
    """Claude's hosted callbacks, a local (loopback) one, or one the operator listed. Nothing else."""
    if not isinstance(uri, str) or len(uri) > 500 or "#" in uri:
        return False
    return uri in HOSTED_CALLBACKS or uri in _extra_callbacks() or _loopback(uri) is not None


def redirect_matches(registered: list[str], uri: str) -> bool:
    """Exact match; for loopback addresses the port may change (native apps pick a new one)."""
    if not allowed_redirect(uri):
        return False
    asked = _loopback(uri)
    for r in registered:
        if r == uri:
            return True
        known = _loopback(r)
        if known and asked and known.hostname == asked.hostname and known.path == asked.path:
            return True
    return False


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


def _resource_metadata() -> JSONResponse:
    return _json({
        "resource": resource_url(),
        "authorization_servers": [base_url()],
        "scopes_supported": list(store.SCOPES),
        "bearer_methods_supported": ["header"],
        "resource_name": "jobwright",
        "resource_documentation": f"{base_url()}/profile?tab=claude",
    })


@router.get("/.well-known/oauth-protected-resource")
def protected_resource() -> JSONResponse:
    return _resource_metadata()


@router.get("/.well-known/oauth-protected-resource/mcp")
def protected_resource_mcp() -> JSONResponse:
    return _resource_metadata()


def _server_metadata() -> JSONResponse:
    base = base_url()
    return _json({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "revocation_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": [*store.SCOPES, *store.EXTRA_SCOPES],
        "authorization_response_iss_parameter_supported": True,
    })


@router.get("/.well-known/oauth-authorization-server")
def authorization_server() -> JSONResponse:
    return _server_metadata()


@router.get("/.well-known/oauth-authorization-server/mcp")
def authorization_server_mcp() -> JSONResponse:
    return _server_metadata()


# ---------------------------------------------------------------------------
# Dynamic client registration (RFC 7591), public clients only
# ---------------------------------------------------------------------------


@router.post("/oauth/register")
async def register(request: Request) -> JSONResponse:
    if not REGISTER_LIMIT.hit(client_ip(request)):
        return _too_many()
    try:
        body = await request.json()
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return _json({"error": "invalid_client_metadata", "error_description": "JSON body required"}, 400)
    uris = body.get("redirect_uris")
    if not isinstance(uris, list) or not uris or len(uris) > 5 or not all(allowed_redirect(u) for u in uris):
        return _json({"error": "invalid_redirect_uri",
                      "error_description": "Only Claude's own callback or a local address may be registered."}, 400)
    # Public clients only: whatever auth method is asked for, the answer is "none" (no secret is issued),
    # as RFC 7591 lets the server decide. PKCE is what binds the code to the client.
    name = body.get("client_name") if isinstance(body.get("client_name"), str) else "Claude"
    name = " ".join(name.split())[:80] or "Claude"
    client = store.register_client(name, uris)
    return _json({**client, "token_endpoint_auth_method": "none",
                  "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
                  "client_id_issued_at": store.now()}, 201)


# ---------------------------------------------------------------------------
# Authorize: consent page behind Cloudflare Access
# ---------------------------------------------------------------------------


def _validate(q: dict) -> str | None:
    client = store.get_client(q.get("client_id"))
    if client is None or not q.get("redirect_uri") or not redirect_matches(client["redirect_uris"], q["redirect_uri"]):
        return "Unknown app or return address."
    if q.get("response_type") != "code":
        return "Only response_type=code is supported."
    challenge = q.get("code_challenge") or ""
    if q.get("code_challenge_method") != "S256" or not (43 <= len(challenge) <= 128):
        return "This request is missing its security check (S256 PKCE)."
    if q.get("resource") and q["resource"].rstrip("/") != resource_url():
        return "This request is for a different server."
    bad = store.unknown_scopes(q.get("scope"))
    if bad:
        return f"Unknown permission requested: {', '.join(bad)}."
    return None


def _identity(request: Request):
    from jobwright.web.auth import AuthError, identify

    headers = {k.lower(): v for k, v in request.headers.items()}
    try:
        return identify(headers, dict(request.cookies), request.client.host if request.client else None), None
    except AuthError as exc:
        return None, str(exc)


_CSS = """
*{box-sizing:border-box}
:root{--bg:#fbfaf9;--card:#fff;--fg:#1b1c1f;--muted:#6b6d73;--line:#e7e5e1;--soft:#f3f2ef;
--primary:#3664be;--primary-fg:#fff;--tint:rgba(54,100,190,.08);--warn:#9a3b0f;--warn-bg:#fdf1ea}
@media(prefers-color-scheme:dark){:root{--bg:#0c0d0f;--card:#16171a;--fg:#ecebe8;--muted:#9a9ca3;
--line:#2a2b30;--soft:#1d1e22;--primary:#8aa8e6;--primary-fg:#0c0d0f;--tint:rgba(138,168,230,.12);
--warn:#f2a07a;--warn-bg:#2a1a12}}
body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px 14px;
background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
-webkit-font-smoothing:antialiased}
main{width:100%;max-width:440px;background:var(--card);border:1px solid var(--line);border-radius:18px;
padding:28px;box-shadow:0 1px 2px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.05)}
.brand{display:flex;align-items:center;gap:10px;margin-bottom:22px;font-weight:600;letter-spacing:-.01em}
.brand img{width:32px;height:32px;border-radius:8px}
h1{margin:0 0 6px;font-size:22px;line-height:1.25;font-weight:650;letter-spacing:-.015em}
p{margin:0}.lead{color:var(--muted)}.who{margin-top:10px;font-size:13px;color:var(--muted)}
.who b{color:var(--fg);font-weight:600}
h2{margin:26px 0 10px;font-size:13px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.hint{margin:-4px 0 10px;font-size:13px;color:var(--muted)}
.cards{display:grid;gap:8px}
.card{display:flex;align-items:center;gap:12px;padding:12px 14px;border:1px solid var(--line);border-radius:12px;
cursor:pointer;transition:border-color .12s,background .12s}
.card:hover{border-color:var(--muted)}
.card input{position:absolute;opacity:0;pointer-events:none}
.card:has(input:checked){border-color:var(--primary);background:var(--tint)}
.card:has(input:focus-visible){outline:2px solid var(--primary);outline-offset:2px}
.avatar{flex:none;width:36px;height:36px;border-radius:50%;display:grid;place-items:center;font-weight:600;
font-size:14px;background:var(--soft);color:var(--fg)}
.card:has(input:checked) .avatar{background:var(--primary);color:var(--primary-fg)}
.name{font-weight:600}.sub{font-size:13px;color:var(--muted)}
.dot{margin-left:auto;width:18px;height:18px;border-radius:50%;border:2px solid var(--line);flex:none}
.card:has(input:checked) .dot{border:5px solid var(--primary)}
.perms{border:1px solid var(--line);border-radius:12px;overflow:hidden}
.perm{display:flex;gap:14px;align-items:flex-start;padding:14px;cursor:pointer}
.perm+.perm{border-top:1px solid var(--line)}
.perm .t{display:block;font-weight:600}.perm .d{display:block;font-size:13px;color:var(--muted);margin-top:2px}
.perm .txt{flex:1}
.badge{flex:none;font-size:12px;color:var(--muted);background:var(--soft);border-radius:999px;padding:3px 9px;margin-top:2px}
.switch{flex:none;appearance:none;-webkit-appearance:none;margin:2px 0 0;width:40px;height:24px;border-radius:999px;
background:var(--line);position:relative;cursor:pointer;transition:background .15s}
.switch::after{content:"";position:absolute;top:3px;left:3px;width:18px;height:18px;border-radius:50%;background:#fff;
box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
.switch:checked{background:var(--primary)}.switch:checked::after{transform:translateX(16px)}
.switch:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
.note{margin-top:18px;font-size:13px;color:var(--muted)}
.warn{margin-top:14px;padding:10px 12px;border-radius:10px;background:var(--warn-bg);color:var(--warn);font-size:14px}
.actions{display:grid;gap:8px;margin-top:22px}
button{font:inherit;font-weight:600;border-radius:12px;padding:13px 16px;cursor:pointer;border:1px solid transparent;
min-height:46px}
button.primary{background:var(--primary);color:var(--primary-fg)}
button.primary:hover{filter:brightness(1.05)}
button.ghost{background:transparent;color:var(--muted);border-color:var(--line)}
button:focus-visible{outline:2px solid var(--primary);outline-offset:2px}
.msg h1{margin-bottom:8px}.msg .lead{color:var(--fg)}
@media (max-width:420px){main{padding:22px 18px;border-radius:16px}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
"""

_BRAND = "<div class=brand><img src='/icon-192.png' alt='' width=32 height=32><span>jobwright</span></div>"


def _email(addr: str | None) -> str:
    # Cloudflare's email obfuscation rewrites addresses into "[email protected]" links; opt this one out.
    return f"<!--email_off-->{html.escape(addr or '')}<!--/email_off-->"


def _page(body: str, status: int = 200, *, form_target: str | None = None) -> HTMLResponse:
    esc = html.escape
    csp = ("default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; frame-ancestors 'none'; "
           "base-uri 'none'; form-action 'self'")
    if form_target:
        csp += f" {form_target}"
    doc = (f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,"
           f"initial-scale=1'><meta name=robots content=noindex><meta name=color-scheme content='light dark'>"
           f"<title>{esc('Connect Claude to jobwright')}</title><link rel=icon href='/favicon.ico'>"
           f"<style>{_CSS}</style><main>{_BRAND}{body}</main></html>")
    resp = HTMLResponse(doc, status_code=status)
    resp.headers["Content-Security-Policy"] = csp
    resp.headers["X-Frame-Options"] = "DENY"
    # "same-origin", not "no-referrer": with no-referrer browsers send "Origin: null" on our own form POST,
    # which the Origin check rejects. same-origin still sends nothing to claude.ai.
    resp.headers["Referrer-Policy"] = "same-origin"
    return _no_store(resp)  # type: ignore[return-value]


def _message(title: str, text: str, status: int, *, html_text: str | None = None) -> HTMLResponse:
    body = (f"<div class=msg><h1>{html.escape(title)}</h1><p class=lead>{html_text or html.escape(text)}</p>"
            f"<p class=note>You can close this tab and start again from Claude.</p></div>")
    return _page(body, status)


_PERM_TEXT = {
    "jobs:read": ("See your jobs", "Jobs, scores, today's picks and your saved answers."),
    "jobs:write": ("Update your board", "Rate and move jobs, save answers and tailored resumes, skip picks."),
    "apply": ("Apply for you", "Fill applications in your own browser with Claude in Chrome, using only your "
              "saved answers, and keep a record of every answer sent."),
}


def _initials(name: str) -> str:
    parts = [w for w in (name or "?").split() if w]
    return ("".join(w[0] for w in parts[:2]) or "?").upper()


def _consent_page(q: dict, identity, profiles, nonce: str) -> HTMLResponse:
    from jobwright.users import is_admin_email, normalize_email

    esc = html.escape
    client = store.get_client(q["client_id"]) or {"client_name": "Claude"}
    target = urlsplit(q["redirect_uri"])
    host = target.hostname or ""
    origin = f"{target.scheme}://{target.netloc}"
    asked = store.normalize_scope(q.get("scope")).split()
    me = normalize_email(identity.email)
    admin = is_admin_email(identity.email)
    local = ("" if q["redirect_uri"] in HOSTED_CALLBACKS else
             "<p class=warn>This returns to a program on your own computer. Only continue if you started it.</p>")

    def own(p) -> bool:
        return me in {normalize_email(x) for x in p.emails}

    if len(profiles) == 1:
        p = profiles[0]
        picker = (f"<input type=hidden name=user_id value='{esc(p.user_id)}'>"
                  f"<h2>Job search</h2><div class=cards><div class=card style='cursor:default'>"
                  f"<span class=avatar>{esc(_initials(p.name or p.user_id))}</span>"
                  f"<span><span class=name>{esc(p.name or p.user_id)}</span></span></div></div>")
    else:
        ordered = sorted(profiles, key=lambda p: (not own(p), (p.name or p.user_id).lower()))
        cards = "".join(
            f"<label class=card><input type=radio name=user_id value='{esc(p.user_id)}' required"
            f"{' checked' if i == 0 and own(p) else ''}><span class=avatar>{esc(_initials(p.name or p.user_id))}</span>"
            f"<span><span class=name>{esc(p.name or p.user_id)}</span><br>"
            f"<span class=sub>{'Your job search' if own(p) else 'Admin access'}</span></span>"
            f"<span class=dot aria-hidden=true></span></label>"
            for i, p in enumerate(ordered))
        hint = ("<p class=hint>You're an admin, so you can connect anyone's job search.</p>"
                if admin and any(not own(p) for p in profiles) else "")
        picker = f"<h2>Which profile?</h2>{hint}<div class=cards role=radiogroup>{cards}</div>"

    rows = []
    for s in store.SCOPES:
        title, desc = _PERM_TEXT.get(s, (store.SCOPE_LABELS[s], ""))
        if s == "jobs:read":
            control = "<span class=badge>Always on</span>"
            rows.append(f"<div class=perm><span class=txt><span class=t>{esc(title)}</span>"
                        f"<span class=d>{esc(desc)}</span></span>{control}</div>")
        else:
            checked = " checked" if s in asked else ""
            rows.append(f"<label class=perm><span class=txt><span class=t>{esc(title)}</span>"
                        f"<span class=d>{esc(desc)}</span></span>"
                        f"<input class=switch type=checkbox role=switch name=scope value='{esc(s)}'{checked}"
                        f" aria-label='{esc(title)}'></label>")
    body = (
        f"<h1>Connect {esc(client['client_name'])} to your job search</h1>"
        f"<p class=lead>{esc(client['client_name'])} on <b>{esc(host)}</b> will be able to use jobwright for you.</p>"
        f"<p class=who>Signed in as <b>{_email(identity.email)}</b></p>{local}"
        f"<form method=post action='/oauth/authorize'>"
        f"<input type=hidden name=consent value='{esc(nonce)}'>{picker}"
        f"<h2>What Claude can do</h2><div class=perms>{''.join(rows)}</div>"
        f"<p class=note>You can disconnect at any time in jobwright: Settings, Claude.</p>"
        f"<div class=actions><button class=primary name=action value=allow>Connect</button>"
        f"<button class=ghost name=action value=deny formnovalidate>Cancel</button></div></form>"
    )
    return _page(body, form_target=origin)


@router.get("/oauth/authorize")
def authorize_page(request: Request) -> Response:
    if not AUTHORIZE_LIMIT.hit(client_ip(request)):
        return _message("Too many tries", "Wait a few minutes, then connect again from Claude.", 429)
    q = {k: request.query_params.get(k) for k in _AUTHORIZE_FIELDS if request.query_params.get(k)}
    bad = _validate(q)
    if bad:
        return _message("Can't connect", bad, 400)
    identity, err = _identity(request)
    if identity is None:
        return _message("Sign in first", f"Open this from the jobwright sign-in. ({err})", 401)
    profiles = _profiles_for(identity.email)
    if not profiles:
        return _message("No jobwright profile yet", "", 403,
                        html_text=f"{_email(identity.email) if identity.email else 'This login'} isn't linked to a "
                        "jobwright profile. Ask the person who runs your jobwright to add this email, then "
                        "connect again from Claude.")
    nonce = store.create_consent(identity.email, q)
    return _consent_page(q, identity, profiles, nonce)


def _profiles_for(email: str):
    """Profiles this login may connect: its own, or every profile for an admin (as on the dashboard)."""
    from jobwright.users import profiles_for_login

    return profiles_for_login(email) if email else []


def _redirect(uri: str, params: dict) -> RedirectResponse:
    sep = "&" if urlsplit(uri).query else "?"
    resp = RedirectResponse(uri + sep + urlencode({k: v for k, v in params.items() if v is not None}), 302)
    return _no_store(resp)  # type: ignore[return-value]


@router.post("/oauth/authorize")
async def authorize_submit(request: Request) -> Response:
    if not AUTHORIZE_LIMIT.hit(client_ip(request)):
        return _message("Too many tries", "Wait a few minutes, then connect again from Claude.", 429)
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") not in (base_url(), _request_origin(request)):
        return _message("Can't connect", "This page was opened from another site, so it was blocked for your "
                        "safety. Start connecting again from Claude.", 403)
    form = await request.form()
    identity, err = _identity(request)
    if identity is None:
        return _message("Sign in first", f"Open this from the jobwright sign-in. ({err})", 401)
    q = store.take_consent(str(form.get("consent") or ""), identity.email)
    if q is None:
        return _message("This page expired", "Start connecting again from Claude.", 400)
    bad = _validate(q)
    if bad:
        return _message("Can't connect", bad, 400)
    if form.get("action") != "allow":
        return _redirect(q["redirect_uri"], {"error": "access_denied", "state": q.get("state"), "iss": base_url()})
    user_id = str(form.get("user_id") or "")
    if user_id not in {p.user_id for p in _profiles_for(identity.email)}:
        return _message("Can't connect", "That profile does not belong to this login.", 403)
    picked = [s for s in form.getlist("scope") if s in store.SCOPES]
    scope = " ".join(s for s in store.SCOPES if s == "jobs:read" or s in picked)
    code = store.create_code(client_id=q["client_id"], user_id=user_id, email=identity.email,
                             redirect_uri=q["redirect_uri"], challenge=q["code_challenge"], scope=scope,
                             resource=q.get("resource"))
    log.info("connector: %s approved %s for profile %s (%s)", identity.email, q["client_id"], user_id, scope)
    return _redirect(q["redirect_uri"], {"code": code, "state": q.get("state"), "iss": base_url()})


def _request_origin(request: Request) -> str:
    return f"{request.url.scheme}://{request.url.netloc}"


# ---------------------------------------------------------------------------
# Token and revocation
# ---------------------------------------------------------------------------


def pkce_ok(verifier: str, challenge: str) -> bool:
    if not verifier or not (43 <= len(verifier) <= 128):
        return False
    computed = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return store.same(computed, challenge)


def _denied(request: Request, description: str) -> JSONResponse:
    TOKEN_FAILURE_LIMIT.hit(client_ip(request))
    return _json({"error": "invalid_grant", "error_description": description}, 400)


@router.post("/oauth/token")
async def token(request: Request) -> JSONResponse:
    if TOKEN_FAILURE_LIMIT.blocked(client_ip(request)):
        return _too_many()
    form = await request.form()
    f = {k: str(v) for k, v in form.items()}
    grant_type = f.get("grant_type")
    if grant_type == "authorization_code":
        row = store.take_code(f.get("code", ""))
        if row is None:
            return _denied(request, "unknown, used or expired code")
        if row["client_id"] != f.get("client_id") or row["redirect_uri"] != f.get("redirect_uri"):
            return _denied(request, "code was issued to another client or return address")
        if not pkce_ok(f.get("code_verifier", ""), row["challenge"]):
            return _denied(request, "code_verifier does not match")
        if f.get("resource") and f["resource"].rstrip("/") != resource_url():
            return _json({"error": "invalid_target"}, 400)
        from jobwright.users import email_opens_profile, get_user

        user = get_user(row["user_id"])
        if not email_opens_profile(row["email"], user):
            return _denied(request, "this login no longer opens that profile")
        grant_id = store.create_grant(client_id=row["client_id"], user_id=row["user_id"], email=row["email"],
                                      scope=row["scope"])
        return _json(store.issue_tokens(grant_id))
    if grant_type == "refresh_token":
        try:
            return _json(store.refresh_tokens(f.get("refresh_token", ""), f.get("client_id")))
        except store.InvalidGrant as exc:
            return _denied(request, str(exc))
    return _json({"error": "unsupported_grant_type"}, 400)


@router.post("/oauth/revoke")
async def revoke(request: Request) -> Response:
    form = await request.form()
    value = str(form.get("token") or "")
    if value:
        store.revoke_token(value)
    return _no_store(Response(status_code=200))
