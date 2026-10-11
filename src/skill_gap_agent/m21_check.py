"""M21 offline check — disclosure consent gate (server + panel) and the
accuracy of the data-disclosure copy (specs/12-extension.md §Data disclosure).

Run: python -m skill_gap_agent.m21_check
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from . import server

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"

BANNED_CLAIM = "stays on your machine"


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
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except OSError:
            # Windows intermittently aborts loopback connections
            # (WinError 10053) under multi-check runs — retry once; the
            # probes are idempotent (rejections and GETs only).
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def _upload(base: str, name: str, data: bytes, ack: bool) -> tuple[int, dict]:
    headers = {
        "Content-Type": "application/octet-stream",
        "X-Filename": urllib.parse.quote(name),
    }
    if ack:
        headers["X-Disclosure-Ack"] = "1"
    code, body = _req(base, "/api/resume", "POST", headers, data)
    return code, json.loads(body.decode("utf-8") or "{}")


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
    server._drop_paused()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


# --- checks -----------------------------------------------------------------


def check_resume_ack_gate() -> None:
    httpd, base = _start()
    try:
        # Without the ack header the upload is refused before any handling.
        code, body = _upload(base, "resume.txt", b"skills", ack=False)
        assert code == 409, (code, body)
        assert "disclosure" in body.get("error", ""), body

        # With the ack the request proceeds to the next gate (bad type 415)
        # — the ack itself is accepted.
        code, body = _upload(base, "resume.exe", b"skills", ack=True)
        assert code == 415, (code, body)
        print("resume ack gate OK: 409 without X-Disclosure-Ack, gate passes with it")
    finally:
        httpd.shutdown()


def check_disclosure_copy() -> None:
    html = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    ext_readme = (EXTENSION_DIR / "README.md").read_text(encoding="utf-8")
    root_readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    for name, text in (
        ("sidepanel.html", html),
        ("extension/README.md", ext_readme),
        ("README.md", root_readme),
    ):
        assert BANNED_CLAIM not in text, f"banned claim still in {name}"

    for needle in (
        "sent over HTTPS", "extension's developer",
        "OpenRouter", "GLM", "OpenAI", "Where your data goes",
    ):
        assert needle in html, f"disclosure copy missing from panel: {needle!r}"
    assert "skill-gap terms" in html, "GitHub flow not disclosed"
    print("disclosure copy OK: claim ban, named destinations, GitHub note")
    for name, text in (("extension/README.md", ext_readme), ("README.md", root_readme)):
        assert "extension's developer" in text, (
            f"accurate disclosure missing from {name}"
        )
        assert "output/uploads/" in text, f"locality half of the truth missing from {name}"


def check_panel_wiring() -> None:
    html = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")
    assert re.search(r'id="disclosureack"', html), "consent checkbox missing"
    assert not re.search(r'id="disclosureack"[^>]*checked', html), (
        "consent checkbox must never be pre-checked"
    )
    assert "DISCLOSURE_CONSENT_VERSION" in js, "consent versioning missing"
    assert "disclosureConsent" in js, "consent flag missing"
    assert "X-Disclosure-Ack" in js, "panel must send the ack header"
    assert js.count("disclosureAcked()") >= 2, (
        "upload and analyze must both gate on the disclosure consent"
    )
    print("panel wiring OK: versioned consent gates upload + analyze, ack header")


def main() -> None:
    check_resume_ack_gate()
    check_disclosure_copy()
    check_panel_wiring()
    print("m21_check: PASS")


if __name__ == "__main__":
    main()
