"""Provider-agnostic LLM interface (specs/decisions.md).

All LLM calls go through `judge()` / `chat()` — structured prompt in,
structured JSON out. Swapping providers/models is a config change, which is
what enables the milestone-3 calibration check and the later local-model
benchmark (deferred-enhancements #6).

v1 primary: GLM 5.3 Flash (Z.ai open-platform API, OpenAI-compatible endpoint).
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# .env lives at repo root; load_dotenv searches CWD upward, but be explicit so
# the module works from any working directory.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

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


class LLMError(RuntimeError):
    pass


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
    key = os.getenv(p["key_env"])
    if not key or key == "your-key-here":
        raise LLMError(
            f"Missing API key: set {p['key_env']} in .env "
            f"(see .env.example)"
        )
    return OpenAI(base_url=p["base_url"], api_key=key), p


def chat(prompt: str, system: str = "", cfg: LLMConfig | None = None) -> str:
    """Single completion -> raw text."""
    cfg = cfg or LLMConfig()
    client, p = _client(cfg)
    model = cfg.model or p["model"]
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    last_err: Exception | None = None
    for attempt in range(cfg.max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=cfg.temperature,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:  # noqa: BLE001 — provider SDK raises many types
            last_err = e
            time.sleep(2**attempt)
    raise LLMError(f"LLM call failed after {cfg.max_retries} retries: {last_err}")


def _extract_json(text: str) -> Any:
    """Parse JSON from a model response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise LLMError(f"No JSON object in response: {text[:200]!r}")
    return json.loads(text[start : end + 1])


def judge(prompt: str, system: str, cfg: LLMConfig | None = None) -> dict[str, Any]:
    """Structured call: prompt -> JSON object. Retries on parse failure."""
    cfg = cfg or LLMConfig()
    last_err: Exception | None = None
    for attempt in range(cfg.max_retries):
        raw = chat(prompt, system=system, cfg=cfg)
        try:
            result = _extract_json(raw)
            if isinstance(result, dict):
                return result
            last_err = LLMError(f"Expected JSON object, got {type(result).__name__}")
        except (json.JSONDecodeError, LLMError) as e:
            last_err = e
            # Nudge the model on retry
            prompt = prompt + "\n\nIMPORTANT: respond with ONLY a valid JSON object."
    raise LLMError(f"judge() failed to produce valid JSON: {last_err}")
