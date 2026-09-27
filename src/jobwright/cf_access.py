"""Keep the Cloudflare Access allowlist in sync with users.yaml.

Only the allow policy named ``jobwright users`` on the dashboard's Access app
is ever written; every other policy is read for reporting and left untouched.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx

from jobwright.users import list_admin_emails, list_users, normalize_email

log = logging.getLogger(__name__)

API_BASE = "https://api.cloudflare.com/client/v4"
MANAGED_POLICY_NAME = "jobwright users"
DEFAULT_HOSTNAME = "jobwright.parthchandak.info"
REQUIRED_PERMISSION = "Account > Access: Apps and Policies > Edit"
_CERT_BLOCK = re.compile(r"-----BEGIN ARGO TUNNEL TOKEN-----(.+?)-----END ARGO TUNNEL TOKEN-----", re.S)


class CFAccessError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(os.environ.get("CLOUDFLARE_API_TOKEN", "").strip())


def cert_path() -> Path:
    return Path.home() / ".cloudflared" / "cert.pem"


def account_id_from_cert(path: Path | None = None) -> str:
    """Account id from cloudflared's origin cert (its embedded token is never used)."""
    try:
        text = (path or cert_path()).read_text(encoding="utf-8")
    except OSError:
        return ""
    m = _CERT_BLOCK.search(text)
    if not m:
        return ""
    try:
        data = json.loads(base64.b64decode("".join(m.group(1).split())))
    except (ValueError, TypeError):
        return ""
    return str(data.get("accountID") or "") if isinstance(data, dict) else ""


def desired_emails() -> list[str]:
    emails = {normalize_email(e) for u in list_users() for e in u.emails}
    emails.update(list_admin_emails())
    return sorted(e for e in emails if e)


def rule_emails(rules: list[dict] | None) -> list[str]:
    out: set[str] = set()
    for rule in rules or []:
        e = normalize_email(((rule or {}).get("email") or {}).get("email"))
        if e:
            out.add(e)
    return sorted(out)


