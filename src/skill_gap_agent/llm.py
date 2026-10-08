"""Provider-agnostic LLM interface (specs/decisions.md).

All LLM calls go through `judge()` / `chat()` — structured prompt in,
structured JSON out. Swapping providers/models is a config change, which is
what enables the milestone-3 calibration check and the later local-model
benchmark (deferred-enhancements #6).

v1 primary: DeepSeek V4 Flash 0731 via OpenRouter (see PROVIDERS below).
"""

from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass, replace
from typing import Any

from .secrets import get_secret

# OpenAI-compatible endpoints. Primary: DeepSeek V4 Flash via OpenRouter
# (284B MoE / 13B active — strong reasoning at ~$0.035/M input, $0.106/M output).
# GLM via OpenRouter/Z.ai and OpenAI remain available for the calibration check.
PROVIDERS: dict[str, dict[str, str]] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1/",
        "model": "deepseek/deepseek-v4-flash-0731",
        "key_env": "OPENROUTER_API_KEY",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "model": "glm-4.5-flash",
        "key_env": "GLM_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1/",
        "model": "gpt-4o-mini",
        "key_env": "OPENAI_API_KEY",
    },
}


@dataclass
class LLMConfig:
    provider: str = "openrouter"
    model: str | None = None  # None -> provider default
    temperature: float = 0.2
    max_retries: int = 3
    # M16 free-tier routing (specs/05-ai-caller.md §Free-tier routing):
    # run-level opt-in flag; when true every call routes to the next
    # FREE_MODELS entry instead of the provider default.
    free_tier: bool = False
    # M16 per-touchpoint timeout (seconds). None = the caller's default for
    # its touchpoint (judge/synthesis/bridge/OSS 120s; extraction 1800s).
    timeout: float | None = None


# M16: ordered fallback list of OpenRouter `:free` model IDs. The free set
# churns, so this is config, not a spec constant — edit here when models
# appear/vanish (specs/05-ai-caller.md §Free-tier routing).
FREE_MODELS: list[str] = [
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]

# M16 retry policy (specs/05-ai-caller.md §Retry & failure handling).
RETRY_BASE_SECONDS = 2.0
RETRY_FACTOR = 2.0
RETRY_CAP_SECONDS = 60.0
RETRY_ATTEMPTS_FREE = 5
# Sentinel for "the caller did not choose an attempt budget" — free mode
# raises the budget to RETRY_ATTEMPTS_FREE only when this is untouched.
_DEFAULT_MAX_RETRIES = 3
# Per-touchpoint request timeouts: judge/synthesis/bridge/OSS get 120s;
# extraction keeps a 30-minute budget until the extraction-latency open
# item resolves the speed side.
DEFAULT_TIMEOUT_SECONDS = 120.0
EXTRACTION_TIMEOUT_SECONDS = 1800.0


class LLMError(RuntimeError):
    pass


class LLMNonTransientError(LLMError):
    """M16: an error retrying cannot fix (401/403 bad key, 400 malformed
    request, 404 unknown model). Fails on the first attempt into M15's
    loud-degradation path — retrying a bad key burns the run's budget."""


class LLMQuotaError(LLMError):
    """M16: a free-mode call that died of 429 quota exhaustion after its
    retries. Carries the spec's reason text (05-ai-caller.md §Free-tier
    routing) so M15's banner shows it instead of raw SDK error text."""


# M16: the loud-degradation reason for free-mode quota exhaustion —
# verbatim from specs/05-ai-caller.md §Free-tier routing ("Interaction
# with M15"). Surface: degraded_reasons -> M15 banner.
QUOTA_EXHAUSTED_MESSAGE = (
    "free quota exhausted — add your own key or wait for the reset"
)


