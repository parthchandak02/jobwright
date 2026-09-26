"""
Unified LLM client for jobwright.

Auto-detects provider from environment (first match wins):
  FIREWORKS_API_KEY -> Fireworks AI (default: glm-5p3-flash)
  GEMINI_API_KEY    -> Google Gemini (default: gemini-3.7-flash)
  OPENAI_API_KEY    -> OpenAI (default: gpt-4o-mini)
  LLM_URL           -> Local llama.cpp / Ollama compatible endpoint

LLM_MODEL env var overrides the model name for the active provider.
"""

import contextvars
import logging
import os
import threading
import time
from collections import defaultdict
from contextlib import contextmanager

import httpx

log = logging.getLogger(__name__)

_FIREWORKS_BASE = "https://api.fireworks.ai/inference/v1"
_FIREWORKS_DEFAULT_MODEL = "accounts/fireworks/models/glm-5p3-flash"
_FIREWORKS_SHORT_MODELS = {
    "deepseek-v4-flash-0731": _FIREWORKS_DEFAULT_MODEL,
    "deepseek-v4-flash": _FIREWORKS_DEFAULT_MODEL,
    "deepseek-v4-pro-0813": "accounts/fireworks/models/deepseek-v4-pro-0813",
    "deepseek-v4-pro": "accounts/fireworks/models/deepseek-v4-pro",
    "glm-5p3-flash": "accounts/fireworks/models/glm-5p3-flash",
    "glm-5.3-flash": "accounts/fireworks/models/glm-5p3-flash",
    "glm-5.3": "accounts/fireworks/models/glm-5p3-flash",
    "gpt-oss-120b": "accounts/fireworks/models/gpt-oss-120b",
    "minimax-m3": "accounts/fireworks/models/minimax-m3",
}

# ---------------------------------------------------------------------------
# Provider detection
# ---------------------------------------------------------------------------

def _resolve_fireworks_model(model_override: str) -> str:
    """Map LLM_MODEL to a Fireworks serverless model id."""
    if not model_override:
        return _FIREWORKS_DEFAULT_MODEL
    if model_override.startswith("accounts/fireworks/models/"):
        return model_override
    if model_override in _FIREWORKS_SHORT_MODELS:
        return _FIREWORKS_SHORT_MODELS[model_override]
    if model_override.startswith(("gemini-", "gpt-4", "gpt-3")):
        log.warning(
            "LLM_MODEL=%s is not a Fireworks model; using %s",
            model_override,
            _FIREWORKS_DEFAULT_MODEL,
        )
        return _FIREWORKS_DEFAULT_MODEL
    return model_override


def _detect_provider(model_override: str | None = None) -> tuple[str, str, str]:
    """Return (base_url, model, api_key) based on environment variables.

    Reads env at call time (not module import time) so that load_env() called
    in _bootstrap() is always visible here.

    When LLM_MODEL names a provider-specific model (e.g. gemini-*), route to that
    provider if its API key is set — avoids Fireworks winning over an explicit
    Gemini model in per-user or brief-script env.
    """
    fireworks_key = os.environ.get("FIREWORKS_API_KEY", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    local_url = os.environ.get("LLM_URL", "")
    if model_override is None:
        model_override = os.environ.get("LLM_MODEL", "")

    if model_override.startswith("gemini-") and gemini_key and not local_url:
        return (
            "https://generativelanguage.googleapis.com/v1beta/openai",
            model_override,
            gemini_key,
        )

    if (
        model_override.startswith("accounts/fireworks/models/")
        or model_override in _FIREWORKS_SHORT_MODELS
    ) and fireworks_key and not local_url:
        return (
            _FIREWORKS_BASE,
            _resolve_fireworks_model(model_override),
            fireworks_key,
        )

    if model_override.startswith(("gpt-4", "gpt-3", "o1", "o3", "o4")) and openai_key and not local_url:
        return (
            "https://api.openai.com/v1",
            model_override,
            openai_key,
        )

    if fireworks_key and not local_url:
        return (
            _FIREWORKS_BASE,
            _resolve_fireworks_model(model_override),
            fireworks_key,
        )

    if gemini_key and not local_url:
        return (
            "https://generativelanguage.googleapis.com/v1beta/openai",
            model_override or "gemini-3.7-flash",
            gemini_key,
        )

    if openai_key and not local_url:
        return (
            "https://api.openai.com/v1",
            model_override or "gpt-4o-mini",
            openai_key,
        )

    if local_url:
        return (
            local_url.rstrip("/"),
            model_override or "local-model",
            os.environ.get("LLM_API_KEY", ""),
        )

    raise RuntimeError(
        "No LLM provider configured. "
        "Set FIREWORKS_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, or LLM_URL in your environment."
    )


# ---------------------------------------------------------------------------
# Token usage ledger
#
# Every successful call adds its token counts to an in-process ledger keyed by
# (purpose, provider, model). ``llm_purpose("score")`` tags calls made inside a
# block; pipeline stages flush the ledger to the llm_usage table so spend per
# run and per purpose is visible. Costs are only computed when a per-model price
# is configured (JOBWRIGHT_LLM_PRICES='{"model": [in_per_1M, out_per_1M]}').
# ---------------------------------------------------------------------------

_purpose: contextvars.ContextVar[str] = contextvars.ContextVar("llm_purpose", default="other")
_usage_lock = threading.Lock()
_usage: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0])


