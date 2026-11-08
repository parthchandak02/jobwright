"""The applicant's own browser: a fresh persistent Playwright profile per user.

``<user dir>/apply-browser/profile`` holds only cookies created while applying
for that person. It is never copied from the operator's Chrome profile and
never shared between profiles. Every request is checked against a domain
allowlist (the job's ATS host + its asset/CDN hosts + CAPTCHA widget hosts);
everything else is aborted. In a dry run every non-GET request is aborted as
well, so nothing can be submitted and no account can be created even if a
button is misread.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from jobwright import config

log = logging.getLogger(__name__)

# Hosts an ATS family's pages load from (form, scripts, uploads).
ATS_HOSTS: dict[str, tuple[str, ...]] = {
    "greenhouse": ("greenhouse.io", "grnhse.io", "greenhouse-assets.s3.amazonaws.com"),
    "lever": ("lever.co", "lever-client-assets.s3.amazonaws.com"),
    "ashby": ("ashbyhq.com", "ashbyprd.com"),
    "workday": ("myworkdayjobs.com", "myworkday.com", "workday.com", "wd1.myworkdaysite.com"),
    "smartrecruiters": ("smartrecruiters.com",),
    "workable": ("workable.com",),
}
# Generic static asset hosts most career sites use.
CDN_HOSTS = (
    "fonts.googleapis.com", "fonts.gstatic.com", "cdnjs.cloudflare.com", "cdn.jsdelivr.net", "unpkg.com",
    "cloudfront.net", "ajax.googleapis.com", "use.typekit.net", "p.typekit.net",
)
# CAPTCHA widgets must load so a human can solve them (we never solve them).
CAPTCHA_HOSTS = ("www.google.com", "www.recaptcha.net", "www.gstatic.com", "hcaptcha.com",
                 "challenges.cloudflare.com")
_SAFE_SCHEMES = ("data", "blob", "about")
_SECOND_LEVEL = {"co.uk", "com.au", "co.in", "co.nz", "com.br", "co.jp", "com.sg"}


def registrable_domain(host: str) -> str:
    parts = (host or "").lower().strip(".").split(".")
    if len(parts) <= 2 or all(p.isdigit() for p in parts):
        return ".".join(parts)
    if ".".join(parts[-2:]) in _SECOND_LEVEL:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def allowed_hosts_for(url: str, ats: str | None = None, extra: tuple[str, ...] = ()) -> set[str]:
    host = (urlparse(url).hostname or "").lower()
    allowed = {host, registrable_domain(host)} if host else set()
    if ats:
        allowed.update(ATS_HOSTS.get(ats, ()))
    allowed.update(CDN_HOSTS)
    allowed.update(CAPTCHA_HOSTS)
    allowed.update(h.strip().lower() for h in os.environ.get("JOBWRIGHT_APPLY_EXTRA_HOSTS", "").split(",")
                   if h.strip())
    allowed.update(extra)
    allowed.discard("")
    return allowed


def host_allowed(url: str, allowed: set[str]) -> bool:
    parsed = urlparse(url)
    if parsed.scheme in _SAFE_SCHEMES:
        return True
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    return any(host == a or host.endswith("." + a) for a in allowed)


def profile_dir_for_user() -> Path:
    d = Path(config.APP_DIR) / "apply-browser" / "profile"
    d.mkdir(parents=True, exist_ok=True)
    for p in (d.parent, d):
        try:
            p.chmod(0o700)
        except OSError:
            pass
    return d


@dataclass
class BrowserSession:
    allowed_hosts: set[str]
    dry_run: bool = True
    headless: bool = True
    user_data_dir: Path | None = None
    viewport: tuple[int, int] = (1280, 900)
    blocked: list[str] = field(default_factory=list)
    _pw: Any = None
    context: Any = None
    _page: Any = None

    def start(self) -> "BrowserSession":
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        data_dir = self.user_data_dir or profile_dir_for_user()
        self.context = self._pw.chromium.launch_persistent_context(
            str(data_dir),
            headless=self.headless,
            viewport={"width": self.viewport[0], "height": self.viewport[1]},
            accept_downloads=False,
            permissions=[],
            args=["--disable-notifications", "--deny-permission-prompts", "--disable-save-password-bubble"],
        )
        self.context.route("**/*", self._route)
        self.context.on("page", self._on_page)
        self._page = self.context.pages[0] if self.context.pages else self.context.new_page()
        return self

    def _on_page(self, page) -> None:
        self._page = page

    def _route(self, route) -> None:
        req = route.request
        url = req.url
        if not host_allowed(url, self.allowed_hosts):
            self.blocked.append(f"host {url[:200]}")
            route.abort("blockedbyclient")
            return
        if self.dry_run and req.method not in ("GET", "HEAD", "OPTIONS"):
            self.blocked.append(f"dry-run {req.method} {url[:200]}")
            route.abort("blockedbyclient")
            return
        route.continue_()

    @property
    def page(self):
        if self._page is not None and self._page.is_closed() and self.context.pages:
            self._page = self.context.pages[-1]
        return self._page

    def goto(self, url: str) -> None:
        if not host_allowed(url, self.allowed_hosts):
            raise PermissionError(f"{urlparse(url).hostname} is not on this application's allowlist")
        self.page.goto(url, wait_until="domcontentloaded", timeout=45_000)

    def screenshot(self, path: Path, full_page: bool = False) -> str | None:
        try:
            self.page.screenshot(path=str(path), full_page=full_page, timeout=15_000)
            try:
                path.chmod(0o600)
            except OSError:
                pass
            return path.name
        except Exception as exc:  # noqa: BLE001
            log.warning("screenshot %s failed: %s", path.name, exc)
            return None

    def close(self) -> None:
        for closer in (getattr(self.context, "close", None), getattr(self._pw, "stop", None)):
            if closer:
                try:
                    closer()
                except Exception:  # noqa: BLE001
                    pass
        self.context = None
        self._pw = None
