"""M20 offline check — request-origin gate, Content-Type enforcement,
skills_path containment, panel transport rule
(specs/12-extension.md §Security posture).

Run: python -m skill_gap_agent.m20_check
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from . import server

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"


# --- http helpers (same shape as m16_check) ---------------------------------


def _req(
    base: str,
    path: str,
    method: str = "GET",
    headers: dict | None = None,
    body: bytes | None = None,
) -> tuple[int, bytes]:
    req = urllib.request.Request(
        base + path, data=body, headers=headers or {}, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _post_json(
    base: str, path: str, payload: dict, headers: dict | None = None
) -> tuple[int, dict]:
    hdrs = {"Content-Type": "application/json"}
    hdrs.update(headers or {})
    code, body = _req(
        base, path, "POST", hdrs, json.dumps(payload).encode("utf-8")
    )
    try:
        return code, json.loads(body.decode("utf-8") or "{}")
    except ValueError:
        return code, {"_raw": body.decode("utf-8", "replace")}


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
        server._oauth["codes"].clear()
        server._oauth["expected_states"].clear()
    server._drop_paused()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _status(base: str) -> str:
    _, body = _req(base, "/api/status")
    return json.loads(body.decode("utf-8")).get("status")


# --- checks -----------------------------------------------------------------


def check_origin_gate() -> None:
    httpd, base = _start()
    try:
        # Foreign and null Origins are refused on GET *and* POST.
        code, _ = _req(base, "/api/status", headers={"Origin": "https://evil.example"})
        assert code == 403, code
        code, _ = _req(base, "/api/status", headers={"Origin": "null"})
        assert code == 403, code
        code, body = _post_json(
            base, "/api/oauth/state", {"state": "m20-evil"},
            headers={"Origin": "https://evil.example"},
        )
        assert code == 403, (code, body)

        # The extension, the server's own page, and headerless callers pass.
        code, _ = _req(
            base, "/api/status",
            headers={"Origin": "chrome-extension://abcdefgh"},
        )
        assert code == 200, code
        code, _ = _req(base, "/api/status")  # navigation / CLI shape
        assert code == 200, code
        for origin in (None, "chrome-extension://abcdefgh", base):
            hdrs = {"Origin": origin} if origin else {}
            code, body = _post_json(
                base, "/api/oauth/state", {"state": "m20-ok"}, headers=hdrs
            )
            assert code == 200, (origin, code, body)
        print("origin gate OK: foreign/null refused, extension/self/headerless pass")
    finally:
        httpd.shutdown()


def check_content_type() -> None:
    httpd, base = _start()
    try:
        # text/plain JSON is the CSRF "simple request" shape — 415, no run.
        code, body = _req(
            base, "/api/run", "POST",
            {"Content-Type": "text/plain"},
            json.dumps({"phase": "gaps", "jds": []}).encode("utf-8"),
        )
        assert code == 415, (code, body)
        assert _status(base) == "idle", "a rejected POST must never start a run"

        # /api/resume wants octet-stream, not JSON.
        code, body = _req(
            base, "/api/resume", "POST",
            {"Content-Type": "application/json", "X-Filename": "x.txt"},
            b"{}",
        )
        assert code == 415, (code, body)
        print("content-type OK: text/plain POST + wrong resume type refused")
    finally:
        httpd.shutdown()


def check_skills_containment() -> None:
    httpd, base = _start()
    try:
        outside = str(Path.home() / "outside-m20.json")
        code, body = _post_json(base, "/api/run", {
            "phase": "gaps", "jds": [], "use_llm": False,
            "skills_path": outside,
        })
        assert code == 400, (code, body)
        assert "repo root or the OS temp dir" in body.get("error", ""), body
        assert _status(base) == "idle", "a refused skills_path must not run"

        code, body = _post_json(base, "/api/run", {
            "phase": "gaps", "jds": [], "use_llm": False,
            "skills_path": str(REPO_ROOT / "pyproject.toml"),
        })
        assert code == 400, (code, body)
        assert ".json" in body.get("error", ""), body
        print("skills_path containment OK: outside-repo and non-json refused")
    finally:
        httpd.shutdown()


def check_panel_transport_rule() -> None:
    js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")
    assert "function normalizeServer" in js, "serverBase validation missing"
    assert re.search(r'url\.protocol === "http:"', js), "http rule missing"
    assert "use https://" in js, "https requirement not surfaced to the user"
    assert "normalizeServer(stored.serverBase)" in js, (
        "loadState must validate the stored serverBase too"
    )
    print("panel transport rule OK: normalizeServer + loadState validation")


def main() -> None:
    check_origin_gate()
    check_content_type()
    check_skills_containment()
    check_panel_transport_rule()
    print("m20_check: PASS")


if __name__ == "__main__":
    main()