# --- M15: LLM presence policy (specs/05-ai-caller.md §LLM presence policy) ---
# Provenance labels are defined once here; output.py and the extension panel
# render them. Reused LLM output must never read as freshly generated.
LABEL_LLM = "LLM"
LABEL_LLM_CACHED = "LLM (cached)"
LABEL_RULE = "Rule-based"


def rule_unavailable_label(reason: str) -> str:
    """Label for rule-based output that was forced by an LLM failure."""
    return f"Rule-based (LLM unavailable — {reason})"


def key_present(provider: str) -> bool:
    """M15 pre-flight probe: is a key stored for this provider?"""
    p = PROVIDERS.get(provider)
    if p is None:
        raise LLMError(f"Unknown provider: {provider}")
    key = get_secret(p["key_env"])
    return bool(key) and key != "your-key-here"


def require_api_key(provider: str) -> None:
    """M15 fail-fast: LLM mode with no key must refuse before any work.

    Presence check only — an invalid key fails at the first call, which is
    the loud-degradation path (specs/05-ai-caller.md §Degradation).
    """
    if not key_present(provider):
        key_env = PROVIDERS[provider]["key_env"] if provider in PROVIDERS else provider
        raise LLMError(
            f"LLM mode needs an API key for '{provider}'. Save one in the "
            f"extension panel's LLM section (or set {key_env} in the OS "
            f"keyring), or turn off 'Use LLM intelligence' to run in "
            f"Rule-based mode."
        )


def _client(cfg: LLMConfig):
    try:
        from openai import OpenAI
    except ImportError as e:
        raise LLMError(
            "The 'openai' package is required for LLM calls. "
            "Install with: pip install openai"
        ) from e

    p = PROVIDERS.get(cfg.provider)
    if p is None:
        raise LLMError(f"Unknown provider: {cfg.provider}")
    key = get_secret(p["key_env"])
    if not key or key == "your-key-here":
        raise LLMError(
            f"Missing API key: set {p['key_env']} via the OS keyring "
            f"(keyring.set_password('skill-gap-agent', '{p['key_env']}', ...))"
        )
    timeout = cfg.timeout if cfg.timeout is not None else DEFAULT_TIMEOUT_SECONDS
    return OpenAI(base_url=p["base_url"], api_key=key, timeout=timeout), p


def _classify_error(e: Exception) -> tuple[bool, float | None]:
    """M16 classification (specs/05-ai-caller.md §Retry & failure handling).

    Returns (transient, retry_after). Transient: 429, 5xx, timeouts,
    connection errors. Non-transient: 401/403 bad key, 400 malformed
    request, 404 unknown model — fail immediately. `retry_after` is the
    Retry-After header value in seconds when the response carries one.
    """
    status = getattr(e, "status_code", None)
    if status is None:
        # openai SDK APIStatusError carries .status_code; older shapes may
        # only expose the message — classify from it.
        msg = str(e)
        m = re.search(r"\b(4\d\d|5\d\d)\b", msg)
        status = int(m.group(1)) if m else None
    if status is not None:
        if status in (401, 403, 400, 404):
            return False, None
        return True, _retry_after(e)
    text = str(e).lower()
    if any(k in text for k in ("timeout", "timed out", "connection", "temporarily")):
        return True, None
    # Unknown errors are treated as transient: a flaky free endpoint is the
    # common case, and a genuinely broken call still fails within budget.
    return True, None


def _retry_after(e: Exception) -> float | None:
    """Retry-After header (seconds) from an SDK-wrapped HTTP error, if any."""
    headers = getattr(e, "headers", None) or {}
    try:
        value = headers.get("retry-after") or headers.get("Retry-After")
    except Exception:  # noqa: BLE001 — headers may be a plain dict or None
        value = None
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _backoff_seconds(attempt: int, retry_after: float | None) -> float:
    """Exponential backoff with full jitter, capped; Retry-After wins when
    present (min(retry_after, cap)) — OpenRouter sends one on 429."""
    if retry_after is not None:
        return min(retry_after, RETRY_CAP_SECONDS)
    raw = min(RETRY_BASE_SECONDS * (RETRY_FACTOR**attempt), RETRY_CAP_SECONDS)
    return random.uniform(0, raw)


