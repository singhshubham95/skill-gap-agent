"""M16 offline verification — free-tier access + retry hardening.

Pins the M16 fixes (specs/05-ai-caller.md §Free-tier routing +
§Retry & failure handling; specs/12-extension.md §M16 A/B):

1. check_oauth_connect_flow — the callback stores a one-time code with a
   TTL, /api/oauth/pending reports it, the exchange (stubbed at the
   OpenRouter boundary) stores the minted key in the OPENROUTER_API_KEY
   keyring slot, a code mismatch / exchange failure stores nothing, and
   the panel carries the Connect button + PKCE wiring with no key in
   chrome.storage.
2. check_consent_gate — free_tier without privacy_ack is refused (409)
   before any work; the panel shows the verbatim disclaimer with an
   unchecked checkbox and a versioned consent flag.
3. check_retry_classification — transient errors (429/5xx/timeout) retry
   within the attempt budget and honor Retry-After; non-transient errors
   (401/400/404) fail on the first attempt.
4. check_bounded_attempts — total API attempts per logical judge() call
   are bounded by max_retries even when every response is unparseable
   (the old judge×chat nesting multiplied attempts).
5. check_model_fallback — free mode advances to the next FREE_MODELS
   entry on model-unavailable, and the attempt cap rises to 5.

All LLM seams are stubbed at the llm._client boundary; the OpenRouter
exchange is stubbed at server._exchange_openrouter_code; the keyring is
stubbed at the secrets module boundary. Localhost only.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from . import llm as llm_mod
from . import secrets as secrets_mod
from . import server

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"

DISCLAIMER_SNIPPET = "Free models cost nothing"


# --- http helpers (same shape as m15_check) ---------------------------------


def _get(base: str, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return resp.status, resp.read()


def _get_json(base: str, path: str) -> tuple[int, dict]:
    code, body = _get(base, path)
    return code, json.loads(body.decode("utf-8"))


def _post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def _start() -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with server._lock:
        server._run.update(
            status="idle", stage=None, phase=None,
            started_at=None, finished_at=None, error=None,
            llm_mode=None, degraded_reasons=[],
            free_tier=False, llm_model=None,
        )
        server._oauth.update(code=None, created_at=None)
    server._drop_paused()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


# --- llm seam stubs ---------------------------------------------------------


class _FakeStatusError(Exception):
    """Stand-in for an openai SDK APIStatusError."""

    def __init__(self, status_code: int, retry_after: str | None = None):
        super().__init__(f"Error {status_code}")
        self.status_code = status_code
        self.headers = {"retry-after": retry_after} if retry_after else {}


def _ok_response(text: str):
    """Minimal stand-in for a chat.completions response."""
    message = type("M", (), {"content": text})()
    choice = type("C", (), {"message": message})()
    return type("R", (), {"choices": [choice]})()


class _StubClient:
    """Chat client whose create() replays a scripted list of outcomes.

    Each create() call consumes one outcome: an Exception is raised, any
    other value is returned as the response. Every call is recorded.
    """

    def __init__(self, outcomes: list):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []
        self.completions = self._Completions(self)

    class _Completions:
        def __init__(self, outer: _StubClient):
            self._outer = outer

        def create(self, **kwargs):
            self._outer.calls.append(kwargs)
            outcome = (
                self._outer.outcomes.pop(0)
                if self._outer.outcomes else None
            )
            if isinstance(outcome, Exception):
                raise outcome
            return outcome if outcome is not None else _ok_response("{}")


def _patch_client(outcomes: list) -> _StubClient:
    """Route llm._client to a stub client replaying `outcomes`.

    Returns the stub; restore llm._client with _unpatch_client().
    """
    stub = _StubClient(outcomes)
    _patch_client.original = llm_mod._client
    llm_mod._client = lambda cfg: (stub, llm_mod.PROVIDERS["openrouter"])
    return stub


def _unpatch_client() -> None:
    llm_mod._client = _patch_client.original


# --- checks -----------------------------------------------------------------


def check_oauth_connect_flow() -> None:
    httpd, base = _start()
    stored: dict[str, str] = {}
    real_set = secrets_mod.set_secret
    real_get = secrets_mod.get_secret

    def fake_set(env_name: str, value: str) -> None:
        stored[env_name] = value

    def fake_get(env_name: str) -> str | None:
        return stored.get(env_name)

    secrets_mod.set_secret = fake_set
    secrets_mod.get_secret = fake_get
    real_exchange = server._exchange_openrouter_code
    exchanged: list[dict] = []

    def fake_exchange(code: str, code_verifier: str) -> dict:
        exchanged.append({"code": code, "code_verifier": code_verifier})
        return {"key": "sk-or-m16-minted-key"}

    server._exchange_openrouter_code = fake_exchange
    try:
        # No callback yet -> nothing pending.
        code, body = _get_json(base, "/api/oauth/pending?state=abc")
        assert code == 200 and body.get("pending") is False, (code, body)

        # Step 3: OpenRouter redirects the tab to the callback.
        code, raw = _get(base, "/api/oauth/callback?code=one-time-code&state=abc")
        assert code == 200 and b"Connected" in raw, (code, raw[:200])
        code, body = _get_json(base, "/api/oauth/pending?state=abc")
        assert body.get("pending") is True, body

        # Step 4: the panel exchanges; the key lands in the keyring slot.
        code, body = _post(base, "/api/oauth/exchange", {
            "code": "one-time-code", "code_verifier": "verifier-xyz",
        })
        assert code == 200 and body.get("key_set") is True, (code, body)
        assert stored.get("OPENROUTER_API_KEY") == "sk-or-m16-minted-key", stored
        assert exchanged == [{
            "code": "one-time-code", "code_verifier": "verifier-xyz",
        }], exchanged
        # The code is one-time: consumed by the exchange.
        code, body = _get_json(base, "/api/oauth/pending?state=abc")
        assert body.get("pending") is False, body

        # A second exchange with the same code is refused, nothing stored.
        code, body = _post(base, "/api/oauth/exchange", {
            "code": "one-time-code", "code_verifier": "verifier-xyz",
        })
        assert code == 409, (code, body)

        # A code mismatch is rejected and stores nothing.
        code, _ = _get(base, "/api/oauth/callback?code=fresh-code&state=abc")
        assert code == 200
        code, body = _post(base, "/api/oauth/exchange", {
            "code": "wrong-code", "code_verifier": "verifier-xyz",
        })
        assert code == 409, (code, body)
        assert stored.get("OPENROUTER_API_KEY") == "sk-or-m16-minted-key", stored

        # Exchange failure -> 502, nothing stored.
        def failing_exchange(code: str, code_verifier: str) -> dict:
            raise RuntimeError("openrouter down")

        server._exchange_openrouter_code = failing_exchange
        code, _ = _get(base, "/api/oauth/callback?code=boom-code&state=abc")
        assert code == 200
        code, body = _post(base, "/api/oauth/exchange", {
            "code": "boom-code", "code_verifier": "verifier-xyz",
        })
        assert code == 502, (code, body)
        assert stored.get("OPENROUTER_API_KEY") == "sk-or-m16-minted-key", stored

        # Panel surface: Connect button + PKCE wiring; no key in storage.
        html = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
        assert 'id="connectfree"' in html, "Connect free LLM button missing"
        assert 'id="freetier"' in html and 'id="privacyack"' in html, html
        js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")
        assert "code_challenge" in js and "S256" in js, "PKCE wiring missing"
        assert "/api/oauth/pending" in js and "/api/oauth/exchange" in js, js
        assert "chrome.tabs.create" in js, "connect must open a tab"
        assert not re.search(
            r"chrome\.storage\.local\.set\([^)]*key", js, re.IGNORECASE | re.DOTALL
        ), "key material must never go into chrome.storage"
        print("oauth connect OK: callback -> pending -> exchange -> keyring slot")
    finally:
        secrets_mod.set_secret = real_set
        secrets_mod.get_secret = real_get
        server._exchange_openrouter_code = real_exchange
        httpd.shutdown()


def check_consent_gate() -> None:
    httpd, base = _start()
    # The consent gate must be checked regardless of key state: stub the
    # M15 pre-flight (server.py imported require_api_key by name) so it
    # cannot mask the 409 ordering.
    real_require = server.require_api_key
    server.require_api_key = lambda provider: None
    try:
        # free_tier without privacy_ack: refused (409) before any work.
        code, body = _post(base, "/api/run", {
            "phase": "gaps", "free_tier": True, "privacy_ack": False,
            "jds": [], "skills_path": "x.json",
        })
        assert code == 409, (code, body)
        assert "privacy_ack" in body.get("error", ""), body
        code, status = _get_json(base, "/api/status")
        assert status.get("status") == "idle", status  # nothing started

        # Panel surface: verbatim disclaimer, unchecked checkbox, consent
        # versioning, run contract carries free_tier + privacy_ack.
        html = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
        assert DISCLAIMER_SNIPPET in html, "verbatim disclaimer missing"
        assert re.search(r'id="privacyack"', html), "consent checkbox missing"
        assert not re.search(r'id="privacyack"[^>]*checked', html), (
            "consent checkbox must never be pre-checked"
        )
        js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")
        assert "CONSENT_VERSION" in js, "consent versioning missing"
        assert re.search(r"free_tier\s*=\s*true", js), "run body must carry free_tier"
        assert re.search(r"privacy_ack\s*=\s*true", js), "run body must carry privacy_ack"
        assert "free_consent_at" in js and "consent_version" in js, js
        print("consent gate OK: 409 without ack, verbatim disclaimer, versioned flag")
    finally:
        server.require_api_key = real_require
        httpd.shutdown()


def check_retry_classification() -> None:
    real_sleep = llm_mod.time.sleep
    sleeps: list[float] = []
    llm_mod.time.sleep = lambda s: sleeps.append(s)
    try:
        cfg = llm_mod.LLMConfig()

        # Transient 429 with Retry-After: retries, honors the header.
        stub = _patch_client([_FakeStatusError(429, retry_after="7"),
                              _ok_response("done")])
        sleeps.clear()
        out = llm_mod.chat("p", system="s", cfg=cfg)
        assert out == "done", out
        assert len(stub.calls) == 2, len(stub.calls)
        assert sleeps == [7.0], sleeps  # min(retry_after, cap), not jitter
        _unpatch_client()

        # Transient 5xx then success: recovers within the budget.
        stub = _patch_client([_FakeStatusError(503), _ok_response("done")])
        sleeps.clear()
        out = llm_mod.chat("p", system="s", cfg=cfg)
        assert out == "done" and len(stub.calls) == 2, (out, len(stub.calls))
        assert len(sleeps) == 1 and 0 <= sleeps[0] <= 60, sleeps
        _unpatch_client()

        # Timeout-shaped error is transient too.
        stub = _patch_client([llm_mod.LLMError("request timed out"),
                              _ok_response("done")])
        out = llm_mod.chat("p", system="s", cfg=cfg)
        assert out == "done" and len(stub.calls) == 2, (out, len(stub.calls))
        _unpatch_client()

        # Non-transient 401: fails on the FIRST attempt, no sleep.
        stub = _patch_client([_FakeStatusError(401)])
        sleeps.clear()
        try:
            llm_mod.chat("p", system="s", cfg=cfg)
            raise AssertionError("expected non-transient failure")
        except llm_mod.LLMNonTransientError:
            pass
        assert len(stub.calls) == 1, len(stub.calls)
        assert not sleeps, sleeps
        _unpatch_client()

        # 400 and 404 are non-transient as well.
        for status in (400, 404):
            stub = _patch_client([_FakeStatusError(status)])
            try:
                llm_mod.chat("p", system="s", cfg=cfg)
                raise AssertionError(f"expected failure for {status}")
            except llm_mod.LLMNonTransientError:
                pass
            assert len(stub.calls) == 1, (status, len(stub.calls))
            _unpatch_client()
        print("retry classification OK: transient retries + Retry-After, "
              "non-transient fails first attempt")
    finally:
        llm_mod.time.sleep = real_sleep


def check_bounded_attempts() -> None:
    real_sleep = llm_mod.time.sleep
    llm_mod.time.sleep = lambda s: None
    try:
        # Every response is valid text but unparseable JSON: judge() keeps
        # parse-retrying, but total API attempts must stay <= max_retries.
        stub = _patch_client([_ok_response("not json at all")] * 10)
        try:
            llm_mod.judge("p", "s", cfg=llm_mod.LLMConfig())
            raise AssertionError("expected judge failure")
        except llm_mod.LLMError:
            pass
        assert len(stub.calls) == llm_mod.LLMConfig().max_retries, (
            f"attempts multiplied: {len(stub.calls)}"
        )
        print(f"bounded attempts OK: {len(stub.calls)} API attempts "
              f"for max_retries={llm_mod.LLMConfig().max_retries}")
    finally:
        llm_mod.time.sleep = real_sleep
        _unpatch_client()


def check_model_fallback() -> None:
    real_sleep = llm_mod.time.sleep
    llm_mod.time.sleep = lambda s: None
    try:
        # Free mode: model-unavailable (404) rotates to the next FREE_MODELS
        # entry, and the attempt cap rises to 5.
        stub = _patch_client(
            [_FakeStatusError(404), _FakeStatusError(404),
             _ok_response(json.dumps({"ok": True}))]
        )
        cfg = llm_mod.LLMConfig(free_tier=True)
        out = llm_mod.chat("p", system="s", cfg=cfg)
        assert json.loads(out) == {"ok": True}, out
        models = [c["model"] for c in stub.calls]
        # One rotation: entry 0, then entry 1, then entry 1 again (the list
        # has 2 entries; the last absorbs further retries).
        assert models == llm_mod.FREE_MODELS[:2] + [llm_mod.FREE_MODELS[-1]], models
        assert models[0] != models[1], "fallback must advance the model"
        _unpatch_client()

        # Free-mode attempt cap is 5: five 429s exhaust the budget.
        stub = _patch_client([_FakeStatusError(429)] * 5)
        try:
            llm_mod.chat("p", system="s", cfg=llm_mod.LLMConfig(free_tier=True))
            raise AssertionError("expected exhaustion")
        except llm_mod.LLMError as e:
            assert "5" in str(e), e
        assert len(stub.calls) == llm_mod.RETRY_ATTEMPTS_FREE, len(stub.calls)
        _unpatch_client()

        # judge() in free mode is bounded by 5 total attempts too.
        stub = _patch_client([_ok_response("garbage")] * 10)
        try:
            llm_mod.judge("p", "s", cfg=llm_mod.LLMConfig(free_tier=True))
            raise AssertionError("expected judge failure")
        except llm_mod.LLMError:
            pass
        assert len(stub.calls) == llm_mod.RETRY_ATTEMPTS_FREE, len(stub.calls)
        print("model fallback OK: :free rotation + 5-attempt free cap")
    finally:
        llm_mod.time.sleep = real_sleep
        _unpatch_client()


def main() -> None:
    check_oauth_connect_flow()
    check_consent_gate()
    check_retry_classification()
    check_bounded_attempts()
    check_model_fallback()
    print("M16 CHECK PASS: OAuth connect, consent gate, retry classification, "
          "bounded attempts, model fallback OK.")


if __name__ == "__main__":
    main()
