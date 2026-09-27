"""Cloudflare Access allowlist sync against a mocked Cloudflare API (no network)."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from jobwright import cf_access
from jobwright.cf_access import MANAGED_POLICY_NAME, CFAccessClient, CFAccessError

pytest.importorskip("fastapi")
import test_web_multiuser  # noqa: E402

api_env = test_web_multiuser.api_env

ACCT = "acct123"
APP_ID = "app1"


def _write_registry(users_root, admins, users):
    import yaml

    users_root.mkdir(parents=True, exist_ok=True)
    (users_root / "users.yaml").write_text(yaml.safe_dump({"admins": admins, "users": users}), encoding="utf-8")


class FakeCF:
    def __init__(self, policies=None, reusable=None, status=200):
        self.policies = policies if policies is not None else []
        self.reusable = reusable or []
        self.status = status
        self.calls: list[tuple[str, str, dict | None]] = []

    def app(self):
        refs = [{"id": p["id"], "name": p["name"], "precedence": p["precedence"], "reusable": True}
                for p in self.reusable]
        return {"id": APP_ID, "name": "jobwright", "aud": "aud-tag", "domain": "jobwright.parthchandak.info",
                "policies": refs}

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        path = request.url.path.removeprefix("/client/v4")
        self.calls.append((request.method, path, body))
        if self.status != 200:
            return httpx.Response(self.status, json={"success": False, "errors": [{"message": "Authentication error"}]})
        base = f"/accounts/{ACCT}/access"
        ok = lambda result: httpx.Response(200, json={"success": True, "result": result,  # noqa: E731
                                                      "result_info": {"total_pages": 1}})
        if request.method == "GET" and path == f"{base}/apps":
            return ok([{"id": "other", "aud": "x", "domain": "else.example.com"}, self.app()])
        if request.method == "GET" and path == f"{base}/apps/{APP_ID}/policies":
            return ok(self.policies)
        if request.method == "GET" and path.startswith(f"{base}/policies/"):
            pid = path.rsplit("/", 1)[1]
            return ok(next(p for p in self.reusable if p["id"] == pid))
        if request.method == "POST" and path == f"{base}/apps/{APP_ID}/policies":
            created = {"id": "new1", **body}
            self.policies.append(created)
            return ok(created)
        if request.method == "PUT":
            return ok({"id": path.rsplit("/", 1)[1], **body})
        return httpx.Response(404, json={"success": False, "errors": [{"message": "not found"}]})

    def client(self):
        return CFAccessClient(token="tok", account_id=ACCT, transport=httpx.MockTransport(self.handler))


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    import jobwright.users as users_mod

    monkeypatch.delenv("JOBWRIGHT_ADMIN_EMAILS", raising=False)
    monkeypatch.setenv("JOBWRIGHT_CF_AUD", "aud-tag")
    _write_registry(users_mod.USERS_ROOT, ["Boss@Example.com"], [
        {"user_id": "ann", "emails": ["ann@example.com", " ANN@example.com"]},
        {"user_id": "bo", "emails": ["bo@example.com", "boss@example.com"]},
    ])
    return users_mod.USERS_ROOT


def _email_rules(*emails):
    return [{"email": {"email": e}} for e in emails]


def test_plan_computation(registry):
    fake = FakeCF(policies=[
        {"id": "p1", "name": MANAGED_POLICY_NAME, "decision": "allow", "precedence": 2,
         "include": _email_rules("ann@example.com", "gone@example.com")},
        {"id": "p0", "name": "owner", "decision": "allow", "precedence": 1,
         "include": _email_rules("owner@example.com") + [{"email_domain": {"domain": "corp.com"}}]},
        {"id": "p9", "name": "blockers", "decision": "deny", "precedence": 3, "include": _email_rules("bad@example.com")},
    ])
    plan = cf_access.plan_sync(fake.client())
    assert plan["desired"] == ["ann@example.com", "bo@example.com", "boss@example.com"]
    assert plan["current"] == ["ann@example.com", "gone@example.com"]
    assert plan["add"] == ["bo@example.com", "boss@example.com"]
    assert plan["remove"] == ["gone@example.com"]
    assert plan["other_policies_emails"] == ["owner@example.com"]
    assert plan["in_sync"] is False
    assert all(m == "GET" for m, _, _ in fake.calls)


def test_finds_app_by_hostname_when_aud_unset(registry, monkeypatch):
    monkeypatch.delenv("JOBWRIGHT_CF_AUD")
    assert FakeCF().client().find_app()["id"] == APP_ID


def test_apply_creates_managed_policy_after_existing(registry):
    fake = FakeCF(policies=[{"id": "p0", "name": "owner", "decision": "allow", "precedence": 4,
                             "include": _email_rules("owner@example.com")}])
    res = cf_access.apply_sync(fake.client())
    assert res["created"] is True and res["applied"] is True
    writes = [c for c in fake.calls if c[0] != "GET"]
    assert len(writes) == 1
    method, path, body = writes[0]
    assert (method, path) == ("POST", f"/accounts/{ACCT}/access/apps/{APP_ID}/policies")
    assert body == {"name": MANAGED_POLICY_NAME, "decision": "allow", "precedence": 5,
                    "include": _email_rules("ann@example.com", "bo@example.com", "boss@example.com")}


def test_apply_puts_include_list_and_leaves_others_untouched(registry):
    fake = FakeCF(
        policies=[
            {"id": "p1", "name": MANAGED_POLICY_NAME, "decision": "allow", "precedence": 2,
             "include": _email_rules("gone@example.com"), "require": [{"geo": {"country_code": "US"}}]},
            {"id": "p0", "name": "owner", "decision": "allow", "precedence": 1, "include": _email_rules("o@example.com")},
        ],
        reusable=[{"id": "r1", "name": "shared", "decision": "allow", "precedence": 3,
                   "include": _email_rules("shared@example.com")}],
    )
    res = cf_access.apply_sync(fake.client())
    assert res["applied"] is True and res["other_policies_emails"] == ["o@example.com", "shared@example.com"]
    writes = [c for c in fake.calls if c[0] != "GET"]
    assert len(writes) == 1
    method, path, body = writes[0]
    assert (method, path) == ("PUT", f"/accounts/{ACCT}/access/apps/{APP_ID}/policies/p1")
    assert body["include"] == _email_rules("ann@example.com", "bo@example.com", "boss@example.com")
    assert body["require"] == [{"geo": {"country_code": "US"}}] and body["precedence"] == 2


def test_apply_noop_when_in_sync(registry):
    fake = FakeCF(policies=[{"id": "p1", "name": MANAGED_POLICY_NAME, "decision": "allow", "precedence": 1,
                             "include": _email_rules("ann@example.com", "bo@example.com", "boss@example.com")}])
    res = cf_access.apply_sync(fake.client())
    assert res["applied"] is False and res["in_sync"] is True
    assert all(m == "GET" for m, _, _ in fake.calls)


def test_refuses_empty_desired(tmp_path, monkeypatch):
    import jobwright.users as users_mod

    monkeypatch.delenv("JOBWRIGHT_ADMIN_EMAILS", raising=False)
    monkeypatch.setenv("JOBWRIGHT_CF_AUD", "aud-tag")
    _write_registry(users_mod.USERS_ROOT, [], [{"user_id": "ann", "emails": []}])
    fake = FakeCF(policies=[{"id": "p1", "name": MANAGED_POLICY_NAME, "decision": "allow", "precedence": 1,
                             "include": _email_rules("ann@example.com")}])
    with pytest.raises(CFAccessError, match="Refusing"):
        cf_access.apply_sync(fake.client())
    assert all(m == "GET" for m, _, _ in fake.calls)


def test_update_refuses_unmanaged_policy():
    with pytest.raises(CFAccessError, match="Refusing to modify"):
        FakeCF().client().update_policy({"id": APP_ID}, {"id": "p0", "name": "owner"}, [])


def test_403_explains_missing_permission(registry):
    with pytest.raises(CFAccessError) as exc:
        cf_access.plan_sync(FakeCF(status=403).client())
    assert "HTTP 403" in str(exc.value) and "Access: Apps and Policies > Edit" in str(exc.value)


def test_account_id_from_cert_ignores_token(tmp_path):
    payload = base64.b64encode(json.dumps({"zoneID": "z", "accountID": "fromcert", "apiToken": "secret"}).encode())
    cert = tmp_path / "cert.pem"
    cert.write_text(f"-----BEGIN ARGO TUNNEL TOKEN-----\n{payload.decode()}\n-----END ARGO TUNNEL TOKEN-----\n")
    assert cf_access.account_id_from_cert(cert) == "fromcert"
    assert cf_access.account_id_from_cert(tmp_path / "missing.pem") == ""


def test_auto_sync_skipped_without_token():
    assert cf_access.auto_sync() is None
    assert cf_access.status()["configured"] is False


def test_auto_sync_reports_errors(monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

    def boom(client=None):
        raise CFAccessError("nope")

    monkeypatch.setattr(cf_access, "apply_sync", boom)
    assert cf_access.auto_sync() == {"ok": False, "error": "nope"}


def test_web_access_routes_admin_only(api_env, monkeypatch):
    client, h, _ = api_env
    boss, bo = h("boss@example.com"), h("bo@example.com")
    assert client.get("/api/admin/access", headers=bo).status_code == 403
    assert client.post("/api/admin/access/sync", headers=bo).status_code == 403
    assert client.get("/api/admin/access", headers=boss).json()["configured"] is False
    assert client.post("/api/admin/access/sync", headers=boss).status_code == 400

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")
    monkeypatch.setattr(cf_access, "plan_sync", lambda client=None: {"configured": True, "add": ["x@example.com"]})
    monkeypatch.setattr(cf_access, "apply_sync", lambda client=None: {"applied": True, "add": [], "remove": []})
    assert client.get("/api/admin/access", headers=boss).json()["add"] == ["x@example.com"]
    assert client.post("/api/admin/access/sync", headers=boss).json()["applied"] is True


def test_login_changes_trigger_best_effort_sync(api_env, monkeypatch):
    client, h, _ = api_env
    boss = h("boss@example.com")
    res = client.post("/api/onboarding/profile", json={"name": "Cy", "emails": ["cy@example.com"]}, headers=boss)
    assert res.status_code == 200 and res.json()["access_sync"] is None

    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok")

    def boom(client=None):
        raise CFAccessError("HTTP 403")

    monkeypatch.setattr(cf_access, "apply_sync", boom)
    uid = res.json()["user_id"]
    res = client.patch(f"/api/admin/users/{uid}", json={"emails": ["cy2@example.com"]}, headers=boss)
    assert res.status_code == 200 and res.json()["access_sync"] == {"ok": False, "error": "HTTP 403"}
    monkeypatch.setattr(cf_access, "apply_sync", lambda client=None: {"applied": True, "add": ["a@x.com"], "remove": []})
    res = client.put("/api/admin/settings", json={"admins": ["boss@example.com", "a@x.com"]}, headers=boss)
    assert res.status_code == 200 and res.json()["access_sync"]["ok"] is True
    res = client.patch(f"/api/admin/users/{uid}", json={"human_gate": True}, headers=boss)
    assert res.json()["access_sync"] is None
