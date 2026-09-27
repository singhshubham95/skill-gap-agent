"""Secret resolution: OS keyring only (user decision 2026-09-27).

API keys live in the OS credential vault (Windows Credential Manager /
macOS Keychain / libsecret on Linux) outside the repo entirely, so no git
operation can ever expose them. No `.env` file fallback — `.env.example`
was deleted; keyring is the single local method.

Resolution order for a key named e.g. OPENROUTER_API_KEY:
1. Environment variable (explicit override; also covers CI).
2. OS keyring under service "skill-gap-agent" (preferred for local runs).

`keyring` is an optional dependency: if it is not installed (or the OS
backend is unavailable, e.g. headless Linux), resolution returns None and
the caller raises LLMError with the set command.
"""

from __future__ import annotations

import os

_KEYRING_SERVICE = "skill-gap-agent"


def _from_keyring(env_name: str) -> str | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        value = keyring.get_password(_KEYRING_SERVICE, env_name)
    except Exception:  # noqa: BLE001 — any backend failure = fall through
        # No keyring backend (headless Linux, locked vault, etc.).
        return None
    return value or None


def get_secret(env_name: str) -> str | None:
    """Resolve a secret: env var -> OS keyring. No file fallback."""
    value = os.getenv(env_name)
    if value:
        return value
    return _from_keyring(env_name)


def set_secret(env_name: str, value: str) -> None:
    """Store a secret in the OS keyring under this project's service name."""
    import keyring

    keyring.set_password(_KEYRING_SERVICE, env_name, value)


def delete_secret(env_name: str) -> None:
    """Remove a secret from the OS keyring (no-op if absent)."""
    import keyring
    from keyring.errors import KeyRingError

    try:
        keyring.delete_password(_KEYRING_SERVICE, env_name)
    except KeyRingError:
        pass