@contextmanager
def llm_purpose(name: str):
    token = _purpose.set(name)
    try:
        yield
    finally:
        _purpose.reset(token)


def record_usage(provider: str, model: str, usage: dict | None) -> None:
    if not usage:
        return
    prompt = int(usage.get("prompt_tokens") or usage.get("promptTokenCount") or 0)
    completion = int(usage.get("completion_tokens") or usage.get("candidatesTokenCount") or 0)
    details = usage.get("prompt_tokens_details") or {}
    cached = int(details.get("cached_tokens") or usage.get("cachedContentTokenCount") or 0)
    with _usage_lock:
        row = _usage[(_purpose.get(), provider, model)]
        row[0] += prompt
        row[1] += completion
        row[2] += cached
        row[3] += 1


def usage_snapshot(reset: bool = False) -> list[dict]:
    """Aggregated usage since the last reset: purpose/provider/model/tokens/calls."""
    with _usage_lock:
        rows = [
            {"purpose": k[0], "provider": k[1], "model": k[2], "prompt_tokens": v[0],
             "completion_tokens": v[1], "cached_tokens": v[2], "calls": v[3]}
            for k, v in _usage.items()
        ]
        if reset:
            _usage.clear()
    return rows


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    import json

    raw = os.environ.get("JOBWRIGHT_LLM_PRICES", "").strip()
    if not raw:
        return None
    try:
        prices = json.loads(raw)
    except ValueError:
        return None
    price = prices.get(model) or prices.get(model.rsplit("/", 1)[-1])
    if not price:
        return None
    return round(prompt_tokens / 1e6 * float(price[0]) + completion_tokens / 1e6 * float(price[1]), 6)


def flush_usage(conn, run_id: str | None = None) -> int:
    """Write the aggregated ledger to llm_usage and reset it."""
    from datetime import datetime, timezone

    rows = usage_snapshot(reset=True)
    now = datetime.now(timezone.utc).isoformat()
    for r in rows:
        conn.execute(
            "INSERT INTO llm_usage (at, run_id, purpose, provider, model, prompt_tokens, "
            "completion_tokens, cached_tokens, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (now, run_id, r["purpose"], r["provider"], r["model"], r["prompt_tokens"],
             r["completion_tokens"], r["cached_tokens"],
             estimate_cost(r["model"], r["prompt_tokens"], r["completion_tokens"])),
        )
    conn.commit()
    return len(rows)


def _provider_name(base_url: str) -> str:
    if "fireworks" in base_url:
        return "fireworks"
    if "generativelanguage" in base_url:
        return "gemini"
    if "openai.com" in base_url:
        return "openai"
    return "local"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

_MAX_RETRIES = 5
_MAX_RETRY_AFTER = 60  # never sleep longer than this on a provider's Retry-After
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
_EMPTY_RETRIES = 2  # extra in-place retries when a provider returns empty content
_TIMEOUT = 120  # seconds

# Base wait on first 429/503 (doubles each retry, caps at 60s).
# Gemini free tier is 15 RPM = 4s minimum between requests; 10s gives headroom.
_RATE_LIMIT_BASE_WAIT = 10