def _free_model_for(cfg: LLMConfig, rotation: int) -> str:
    """The :free model answering this attempt (one rotation through the list)."""
    if cfg.model:
        return cfg.model
    return FREE_MODELS[min(rotation, len(FREE_MODELS) - 1)]


# M16: the :free ID that last answered a call (moves when the fallback list
# rotates). Read by the server for GET /api/status (specs/05-ai-caller.md
# §Free-tier routing — status fields).
_last_model: str | None = None


def last_model() -> str | None:
    """The model ID that most recently answered an LLM call."""
    return _last_model


def chat(prompt: str, system: str = "", cfg: LLMConfig | None = None) -> str:
    """Single completion -> raw text.

    M16 retry policy: transient failures (429/5xx/timeout/connection) retry
    with jittered capped backoff honoring Retry-After; non-transient errors
    (401/403/400/404) fail on the first attempt. In free mode the attempt
    cap rises to 5 (unless the caller set an explicit budget — judge()'s
    bounded nesting relies on that) and model-unavailable or transiently
    exhausted attempts rotate to the next FREE_MODELS entry (one rotation)
    before the call fails.
    """
    cfg = cfg or LLMConfig()
    client, p = _client(cfg)
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    # V2: an explicit caller budget (e.g. judge()'s single-attempt nesting)
    # wins over the free-mode default — the spec's bound is on total
    # attempts per logical call, so the override must not be re-derived.
    # The sentinel marks "caller did not choose a budget" (the dataclass
    # default); free mode then raises it to 5.
    if cfg.max_retries == _DEFAULT_MAX_RETRIES:
        max_retries = RETRY_ATTEMPTS_FREE if cfg.free_tier else cfg.max_retries
    else:
        max_retries = cfg.max_retries
    last_err: Exception | None = None
    rotation = 0
    for attempt in range(max_retries):
        model = _free_model_for(cfg, rotation) if cfg.free_tier else (
            cfg.model or p["model"]
        )
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=cfg.temperature,
            )
            global _last_model
            _last_model = model
            return resp.choices[0].message.content or ""
        except Exception as e:
            last_err = e
            transient, retry_after = _classify_error(e)
            if cfg.free_tier and _model_unavailable(e):
                # M16 free-mode fallback: advance to the next FREE_MODELS
                # entry (one rotation) on model-unavailable (the free set
                # churns; a stale entry must not kill the call). Every other
                # non-transient error falls through and fails immediately.
                rotation += 1
                if attempt < max_retries - 1:
                    time.sleep(_backoff_seconds(attempt, retry_after))
                continue
            if not transient:
                raise LLMNonTransientError(
                    f"LLM call failed (non-transient, not retried): {e}"
                ) from e
            # V5: transient exhaustion (429/5xx) rotates the model too —
            # the spec's fallback trigger is "attempts exhausted via
            # 429/5xx, or model-unavailable". Rotating on the LAST
            # transient attempt means the next attempt (if the caller
            # retries) starts on the next entry; within this call the
            # rotation advances on every transient failure.
            if cfg.free_tier:
                rotation += 1
            if attempt < max_retries - 1:
                time.sleep(_backoff_seconds(attempt, retry_after))
    if cfg.free_tier and _is_quota_exhausted(last_err):
        # M16: a 429 that survives the retries degrades loudly through
        # M15's banner carrying the spec's reason — not raw SDK text (AC4).
        raise LLMQuotaError(QUOTA_EXHAUSTED_MESSAGE) from last_err
    raise LLMError(f"LLM call failed after {max_retries} retries: {last_err}")


