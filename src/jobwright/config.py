"""jobwright configuration: paths, platform detection, user data."""

import os
import platform
import shutil
from pathlib import Path

# Active multi-profile user id (None = legacy single-user ~/.jobwright)
ACTIVE_USER_ID: str | None = None

# User data directory — all user-specific files live here
APP_DIR = Path(os.environ.get("JOBWRIGHT_DIR", Path.home() / ".jobwright"))

# Core paths (reassigned by set_app_dir / set_active_user)
DB_PATH = APP_DIR / "jobwright.db"
PROFILE_PATH = APP_DIR / "profile.json"
RESUME_PATH = APP_DIR / "resume.txt"
RESUME_PDF_PATH = APP_DIR / "resume.pdf"
SEARCH_CONFIG_PATH = APP_DIR / "searches.yaml"
ENV_PATH = APP_DIR / ".env"
CONNECTIONS_PATH = APP_DIR / "connections.csv"
TARGETS_PATH = APP_DIR / "target_companies.yaml"

# Generated output
TAILORED_DIR = APP_DIR / "tailored_resumes"
COVER_LETTER_DIR = APP_DIR / "cover_letters"
LOG_DIR = APP_DIR / "logs"
NETWORK_DIR = APP_DIR / "network"

# Chrome worker isolation
CHROME_WORKER_DIR = APP_DIR / "chrome-workers"
APPLY_WORKER_DIR = APP_DIR / "apply-workers"

# Package-shipped config (YAML registries)
PACKAGE_DIR = Path(__file__).parent
CONFIG_DIR = PACKAGE_DIR / "config"


def set_app_dir(path: Path | str) -> Path:
    """Point all path constants at a new JOBWRIGHT_DIR.

    Call before bootstrap so DB/profile/env resolve to the right user.
    Always read paths via `jobwright.config.DB_PATH` (not a stale import alias).
    """
    global APP_DIR, DB_PATH, PROFILE_PATH, RESUME_PATH, RESUME_PDF_PATH
    global SEARCH_CONFIG_PATH, ENV_PATH, CONNECTIONS_PATH, TARGETS_PATH
    global TAILORED_DIR, COVER_LETTER_DIR, LOG_DIR, NETWORK_DIR
    global CHROME_WORKER_DIR, APPLY_WORKER_DIR

    app_dir = Path(path).expanduser().resolve()
    os.environ["JOBWRIGHT_DIR"] = str(app_dir)

    APP_DIR = app_dir
    DB_PATH = APP_DIR / "jobwright.db"
    PROFILE_PATH = APP_DIR / "profile.json"
    RESUME_PATH = APP_DIR / "resume.txt"
    RESUME_PDF_PATH = APP_DIR / "resume.pdf"
    SEARCH_CONFIG_PATH = APP_DIR / "searches.yaml"
    ENV_PATH = APP_DIR / ".env"
    CONNECTIONS_PATH = APP_DIR / "connections.csv"
    TARGETS_PATH = APP_DIR / "target_companies.yaml"
    TAILORED_DIR = APP_DIR / "tailored_resumes"
    COVER_LETTER_DIR = APP_DIR / "cover_letters"
    LOG_DIR = APP_DIR / "logs"
    NETWORK_DIR = APP_DIR / "network"
    CHROME_WORKER_DIR = APP_DIR / "chrome-workers"
    APPLY_WORKER_DIR = APP_DIR / "apply-workers"
    return APP_DIR


def set_active_user(user_id: str) -> Path:
    """Resolve a registry user and switch APP_DIR to their data directory."""
    global ACTIVE_USER_ID
    from jobwright.users import get_user

    user = get_user(user_id)
    if user is None:
        raise SystemExit(
            f"Unknown user '{user_id}'. Run: jobwright users list\n"
            f"Or add one: jobwright users add {user_id}"
        )
    ACTIVE_USER_ID = user.user_id
    return set_app_dir(user.resolve_data_dir())


def get_active_user_id() -> str | None:
    return ACTIVE_USER_ID


