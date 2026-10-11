"""M18 verification: state-driven panel checks (offline — no LLM, no keyring,
no network beyond localhost).

Checks:
1. Key-status endpoint (GET /api/key/status): key_set + validation status
   from a stubbed llm.validate_api_key (the real key-info call is never
   made); no key => no validation call; TTL cache means one validation per
   window; saving a key busts the cache; unknown provider => 400; the
   response payload carries booleans + short text only (never key
   material); ok: null ("couldn't verify") never blocks.
2. Mode mapping (node probe over the real sidepanel.js): renderKeyState
   switches nokey/modechips off key_set; buildRunBody maps free / paid /
   rule and the no-key state onto the run-contract fields (use_llm,
   free_tier, privacy_ack only while consented; top_n passthrough).
3. Panel surface (done criteria 1-3 of specs/12-extension.md §M18):
   default view composition, mode chips + captions, no-key state with
   "Create free LLM key" + rule-based path, hidden paste form, consent
   gate hidden + never pre-checked, Settings home for top-N, merged gap
   table with provenance caption, silent connection line, validation uses
   the key-info endpoint (no billable call).

Run: python -m skill_gap_agent.m18_check
"""

from __future__ import annotations

import inspect
import json
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from . import llm as llm_mod
from . import server

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"

# The probe key string: any response containing it would be leaking key
# material — the payload allowlist check below also guards this.
FAKE_KEY = "sk-super-secret-probe"

PROBE_HARNESS = r"""
// m18_check node probe: loads extension/sidepanel.js against a stub DOM
// and checks the M18 state rendering + mode -> run-contract mapping.
const path = process.argv[2];

class El {
  constructor(id) {
    this.id = id;
    this.hidden = false;
    this.value = "";
    this.checked = false;
    this.disabled = false;
    this.textContent = "";
    this.className = "";
    this.children = [];
  }
  addEventListener() {}
  replaceChildren() {}
  appendChild(c) { this.children.push(c); return c; }
  setAttribute() {}
  removeAttribute() {}
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

const els = new Map();
const memo = (id) => {
  if (!els.has(id)) els.set(id, new El(id));
  return els.get(id);
};
memo("modechips").hidden = true; // default HTML state

const modeRadios = [new El("modefree"), new El("modepaid"), new El("moderule")];
let checkedMode = null;

global.document = {
  getElementById: memo,
  createElement: (tag) => new El(tag),
  querySelector: (sel) => (sel.includes("mode") ? checkedMode : null),
  querySelectorAll: (sel) => (sel.includes("mode") ? modeRadios : []),
  // M19 theme applier touches this on load (specs/12-extension.md §M19).
  documentElement: new El("html"),
};
global.chrome = {
  storage: { local: { get: async () => ({}), set: async () => {} } },
  tabs: {
    query: async () => [],
    sendMessage: async () => ({}),
    create: async () => {},
  },
};
global.fetch = async () => { throw new Error("offline (probe)"); };

require(path);
const probe = global.__skillgap_probe;
if (!probe) {
  console.error("probe hook missing from sidepanel.js");
  process.exit(1);
}

const results = {};
// State rendering keyed off key_set (specs/12-extension.md §M18).
probe.renderKeyState(true);
results.keyed_true =
  memo("nokey").hidden === true && memo("modechips").hidden === false;
probe.renderKeyState(false);
results.keyed_false =
  memo("nokey").hidden === false && memo("modechips").hidden === true;

// Mode -> run-contract mapping.
memo("modechips").hidden = false;
memo("topn").value = "7";
memo("privacyack").checked = true;

checkedMode = { value: "free" };
let b = probe.buildRunBody();
results.free =
  b.use_llm === true && b.free_tier === true && b.privacy_ack === true;

memo("privacyack").checked = false;
b = probe.buildRunBody();
results.free_unconsented = b.use_llm === true && b.free_tier === undefined;

checkedMode = { value: "paid" };
b = probe.buildRunBody();
results.paid = b.use_llm === true && b.free_tier === undefined;

checkedMode = { value: "rule" };
b = probe.buildRunBody();
results.rule = b.use_llm === false && b.free_tier === undefined;

memo("modechips").hidden = true;
checkedMode = { value: "free" };
b = probe.buildRunBody();
results.no_key_forces_rule =
  b.use_llm === false && b.free_tier === undefined;

memo("modechips").hidden = false;
checkedMode = { value: "paid" };
results.top_n = probe.buildRunBody().top_n === 7;

console.log(JSON.stringify(results));
process.exit(0);
"""