def _model_unavailable(e: Exception) -> bool:
    """M16 free-mode fallback trigger: the model itself is unavailable
    (404 unknown model) or the provider says so in the message."""
    status = getattr(e, "status_code", None)
    if status == 404:
        return True
    text = str(e).lower()
    return "unavailable" in text or "not a valid model" in text


def _is_quota_exhausted(e: Exception | None) -> bool:
    """M16: did this failure come from a 429 (the free quota)?"""
    if e is None:
        return False
    if isinstance(e, LLMQuotaError):
        return True
    if getattr(e, "status_code", None) == 429:
        return True
    return bool(re.search(r"\b429\b", str(e)))


def _extract_json(text: str) -> Any:
    """Parse JSON from a model response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.removeprefix("json")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"No JSON object in response: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def judge(prompt: str, system: str, cfg: LLMConfig | None = None) -> dict[str, Any]:
    """Structured call: prompt -> JSON object.

    M16 bounded nesting (specs/05-ai-caller.md §Retry & failure handling):
    parse-retries re-invoke chat(), which has its own retry loop — the old
    shape multiplied attempts up to max_retries². The API-attempt budget is
    now shared: total attempts per logical judge() call are bounded by
    max_retries (5 in free mode) regardless of parse-retry nesting.
    """
    cfg = cfg or LLMConfig()
    max_retries = RETRY_ATTEMPTS_FREE if cfg.free_tier else cfg.max_retries
    last_err: Exception | None = None
    # V5 fix: the free-mode rotation lives here, not inside chat() — the
    # nested single-attempt chat() calls of one logical judge() call must
    # share it, or every attempt restarts at FREE_MODELS[0] and the
    # fallback list never advances. It advances only on chat() failures
    # (model-unavailable or exhausted transient attempts — the spec's
    # fallback triggers), never on parse retries of a response that came
    # back fine.
    rotation = 0
    for attempt in range(max_retries):
        # Each chat() call gets exactly one API attempt (the explicit
        # max_retries=1 budget wins over the free-mode default); the
        # parse-retry loop owns the whole budget. A chat() failure (e.g. a
        # 429 that exhausted its single attempt) is a parse-retry-able
        # outcome like unparseable JSON — the loop continues within budget.
        attempt_cfg = _single_attempt(cfg)
        if cfg.free_tier:
            attempt_cfg = replace(
                attempt_cfg, model=_free_model_for(cfg, rotation))
        try:
            raw = chat(prompt, system=system, cfg=attempt_cfg)
        except LLMNonTransientError:
            # Non-transient (bad key, malformed request) must fail on the
            # first attempt in every mode — retrying burns the budget the
            # loud-degradation layer above would use (spec: §Retry &
            # failure handling "Classify before retrying").
            raise
        except LLMError as e:
            last_err = e
            if cfg.free_tier:
                rotation += 1
            continue
        try:
            result = _extract_json(raw)
            if isinstance(result, dict):
                return result
            last_err = LLMError(f"Expected JSON object, got {type(result).__name__}")
        except (json.JSONDecodeError, LLMError) as e:
            last_err = e
            # Nudge the model on retry
            prompt = prompt + "\n\nIMPORTANT: respond with ONLY a valid JSON object."
    if cfg.free_tier and _is_quota_exhausted(last_err):
        raise LLMQuotaError(QUOTA_EXHAUSTED_MESSAGE) from last_err
    raise LLMError(f"judge() failed to produce valid JSON: {last_err}")


def _single_attempt(cfg: LLMConfig) -> LLMConfig:
    """A copy of cfg whose chat() loop spends exactly one attempt."""
    return replace(cfg, max_retries=1)


def extraction_cfg(cfg: LLMConfig | None = None) -> LLMConfig:
    """M16: the extraction touchpoint keeps a 30-minute budget (specs/
    05-ai-caller.md §Retry & failure handling) until the extraction-latency
    open item resolves the speed side."""
    return replace(cfg or LLMConfig(), timeout=EXTRACTION_TIMEOUT_SECONDS)