def get_chrome_path() -> str:
    """Auto-detect Chrome/Chromium executable path, cross-platform.

    Override with CHROME_PATH environment variable.
    """
    env_path = os.environ.get("CHROME_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    system = platform.system()

    if system == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    else:  # Linux
        candidates = []
        for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

    for c in candidates:
        if c and c.exists():
            return str(c)

    # Fall back to PATH search
    for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            return found

    raise FileNotFoundError(
        "Chrome/Chromium not found. Install Chrome or set CHROME_PATH environment variable."
    )


def get_chrome_user_data() -> Path:
    """Default Chrome user data directory, cross-platform."""
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    else:
        return Path.home() / ".config" / "google-chrome"


def ensure_dirs():
    """Create all required directories."""
    for d in [
        APP_DIR, TAILORED_DIR, COVER_LETTER_DIR, LOG_DIR, NETWORK_DIR,
        CHROME_WORKER_DIR, APPLY_WORKER_DIR,
    ]:
        d.mkdir(parents=True, exist_ok=True)
    try:
        APP_DIR.chmod(0o700)
    except OSError:
        pass


def write_private_text(path: Path, content: str) -> None:
    """Write a file with owner-only permissions (secrets, MCP configs)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def get_agent_provider() -> str:
    """Return configured stage-6 agent provider name."""
    load_env()
    return os.environ.get("AGENT_PROVIDER", "cursor-sdk").lower()


def has_apply_agent() -> bool:
    """Check if stage-6 agent backend is available."""
    load_env()
    provider = get_agent_provider()
    if provider == "cursor-sdk":
        return bool(os.environ.get("CURSOR_API_KEY"))
    if provider == "cursor-cli":
        return shutil.which("agent") is not None
    if provider == "claude":
        return shutil.which("claude") is not None
    return False


def load_profile() -> dict:
    """Load user profile from ~/.jobwright/profile.json."""
    import json
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"Profile not found at {PROFILE_PATH}. Run `jobwright init` first."
        )
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def load_search_config() -> dict:
    """Load search configuration from ~/.jobwright/searches.yaml."""
    import yaml
    if not SEARCH_CONFIG_PATH.exists():
        # Fall back to package-shipped example
        example = CONFIG_DIR / "searches.example.yaml"
        if example.exists():
            return yaml.safe_load(example.read_text(encoding="utf-8"))
        return {}
    return yaml.safe_load(SEARCH_CONFIG_PATH.read_text(encoding="utf-8"))


def load_location_filters(search_cfg: dict | None = None) -> tuple[list[str], list[str]]:
    """Return (accept_patterns, reject_patterns) from search config.

    Supports both legacy root keys (location_accept, location_reject_non_remote)
    and nested location.accept_patterns / location.reject_patterns.
    """
    if search_cfg is None:
        search_cfg = load_search_config()
    location_cfg = search_cfg.get("location", {}) or {}
    accept = search_cfg.get("location_accept") or location_cfg.get("accept_patterns") or []
    reject = search_cfg.get("location_reject_non_remote") or location_cfg.get("reject_patterns") or []
    return accept, reject


def load_sites_config() -> dict:
    """Load sites.yaml configuration (sites list, manual_ats, blocked, etc.)."""
    import yaml
    path = CONFIG_DIR / "sites.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def is_manual_ats(url: str | None) -> bool:
    """Check if a URL routes through an ATS that requires manual application."""
    if not url:
        return False
    sites_cfg = load_sites_config()
    domains = sites_cfg.get("manual_ats", [])
    url_lower = url.lower()
    return any(domain in url_lower for domain in domains)


def load_blocked_sites() -> tuple[set[str], list[str]]:
    """Load blocked sites and URL patterns from sites.yaml.

    Returns:
        (blocked_site_names, blocked_url_patterns)
    """
    cfg = load_sites_config()
    blocked = cfg.get("blocked", {})
    sites = set(blocked.get("sites", []))
    patterns = blocked.get("url_patterns", [])
    return sites, patterns


def load_blocked_sso() -> list[str]:
    """Load blocked SSO domains from sites.yaml."""
    cfg = load_sites_config()
    return cfg.get("blocked_sso", [])


def load_base_urls() -> dict[str, str | None]:
    """Load site base URLs for URL resolution from sites.yaml."""
    cfg = load_sites_config()
    return cfg.get("base_urls", {})


# ---------------------------------------------------------------------------
# Default values — referenced across modules instead of magic numbers
# ---------------------------------------------------------------------------

DEFAULTS = {
    "min_score": 7,
    "max_apply_attempts": 3,
    "max_tailor_attempts": 5,
    "poll_interval": 60,
    "apply_timeout": 300,
    "viewport": "1280x900",
}


def global_env_path() -> Path:
    """Resolve the single canonical .env that holds API keys and shared config.

    Order:
      1. JOBWRIGHT_ENV (explicit override)
      2. repo-root .env (editable install: this file is src/jobwright/config.py)
      3. ~/.jobwright/.env (home-global fallback)

    API keys are NOT per-user. Per-user data dirs hold only profile/resume/
    searches/db; secrets live in one place.
    """
    override = os.environ.get("JOBWRIGHT_ENV")
    if override:
        return Path(override).expanduser()
    repo_env = Path(__file__).resolve().parents[2] / ".env"
    if repo_env.exists():
        return repo_env
    return Path.home() / ".jobwright" / ".env"


def load_env():
    """Load environment from the single global .env, then any non-secret per-user overlay.

    Global secrets (GEMINI_API_KEY, CURSOR_API_KEY, ...) come from one .env
    (see global_env_path). A per-user data dir may still carry an optional
    .env with non-secret overrides (e.g. LLM_MODEL, APPLY_DRY_RUN); that is
    layered on top when present. Real shell environment variables win over the
    global file so manual overrides still work.
    """
    from dotenv import load_dotenv

    global_env = global_env_path()
    if global_env.exists():
        load_dotenv(global_env, override=False)

    # Optional per-user overlay for non-secret settings (usually absent).
    if ENV_PATH.exists() and ENV_PATH.resolve() != global_env.resolve():
        load_dotenv(ENV_PATH, override=True)


# ---------------------------------------------------------------------------
# Tier system — feature gating by installed dependencies
# ---------------------------------------------------------------------------

TIER_LABELS = {
    1: "Discovery",
    2: "AI Scoring & Tailoring",
    3: "Full Auto-Apply (Cursor/Hermes)",
}

TIER_COMMANDS: dict[int, list[str]] = {
    1: ["init", "run discover", "run enrich", "status", "dashboard"],
    2: ["run score", "run tailor", "run cover", "run pdf", "run"],
    3: ["apply"],
}


def get_tier() -> int:
    """Detect the current tier based on available dependencies.

    Tier 1 (Discovery):            Python + pip
    Tier 2 (AI Scoring & Tailoring): + LLM API key
    Tier 3 (Full Auto-Apply):       + Agent provider (Cursor SDK/CLI or Claude) + Chrome
    """
    load_env()

    has_llm = any(os.environ.get(k) for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL"))
    if not has_llm:
        return 1

    try:
        get_chrome_path()
        has_chrome = True
    except FileNotFoundError:
        has_chrome = False

    if has_apply_agent() and has_chrome:
        return 3

    return 2


def check_tier(required: int, feature: str) -> None:
    """Raise SystemExit with a clear message if the current tier is too low.

    Args:
        required: Minimum tier needed (1, 2, or 3).
        feature: Human-readable description of the feature being gated.
    """
    current = get_tier()
    if current >= required:
        return

    from rich.console import Console
    _console = Console(stderr=True)

    missing: list[str] = []
    if required >= 2 and not any(os.environ.get(k) for k in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL")):
        missing.append("LLM API key — run [bold]jobwright init[/bold] or set GEMINI_API_KEY")
    if required >= 3:
        provider = get_agent_provider()
        if not has_apply_agent():
            if provider == "cursor-sdk":
                missing.append("CURSOR_API_KEY — set in the repo .env (Cursor Dashboard → Integrations)")
            elif provider == "cursor-cli":
                missing.append("Cursor Agent CLI — install: curl https://cursor.com/install -fsSL | bash")
            else:
                missing.append("Claude Code CLI — install from [bold]https://claude.ai/code[/bold]")
        try:
            get_chrome_path()
        except FileNotFoundError:
            missing.append("Chrome/Chromium — install or set CHROME_PATH")
        if not shutil.which("npx"):
            missing.append("Node.js (npx) — needed for Playwright MCP")

    _console.print(
        f"\n[red]'{feature}' requires {TIER_LABELS.get(required, f'Tier {required}')} (Tier {required}).[/red]\n"
        f"Current tier: {TIER_LABELS.get(current, f'Tier {current}')} (Tier {current})."
    )
    if missing:
        _console.print("\n[yellow]Missing:[/yellow]")
        for m in missing:
            _console.print(f"  - {m}")
    _console.print()
    raise SystemExit(1)
