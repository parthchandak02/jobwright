"""
Unified LLM client for jobwright.

Auto-detects provider from environment (first match wins):
  FIREWORKS_API_KEY -> Fireworks AI (default: deepseek-v4-flash-0731)
  GEMINI_API_KEY    -> Google Gemini (default: gemini-3.7-flash)
  OPENAI_API_KEY    -> OpenAI (default: gpt-4o-mini)
  LLM_URL           -> Local llama.cpp / Ollama compatible endpoint

LLM_MODEL env var overrides the model name for the active provider.
"""

import logging
import os
import time

import httpx

log = logging.getLogger(__name__)

_FIREWORKS_BASE = "https://api.fireworks.ai/inference/v1"
_FIREWORKS_DEFAULT_MODEL = "accounts/fireworks/models/deepseek-v4-flash-0731"
_FIREWORKS_SHORT_MODELS = {
    "deepseek-v4-flash-0731": _FIREWORKS_DEFAULT_MODEL,
    "deepseek-v4-flash": _FIREWORKS_DEFAULT_MODEL,
    "deepseek-v4-pro-0813": "accounts/fireworks/models/deepseek-v4-pro-0813",
    "deepseek-v4-pro": "accounts/fireworks/models/deepseek-v4-pro",
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


def _detect_provider() -> tuple[str, str, str]:
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
# Client
# ---------------------------------------------------------------------------

_MAX_RETRIES = 5
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
            headers={"Content-Type": "application/json"},
            params={"key": self.api_key},
        )
        resp.raise_for_status()
        data = resp.json()
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

    @staticmethod
    def _handle_compat_response(resp: httpx.Response) -> str:
        resp.raise_for_status()
        data = resp.json()
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
        if json_mode and self._is_gemini:
            self._use_native_gemini = True
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
                # Route to native Gemini if we've already confirmed it's needed
                if self._use_native_gemini:
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
                if resp.status_code in (429, 503) and attempt < _MAX_RETRIES - 1:
                    # Respect Retry-After header if provided (Gemini sends this).
                    retry_after = (
                        resp.headers.get("Retry-After")
                        or resp.headers.get("X-RateLimit-Reset-Requests")
                    )
                    if retry_after:
                        try:
                            wait = float(retry_after)
                        except (ValueError, TypeError):
                            wait = _RATE_LIMIT_BASE_WAIT * (2 ** attempt)
                    else:
                        wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)

                    log.warning(
                        "LLM rate limited (HTTP %s). Waiting %ds before retry %d/%d. "
                        "Provider may be throttled (Fireworks/Gemini). "
                        "Set GEMINI_API_KEY for empty-response failover.",
                        resp.status_code, wait, attempt + 1, _MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue
                raise

            except httpx.TimeoutException:
                if attempt < _MAX_RETRIES - 1:
                    wait = min(_RATE_LIMIT_BASE_WAIT * (2 ** attempt), 60)
                    log.warning(
                        "LLM request timed out, retrying in %ds (attempt %d/%d)",
                        wait, attempt + 1, _MAX_RETRIES,
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


def reset_client() -> None:
    """Drop the singleton so the next get_client() re-reads env (e.g. after failover)."""
    global _instance
    if _instance is not None:
        _instance.close()
        _instance = None


def get_client() -> LLMClient:
    """Return (or create) the module-level LLMClient singleton."""
    global _instance
    if _instance is None:
        base_url, model, api_key = _detect_provider()
        log.info("LLM provider: %s  model: %s", base_url, model)
        _instance = LLMClient(base_url, model, api_key)
    return _instance