_GEMINI_COMPAT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"
_GEMINI_NATIVE_BASE = "https://generativelanguage.googleapis.com/v1beta"
_VALID_THINKING_LEVELS = frozenset({"minimal", "low", "medium", "high"})


def _gemini_thinking_level() -> str:
    """GEMINI_THINKING_LEVEL env (default low). Used for Gemini 3.x thinking."""
    level = (os.environ.get("GEMINI_THINKING_LEVEL") or "low").strip().lower()
    if level not in _VALID_THINKING_LEVELS:
        log.warning("Invalid GEMINI_THINKING_LEVEL=%s; using low", level)
        return "low"
    return level


def _is_gemini3_model(model: str) -> bool:
    return model.startswith("gemini-3")


class LLMClient:
    """Thin LLM client supporting OpenAI-compatible and native Gemini endpoints.

    For Gemini keys, starts on the OpenAI-compat layer. On a 403 (which
    happens with preview/experimental models not exposed via compat), it
    automatically switches to the native generateContent API and stays there
    for the lifetime of the process.
    """

    def __init__(self, base_url: str, model: str, api_key: str) -> None:
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
        self._client = httpx.Client(timeout=_TIMEOUT)
        # True once we've confirmed the native Gemini API works for this model
        self._use_native_gemini: bool = False
        self._is_gemini: bool = base_url.startswith(_GEMINI_COMPAT_BASE)
        # Lazily-built cross-provider fallback (e.g. Fireworks -> Gemini on empty).
        self._fallback: LLMClient | None = None
        self._is_fallback: bool = False
        self._schema_unsupported: bool = False

    # -- Native Gemini API --------------------------------------------------

    def _chat_native_gemini(
        self,
        messages: list[dict],
        temperature: float | None,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        """Call the native Gemini generateContent API.

        Used automatically when the OpenAI-compat endpoint returns 403,
        which happens for preview/experimental models not exposed via compat.

        Converts OpenAI-style messages to Gemini's contents/systemInstruction
        format transparently.
        """
        contents: list[dict] = []
        system_parts: list[dict] = []

        for msg in messages:
            role = msg["role"]
            text = msg.get("content", "")
            if role == "system":
                system_parts.append({"text": text})
            elif role == "user":
                contents.append({"role": "user", "parts": [{"text": text}]})
            elif role == "assistant":
                # Gemini uses "model" instead of "assistant"
                contents.append({"role": "model", "parts": [{"text": text}]})

        # Gemini 3.x: low temperature can cause looping; omit when unset sentinel.
        generation_config: dict = {
            "maxOutputTokens": max_tokens,
        }
        if temperature is not None:
            generation_config["temperature"] = temperature
        if json_mode:
            generation_config["responseMimeType"] = "application/json"
        if _is_gemini3_model(self.model):
            generation_config["thinkingConfig"] = {
                "thinkingLevel": _gemini_thinking_level(),
            }

        payload: dict = {
            "contents": contents,
            "generationConfig": generation_config,
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": system_parts}

        url = f"{_GEMINI_NATIVE_BASE}/models/{self.model}:generateContent"
        resp = self._client.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json", "x-goog-api-key": self.api_key},
        )
        resp.raise_for_status()
        data = resp.json()
        record_usage("gemini", self.model, data.get("usageMetadata"))
        candidate = (data.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or [{}]
        text = parts[0].get("text")
        if not (text or "").strip():
            log.warning(
                "Empty native Gemini content (finishReason=%s)",
                candidate.get("finishReason"),
            )
            raise _EmptyLLMResponse("Empty LLM response")
        return text

    # -- OpenAI-compat API --------------------------------------------------

    def _chat_compat(
        self,
        messages: list[dict],
        temperature: float | None,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str:
        """Call the OpenAI-compatible endpoint."""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            payload["temperature"] = temperature
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        # OpenAI-compat maps reasoning_effort -> Gemini thinking_level.
        if self._is_gemini and _is_gemini3_model(self.model):
            payload["reasoning_effort"] = _gemini_thinking_level()

        resp = self._client.post(
            f"{self.base_url}/chat/completions",
            json=payload,
            headers=headers,
        )

        # 403/404 on Gemini compat = use native generateContent API instead.
        if resp.status_code in (403, 404) and self._is_gemini:
            raise _GeminiCompatForbidden(resp)

        return self._handle_compat_response(resp)

    def _handle_compat_response(self, resp: httpx.Response) -> str:
        resp.raise_for_status()
        data = resp.json()
        record_usage(_provider_name(self.base_url), self.model, data.get("usage"))
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        if not (content or "").strip():
            # Diagnose empty completions: reasoning models can burn the whole
            # token budget on hidden thinking, or json_mode can truncate.
            finish = choice.get("finish_reason")
            usage = data.get("usage")
            has_reasoning = bool((message.get("reasoning_content") or "").strip())
            log.warning(
                "Empty LLM content (finish_reason=%s, usage=%s, reasoning_content=%s)",
                finish, usage, "present" if has_reasoning else "none",
            )
            raise _EmptyLLMResponse("Empty LLM response")
        return content

    # -- public API ---------------------------------------------------------

    def chat(
        self,
        messages: list[dict],
        temperature: float | None = 0.0,
        max_tokens: int = 4096,
        json_mode: bool = False,
    ) -> str:
        """Send a chat completion request and return the assistant message text.

        When json_mode=True and the provider is Gemini, uses the native
        generateContent API with responseMimeType=application/json so
        structured outputs are complete and parseable.

        For Gemini 3.x, temperature defaults are left to the API (forcing 0.0
        can cause looping). Callers that pass an explicit temperature still win.
        """
        # JSON on Gemini goes to the native API for this call only (responseMimeType);
        # plain-text calls keep using compat unless compat itself was rejected.
        native_this_call = self._use_native_gemini or (json_mode and self._is_gemini)
        # Google warns low temperature on Gemini 3.x can degrade output.
        if self._is_gemini and _is_gemini3_model(self.model) and temperature == 0.0:
            temperature = None
        # Qwen3 optimization: prepend /no_think to skip chain-of-thought
        # reasoning, saving tokens on structured extraction tasks.
        if "qwen" in self.model.lower() and messages:
            first = messages[0]
            if first.get("role") == "user" and not first["content"].startswith("/no_think"):
                messages = [{"role": first["role"], "content": f"/no_think\n{first['content']}"}] + messages[1:]

        empty_attempts = 0
        for attempt in range(_MAX_RETRIES):
            try:
                if native_this_call:
                    return self._chat_native_gemini(
                        messages, temperature, max_tokens, json_mode=json_mode
                    )

                return self._chat_compat(messages, temperature, max_tokens, json_mode=json_mode)

            except _EmptyLLMResponse:
                empty_attempts += 1
                if empty_attempts <= _EMPTY_RETRIES:
                    log.warning(
                        "Empty response from %s; retrying (%d/%d)",
                        self.model, empty_attempts, _EMPTY_RETRIES,
                    )
                    continue
                fallback_text = self._try_fallback(
                    messages, temperature, max_tokens, json_mode=json_mode
                )
                if fallback_text is not None:
                    return fallback_text
                raise RuntimeError(
                    f"Empty LLM response from {self.model} after {empty_attempts} attempts"
                )

            except _GeminiCompatForbidden:
                # Model not available on OpenAI-compat layer — switch to native.
                log.warning(
                    "Gemini compat endpoint returned 403 for model '%s'. "
                    "Switching to native generateContent API. "
                    "(Preview/experimental models are often compat-only on native.)",
                    self.model,
                )
                self._use_native_gemini = True
                # Retry immediately with native — don't count as a rate-limit wait
                try:
                    return self._chat_native_gemini(
                        messages, temperature, max_tokens, json_mode=json_mode
                    )
                except httpx.HTTPStatusError as native_exc:
                    raise RuntimeError(
                        f"Both Gemini endpoints failed. Compat: 403 Forbidden. "
                        f"Native: {native_exc.response.status_code} — "
                        f"{native_exc.response.text[:200]}"
                    ) from native_exc

            except httpx.HTTPStatusError as exc:
                resp = exc.response
                if resp.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES - 1:
                    wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), _MAX_RETRY_AFTER)
                    retry_after = (
                        resp.headers.get("Retry-After")
                        or resp.headers.get("X-RateLimit-Reset-Requests")
                    )
                    if retry_after:
                        try:
                            wait = min(max(float(retry_after), 1.0), _MAX_RETRY_AFTER)
                        except (ValueError, TypeError):
                            pass
                    log.warning(
                        "LLM HTTP %s from %s. Waiting %ds before retry %d/%d.",
                        resp.status_code, self.model, wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise

            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt < _MAX_RETRIES - 1:
                    wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), _MAX_RETRY_AFTER)
                    log.warning(
                        "LLM transport error (%s), retrying in %ds (attempt %d/%d)",
                        type(exc).__name__, wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise

        raise RuntimeError("LLM request failed after all retries")

    def _try_fallback(
        self,
        messages: list[dict],
        temperature: float | None,
        max_tokens: int,
        json_mode: bool = False,
    ) -> str | None:
        """Retry once on a secondary provider when the primary returns empty.

        Only triggers Fireworks/OpenAI -> Gemini today (the documented fallback).
        Returns the response text, or None if no usable fallback is configured.
        """
        if self._is_fallback or self._is_gemini:
            return None  # already Gemini, or we are the fallback client itself
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        if not gemini_key:
            return None
        if self._fallback is None:
            model = os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-3.7-flash")
            log.warning(
                "Primary provider (%s) returned empty; falling back to Gemini model '%s'",
                self.model, model,
            )
            fb = LLMClient(_GEMINI_COMPAT_BASE, model, gemini_key)
            fb._is_fallback = True
            self._fallback = fb
        try:
            return self._fallback.chat(
                messages, temperature=temperature, max_tokens=max_tokens, json_mode=json_mode
            )
        except Exception as exc:  # noqa: BLE001 - fallback is best-effort
            log.error("Gemini fallback also failed: %s", exc)
            return None

    def chat_structured(
        self,
        messages: list[dict],
        schema: dict,
        *,
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> str:
        """Structured output: json_schema when the provider supports it, else json_object.

        ``schema`` is an OpenAI-style ``{"name", "strict", "schema"}`` object.
        One attempt per call; callers own retries. 429/5xx propagate as
        httpx.HTTPStatusError, empty content raises _EmptyLLMResponse.
        """
        if not self._is_gemini and not self._schema_unsupported:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            payload = {
                "model": self.model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": {"type": "json_schema", "json_schema": schema},
            }
            resp = self._client.post(f"{self.base_url}/chat/completions", json=payload, headers=headers)
            if resp.status_code in (400, 404, 422):
                log.info("Provider rejected json_schema (HTTP %s); using json_object", resp.status_code)
                self._schema_unsupported = True
            else:
                return self._handle_compat_response(resp)
        return self.chat(messages, temperature=temperature, max_tokens=max_tokens, json_mode=True)

    def ask(self, prompt: str, **kwargs) -> str:
        """Convenience: single user prompt -> assistant response."""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)

    def close(self) -> None:
        self._client.close()
        if self._fallback is not None:
            self._fallback.close()


class _GeminiCompatForbidden(Exception):
    """Sentinel: Gemini OpenAI-compat returned 403. Switch to native API."""
    def __init__(self, response: httpx.Response) -> None:
        self.response = response
        super().__init__(f"Gemini compat 403: {response.text[:200]}")


class _EmptyLLMResponse(RuntimeError):
    """The provider returned a 2xx with empty/blank content (retryable)."""


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_instance: LLMClient | None = None
_instance_lock = threading.Lock()
_named: dict[str, LLMClient] = {}


def reset_client() -> None:
    """Drop cached clients so the next get_client() re-reads env."""
    global _instance
    with _instance_lock:
        if _instance is not None:
            _instance.close()
            _instance = None
        for client in _named.values():
            client.close()
        _named.clear()


def get_client() -> LLMClient:
    """Return (or create) the module-level LLMClient singleton (thread-safe)."""
    global _instance
    if _instance is not None:
        return _instance
    with _instance_lock:
        if _instance is None:
            base_url, model, api_key = _detect_provider()
            log.info("LLM provider: %s  model: %s", base_url, model)
            _instance = LLMClient(base_url, model, api_key)
        return _instance


def get_client_for_model(model: str) -> LLMClient:
    """Client for an explicit model id (e.g. the scoring escalation tier).

    Resolves the provider from the model name with the same rules as LLM_MODEL
    and caches one client per model.
    """
    with _instance_lock:
        client = _named.get(model)
        if client is not None:
            return client
        base_url, resolved, api_key = _detect_provider(model)
        client = LLMClient(base_url, resolved, api_key)
        _named[model] = client
        log.info("LLM client for %s: %s %s", model, base_url, resolved)
        return client