# --- http helpers (same shape as m14_check) --------------------------------


def _request(
    base: str, path: str, data: bytes, headers: dict[str, str]
) -> tuple[int, bytes]:
    req = urllib.request.Request(base + path, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _post_json(base: str, path: str, payload: dict) -> tuple[int, dict]:
    code, body = _request(
        base,
        path,
        json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    return code, json.loads(body.decode("utf-8") or "{}")


def _get_json(base: str, path: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(base + path, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8") or "{}")


def _start_server() -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


# --- checks ----------------------------------------------------------------


def check_key_status_endpoint() -> None:
    calls = {"present": True, "validate": 0, "result": {"ok": True, "detail": "key verified"}}
    stored: dict[str, str] = {}

    def fake_present(provider: str) -> bool:
        return calls["present"]

    def fake_validate(provider: str) -> dict:
        calls["validate"] += 1
        return dict(calls["result"])

    def fake_get_secret(name: str) -> str | None:
        return FAKE_KEY if calls["present"] else None

    def fake_set_secret(name: str, value: str) -> None:
        stored[name] = value

    real_present = llm_mod.key_present
    real_validate = llm_mod.validate_api_key
    real_get = llm_mod.get_secret
    real_set = server.secrets.set_secret
    llm_mod.key_present = fake_present
    llm_mod.validate_api_key = fake_validate
    llm_mod.get_secret = fake_get_secret
    server.secrets.set_secret = fake_set_secret
    server._invalidate_key_status("openrouter")
    httpd, base = _start_server()
    try:
        # No key: key_set false, ok null, and validation never runs.
        calls["present"] = False
        code, body = _get_json(base, "/api/key/status?provider=openrouter")
        assert code == 200, (code, body)
        assert body["key_set"] is False and body["ok"] is None, body
        assert calls["validate"] == 0, "no key: validation must not run"

        # Key present: validated once (status true), then TTL-cached.
        calls["present"] = True
        code, body = _get_json(base, "/api/key/status?provider=openrouter")
        assert code == 200, (code, body)
        assert body["key_set"] is True and body["ok"] is True, body
        assert "verified" in body["detail"], body
        assert calls["validate"] == 1
        code, body2 = _get_json(base, "/api/key/status?provider=openrouter")
        assert body2 == body, "second call must be served from cache"
        assert calls["validate"] == 1, "TTL cache must suppress re-validation"

        # Rejected key (ok false) after a key change busts the cache.
        calls["result"] = {"ok": False, "detail": "key rejected (HTTP 401)"}
        code, resp = _post_json(base, "/api/key", {
            "provider": "openrouter", "api_key": FAKE_KEY, "remember": True,
        })
        assert code == 200 and stored.get("OPENROUTER_API_KEY") == FAKE_KEY, resp
        code, body = _get_json(base, "/api/key/status?provider=openrouter")
        assert body["ok"] is False and "rejected" in body["detail"], body
        assert calls["validate"] == 2, "key save must bust the cache"

        # Couldn't verify (ok null) — the neutral, never-blocking state.
        calls["result"] = {"ok": None, "detail": "couldn't verify (network)"}
        server._invalidate_key_status("openrouter")
        code, body = _get_json(base, "/api/key/status?provider=openrouter")
        assert body["ok"] is None and body["key_set"] is True, body

        # Unknown provider is rejected; payload is an allowlist — the fake
        # key must never appear anywhere in any response.
        code, body = _get_json(base, "/api/key/status?provider=nope")
        assert code == 400, (code, body)
        code, body = _get_json(base, "/api/key/status")
        assert code == 200 and body["key_set"] is True, body
        dumped = json.dumps({"a": body, "b": body2})
        assert FAKE_KEY not in dumped, "key material leaked into a response"
        assert set(body) <= {"key_set", "ok", "detail", "checked_at"}, body
    finally:
        llm_mod.key_present = real_present
        llm_mod.validate_api_key = real_validate
        llm_mod.get_secret = real_get
        server.secrets.set_secret = real_set
        server._invalidate_key_status("openrouter")
        httpd.shutdown()
    print("key-status endpoint OK: presence, validation stub, TTL cache, "
          "invalidation, allowlist payload")


def check_mode_mapping() -> None:
    node = shutil.which("node")
    assert node, "node is required for the sidepanel probe (node --check runs in verify)"
    with tempfile.TemporaryDirectory() as tmp:
        harness = Path(tmp) / "probe.js"
        harness.write_text(PROBE_HARNESS, encoding="utf-8")
        proc = subprocess.run(
            [node, str(harness), str(EXTENSION_DIR / "sidepanel.js")],
            capture_output=True, text=True, timeout=60, check=False,
        )
    assert proc.returncode == 0, f"probe failed: {proc.stderr}"
    results = json.loads(proc.stdout.strip().splitlines()[-1])
    expected = [
        "keyed_true", "keyed_false", "free", "free_unconsented",
        "paid", "rule", "no_key_forces_rule", "top_n",
    ]
    for name in expected:
        assert results.get(name) is True, f"probe scenario failed: {name} ({results})"
    print("mode mapping OK: state rendering off key_set + free/paid/rule -> "
          "run-contract fields")


def check_panel_surface() -> None:
    html = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")

    # Done criterion 1: default view composition + disclosure states.
    assert re.search(r'id="conn"[^>]*hidden', html), "connection line must start hidden"
    assert 'id="resumeline"' in html and 'id="setupresume"' in html, "resume collapse missing"
    assert 'id="jdcount"' not in html, "counter must live on the capture button"
    assert "Capture JD" in html, "capture button missing"
    assert re.search(r'id="modechips"[^>]*hidden', html), "mode chips start hidden"
    for chip in ('id="modefree"', 'id="modepaid"', 'id="moderule"'):
        assert chip in html, f"mode chip missing: {chip}"
    for caption in (
        "costs nothing; provider may log inputs",
        "uses your key's credits",
        "instant, no AI",
    ):
        assert caption in html, f"mode caption missing: {caption}"
    assert re.search(r'id="llmarea"[^>]*hidden', html), "paste form must be hidden by default"
    assert re.search(r'id="freeconsent"[^>]*hidden', html), "consent block hidden by default"
    assert 'id="topn"' in html and 'id="serverBase"' in html, "Settings home missing"
    assert "<summary>Settings</summary>" in html, "Settings block missing"
    assert 'id="rulehint"' not in html, "rulehint must not be in the body (M18)"

    # Done criterion 2: no-key state + one-link paste-form fallback.
    assert 'id="nokey"' in html, "no-key state missing"
    assert "Create free LLM key" in html, "create-key button missing"
    assert 'id="morerule"' in html and "or run rule-based (no AI)" in html, (
        "rule-based path missing from the no-key state"
    )
    assert 'id="havekeylink"' in html and "I already have a key" in html, (
        "paste-form fallback link missing"
    )

    # M16 B gate preserved: verbatim disclaimer + never pre-checked.
    assert "Free models cost nothing" in html, "verbatim disclaimer missing"
    assert not re.search(r'id="privacyack"[^>]*checked', html), (
        "consent checkbox must never be pre-checked"
    )

    # M15 honesty preserved through the table merge: per-item provenance
    # caption; the wide Source column is gone.
    assert "<th>Skill gap</th>" in html and "<th>Score</th>" in html, html
    assert "<th>Source</th>" not in html, "Source column must be merged (M18)"
    assert "demanded by" in js and "g.provenance" in js, "provenance caption missing"

    # Plan: reopen is hidden until the iframe fails.
    assert re.search(r'id="reopen"[^>]*hidden', html), "reopen must be auto-shown only"
    assert "planframe" in js and 'addEventListener("error"' in js, "iframe failure hook missing"

    # Done criterion 3: validation via the key-info endpoint only.
    assert "/api/key/status" in js, "panel must read the key-status endpoint"
    source = inspect.getsource(llm_mod.validate_api_key)
    assert "api/v1/key" in source, "validation must use the key-info endpoint"
    assert "chat" not in source, "validation must never make a billable model call"

    # The key must never reach extension storage (plaintext in the profile).
    assert not re.search(
        r"chrome\.storage\.local\.set\([^)]*key", js, re.IGNORECASE | re.DOTALL
    ), "key material must never go into chrome.storage"
    print("panel surface OK: default view, states, captions, gate, "
          "key-info validation, no key in storage")


def main() -> None:
    check_key_status_endpoint()
    check_mode_mapping()
    check_panel_surface()
    print("M18 CHECK PASS: state-driven panel + key validation + mode mapping OK.")


if __name__ == "__main__":
    main()