class CFAccessClient:
    def __init__(
        self,
        token: str | None = None,
        account_id: str | None = None,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.token = (token if token is not None else os.environ.get("CLOUDFLARE_API_TOKEN", "")).strip()
        if not self.token:
            raise CFAccessError("CLOUDFLARE_API_TOKEN is not set.")
        self.account_id = (
            account_id or os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip() or account_id_from_cert()
        )
        if not self.account_id:
            raise CFAccessError("CLOUDFLARE_ACCOUNT_ID is not set and ~/.cloudflared/cert.pem has no account id.")
        self._http = httpx.Client(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {self.token}"},
            transport=transport,
            timeout=timeout,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            resp = self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise CFAccessError(f"Cloudflare API unreachable: {exc}") from exc
        if resp.status_code in (401, 403):
            raise CFAccessError(
                f"Cloudflare API rejected the token (HTTP {resp.status_code}) on {method} {path}. "
                f"The token needs permission {REQUIRED_PERMISSION} for account {self.account_id}."
            )
        try:
            body = resp.json()
        except ValueError:
            body = {}
        if resp.status_code >= 400 or not body.get("success", False):
            errors = "; ".join(str(e.get("message", e)) for e in body.get("errors") or []) or resp.text[:200]
            if "authentication" in errors.lower():
                raise CFAccessError(
                    f"Cloudflare rejected the API token (check CLOUDFLARE_API_TOKEN; it needs {REQUIRED_PERMISSION})."
                )
            raise CFAccessError(f"Cloudflare API {method} {path} failed (HTTP {resp.status_code}): {errors}")
        return resp

    def _result(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._request(method, path, **kwargs).json().get("result")

    def _list(self, path: str) -> list[dict]:
        out: list[dict] = []
        page = 1
        while True:
            body = self._request("GET", path, params={"page": page, "per_page": 100}).json()
            out.extend(body.get("result") or [])
            info = body.get("result_info") or {}
            if page >= int(info.get("total_pages") or 1):
                return out
            page += 1

    @property
    def _acct(self) -> str:
        return f"/accounts/{self.account_id}/access"

    def find_app(self, aud: str | None = None, hostname: str | None = None) -> dict:
        aud = (aud if aud is not None else os.environ.get("JOBWRIGHT_CF_AUD", "")).strip()
        hostname = (hostname or os.environ.get("JOBWRIGHT_CF_HOSTNAME", "") or DEFAULT_HOSTNAME).strip().lower()
        apps = self._list(f"{self._acct}/apps")
        if aud:
            for app in apps:
                if app.get("aud") == aud:
                    return app
        for app in apps:
            domains = {str(app.get("domain") or "").lower().rstrip("/")}
            domains.update(str(d).lower().rstrip("/") for d in app.get("self_hosted_domains") or [])
            if hostname in domains:
                return app
        raise CFAccessError(f"No Cloudflare Access app found for aud {aud or '(unset)'} or hostname {hostname}.")

    def app_policies(self, app: dict) -> list[dict]:
        """App-scoped policies plus any reusable policies the app references, by id."""
        found: dict[str, dict] = {}
        for p in self._list(f"{self._acct}/apps/{app['id']}/policies"):
            found[p["id"]] = p
        for ref in app.get("policies") or []:
            pid = ref.get("id")
            if not pid or pid in found:
                continue
            policy = dict(ref)
            if "include" not in policy or policy.get("reusable"):
                policy = {**policy, **(self._result("GET", f"{self._acct}/policies/{pid}") or {})}
            found[pid] = policy
        return sorted(found.values(), key=lambda p: (p.get("precedence") or 0, p.get("name") or ""))

    def create_policy(self, app: dict, include: list[dict], precedence: int) -> dict:
        body = {"name": MANAGED_POLICY_NAME, "decision": "allow", "include": include, "precedence": precedence}
        return self._result("POST", f"{self._acct}/apps/{app['id']}/policies", json=body)

    def update_policy(self, app: dict, policy: dict, include: list[dict]) -> dict:
        if policy.get("name") != MANAGED_POLICY_NAME:
            raise CFAccessError(f"Refusing to modify policy {policy.get('name')!r}.")
        body: dict[str, Any] = {
            "name": MANAGED_POLICY_NAME,
            "decision": "allow",
            "include": include,
            "exclude": policy.get("exclude") or [],
            "require": policy.get("require") or [],
        }
        if policy.get("reusable"):
            return self._result("PUT", f"{self._acct}/policies/{policy['id']}", json=body)
        if policy.get("precedence") is not None:
            body["precedence"] = policy["precedence"]
        return self._result("PUT", f"{self._acct}/apps/{app['id']}/policies/{policy['id']}", json=body)


def _managed(policies: list[dict]) -> dict | None:
    return next((p for p in policies if p.get("name") == MANAGED_POLICY_NAME), None)


def _read_state(client: CFAccessClient) -> tuple[dict, list[dict], dict]:
    app = client.find_app()
    policies = client.app_policies(app)
    managed = _managed(policies)
    current = rule_emails(managed.get("include")) if managed else []
    desired = desired_emails()
    others: set[str] = set()
    for p in policies:
        if p is not managed and p.get("decision") == "allow":
            others.update(rule_emails(p.get("include")))
    plan = {
        "configured": True,
        "app": {"id": app.get("id"), "name": app.get("name"), "domain": app.get("domain")},
        "managed_policy": {"id": managed.get("id") if managed else None, "name": MANAGED_POLICY_NAME,
                           "exists": managed is not None},
        "current": current,
        "desired": desired,
        "add": sorted(set(desired) - set(current)),
        "remove": sorted(set(current) - set(desired)),
        "other_policies_emails": sorted(others),
        "other_policies": [p.get("name") for p in policies if p is not managed],
    }
    plan["in_sync"] = managed is not None and not plan["add"] and not plan["remove"]
    return app, policies, plan


def plan_sync(client: CFAccessClient | None = None) -> dict:
    return _read_state(client or CFAccessClient())[2]


def apply_sync(client: CFAccessClient | None = None) -> dict:
    client = client or CFAccessClient()
    app, policies, plan = _read_state(client)
    if not plan["desired"]:
        raise CFAccessError("Refusing to sync: users.yaml has no emails (the policy would lock everyone out).")
    include = [{"email": {"email": e}} for e in plan["desired"]]
    managed = _managed(policies)
    if managed is None:
        precedence = max((int(p.get("precedence") or 0) for p in policies), default=0) + 1
        created = client.create_policy(app, include, precedence) or {}
        plan["managed_policy"] = {"id": created.get("id"), "name": MANAGED_POLICY_NAME, "exists": True}
        plan["created"] = True
    elif plan["add"] or plan["remove"]:
        client.update_policy(app, managed, include)
        plan["created"] = False
    else:
        plan["created"] = False
        plan["applied"] = False
        return plan
    plan["applied"] = True
    plan["current"] = plan["desired"]
    plan["in_sync"] = True
    return plan


def status() -> dict:
    """Plan for the dashboard, or ``{configured: False, error}``; never raises."""
    if not is_configured():
        return {"configured": False, "error": "CLOUDFLARE_API_TOKEN is not set."}
    try:
        return plan_sync()
    except CFAccessError as exc:
        return {"configured": True, "error": str(exc)}


def auto_sync() -> dict | None:
    """Best-effort sync after a login change; ``None`` when no token is set."""
    if not is_configured():
        return None
    try:
        res = apply_sync()
        return {"ok": True, "applied": res.get("applied", False), "add": res["add"], "remove": res["remove"]}
    except CFAccessError as exc:
        log.warning("Cloudflare Access sync failed: %s", exc)
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001
        log.exception("Cloudflare Access sync crashed")
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
