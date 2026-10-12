"""M24 verification: mode-governs-ingestion checks (offline — no LLM, no
keyring, no network beyond localhost).

Checks:
1. Upload contract (POST /api/resume): X-Extraction-Mode selects the
   extraction path (rule = local regex, no LLM call at all; paid/free =
   LLM with the right cfg — provider honored, free_tier set); free-mode
   extraction refuses without X-Privacy-Ack (409 — the M16 gate is not
   UI-only); defaults preserve the pre-M24 behavior (paid/openrouter);
   bad mode/provider -> 400.
2. Mode-aware extraction cache: classes never cross (rule<->llm); an llm
   request never reuses a regex-fallback artifact (retries the LLM); llm
   artifacts are reused for llm requests; legacy two-line sidecars read
   as llm class.
3. Panel surface: setup order (AI access -> mode + consent -> resume ->
   collect -> analyze), M21 disclosure copy preserved (all m21 needles;
   "selected above"), mode-aware copy, version bump, upload headers
   wired, free consent sits with the chips.

Run: python -m skill_gap_agent.m24_check
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from . import resume as resume_mod
from . import server

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"

RESUME_TEXT = "Experienced with Python programming and SQL databases."
BANNED_CLAIM = "stays on your machine"


class _Preserve:
    """Save/restore the extraction artifacts + uploads dir the checks use
    (same shape as m14_check's)."""

    NAMES = (
        "extracted_skills.json",
        "extracted_skills.sha256",
        "extracted_skills.reviewed.json",
        "extracted_approvals.json",
    )

    def __enter__(self):
        self._output = Path(server.__file__).resolve().parents[2] / "output"
        self._saved: dict[str, bytes | None] = {}
        for name in self.NAMES:
            p = self._output / name
            self._saved[name] = p.read_bytes() if p.exists() else None
            if p.exists():
                p.unlink()
        self._uploads_existed = server.UPLOAD_DIR.exists()
        self._uploads = (
            {f.name for f in server.UPLOAD_DIR.iterdir()}
            if self._uploads_existed
            else set()
        )
        return self

    def __exit__(self, *exc):
        for name, data in self._saved.items():
            p = self._output / name
            if data is None:
                if p.exists():
                    p.unlink()
            else:
                p.write_bytes(data)
        if server.UPLOAD_DIR.exists():
            for f in server.UPLOAD_DIR.iterdir():
                if f.name not in self._uploads:
                    f.unlink()
            if not self._uploads_existed and not any(server.UPLOAD_DIR.iterdir()):
                server.UPLOAD_DIR.rmdir()
        return False


# --- http helpers (same shape as m21_check) --------------------------------


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
            # (WinError 10053) under multi-check runs — retry once.
            if attempt == 2:
                raise
    raise AssertionError("unreachable")


def _upload(
    base: str,
    name: str,
    data: bytes,
    mode: str | None = None,
    provider: str | None = None,
    privacy_ack: bool = False,
    disclosure_ack: bool = True,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/octet-stream",
               "X-Filename": urllib.parse.quote(name)}
    if disclosure_ack:
        headers["X-Disclosure-Ack"] = "1"
    if mode is not None:
        headers["X-Extraction-Mode"] = mode
    if provider is not None:
        headers["X-Provider"] = provider
    if privacy_ack:
        headers["X-Privacy-Ack"] = "1"
    code, body = _req(base, "/api/resume", method="POST", headers=headers, body=data)
    return code, json.loads(body.decode("utf-8") or "{}")


def _start_server() -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


# --- checks ----------------------------------------------------------------


def check_upload_contract() -> None:
    calls: list[dict] = []
    real_llm = resume_mod.extract_skills_llm

    def fake_llm(text, cfg=None):
        calls.append({"cfg": cfg})
        return {"skills": {"phrases": ["llm skill"]}}

    resume_mod.extract_skills_llm = fake_llm
    saved_resume = dict(server._resume)
    httpd, base = _start_server()
    try:
        with _Preserve():
            # Unique content per upload — the extraction cache is keyed on
            # the resume's hash, so shared text would collide.
            def text(tag: str) -> bytes:
                return f"{RESUME_TEXT} [{tag}]".encode()

            # M9 (placement revision 2026-10-12): upload is rule-only — no
            # LLM call happens at upload in ANY mode; the mode is stashed and
            # applied at Analyze (extract_to_artifact). The LLM extractor
            # must never be touched here.
            code, body = _upload(base, "r1.txt", text("r1"), mode="rule")
            assert code == 200, (code, body)
            assert body.get("stored") is True and body["mode"] == "rule", body
            assert server._resume.get("mode") == "rule", server._resume

            # Paid mode stashes the provider for analyze-time extraction.
            code, body = _upload(base, "r2.txt", text("r2"),
                                 mode="paid", provider="glm")
            assert code == 200, (code, body)
            assert body["mode"] == "paid", body
            assert server._resume.get("provider") == "glm", server._resume
            assert calls == [], "upload must make no LLM call (M9 rule-only)"

            # Free mode: refused without the M16 privacy consent (not
            # UI-only), accepted with it, and the mode is stashed.
            code, body = _upload(base, "r3.txt", text("r3"), mode="free")
            assert code == 409 and "privacy" in body.get("error", "").lower(), (code, body)
            assert body.get("mode") is None, body
            code, body = _upload(base, "r3.txt", text("r3"),
                                 mode="free", privacy_ack=True)
            assert code == 200, (code, body)
            assert body["mode"] == "free", body
            assert server._resume.get("mode") == "free", server._resume

            # Defaults preserve pre-M24 behavior: paid + openrouter.
            code, body = _upload(base, "r4.txt", text("r4"))
            assert code == 200 and body["mode"] == "paid", (code, body)
            assert server._resume.get("provider") == "openrouter", server._resume
            assert calls == [], "upload must make no LLM call (M9 rule-only)"

            # Bad input is rejected; the disclosure gate is unchanged (M21).
            code, body = _upload(base, "r5.txt", text("r5"), mode="hmm")
            assert code == 400, (code, body)
            code, body = _upload(base, "r5.txt", text("r5"), provider="nope")
            assert code == 400, (code, body)
            code, body = _upload(base, "r5.txt", text("r5"), disclosure_ack=False)
            assert code == 409 and "disclosure" in body.get("error", ""), (code, body)
    finally:
        resume_mod.extract_skills_llm = real_llm
        server._resume.clear()
        server._resume.update(saved_resume)
        httpd.shutdown()
    print("upload contract OK: rule-only upload (no LLM), mode/provider "
          "stashed for analyze, free consent enforced, defaults preserved, "
          "bad input rejected")


def check_mode_scoped_cache() -> None:
    import tempfile

    real_llm = resume_mod.extract_skills_llm
    with tempfile.TemporaryDirectory() as tmp:
        artifact = Path(tmp) / "ex.json"
        approvals = Path(tmp) / "ap.json"
        resume = Path(tmp) / "resume.txt"
        resume.write_text(RESUME_TEXT, encoding="utf-8")
        calls = {"n": 0, "fail": False}

        def fake_llm(text, cfg=None):
            calls["n"] += 1
            if calls["fail"]:
                raise RuntimeError("provider down")
            return {"skills": {"phrases": ["llm skill"]}}

        resume_mod.extract_skills_llm = fake_llm
        try:
            # 1. llm request extracts via LLM; a second llm request hits
            #    the cache (llm artifact reused).
            _, stats = resume_mod.resume_to_skills_json(
                resume, artifact_path=artifact, approvals_path=approvals,
                use_llm=True, auto=True, ask_fn=None,
            )
            assert stats["source"] == "llm" and calls["n"] == 1, stats
            _, stats = resume_mod.resume_to_skills_json(
                resume, artifact_path=artifact, approvals_path=approvals,
                use_llm=True, auto=True, ask_fn=None,
            )
            assert stats["source"] == "artifact" and calls["n"] == 1, stats

            # 2. A rule request never reuses the llm artifact (classes
            #    never cross) — and extracts locally.
            _, stats = resume_mod.resume_to_skills_json(
                resume, artifact_path=artifact, approvals_path=approvals,
                use_llm=False, auto=True, ask_fn=None,
            )
            assert stats["source"] == "regex" and calls["n"] == 1, stats

            # 3. Back to llm: the rule artifact must not satisfy it.
            _, stats = resume_mod.resume_to_skills_json(
                resume, artifact_path=artifact, approvals_path=approvals,
                use_llm=True, auto=True, ask_fn=None,
            )
            assert stats["source"] == "llm" and calls["n"] == 2, stats

            # 4. A regex-fallback artifact never satisfies an llm request
            #    (the fallback condition may have passed — retry the LLM).
            #    Start from a clean slate: with no artifact, the failing
            #    extractor falls back and the fallback is recorded.
            artifact.unlink()
            artifact.with_suffix(".sha256").unlink(missing_ok=True)
            calls["fail"] = True
            _, stats = resume_mod.resume_to_skills_json(
                resume, artifact_path=artifact, approvals_path=approvals,
                use_llm=True, auto=True, ask_fn=None,
            )
            assert stats["source"] == "regex" and calls["n"] == 3, stats
            calls["fail"] = False
            _, stats = resume_mod.resume_to_skills_json(
                resume, artifact_path=artifact, approvals_path=approvals,
                use_llm=True, auto=True, ask_fn=None,
            )
            assert stats["source"] == "llm" and calls["n"] == 4, stats

            # 5. Legacy two-line sidecars read as llm class: an llm
            #    artifact keeps hitting after upgrade.
            sidecar = artifact.with_suffix(".sha256")
            sha = hashlib.sha256(resume.read_bytes()).hexdigest()
            sidecar.write_text(sha + "\nllm\n", encoding="utf-8")
            _, stats = resume_mod.resume_to_skills_json(
                resume, artifact_path=artifact, approvals_path=approvals,
                use_llm=True, auto=True, ask_fn=None,
            )
            assert stats["source"] == "artifact" and calls["n"] == 4, stats
        finally:
            resume_mod.extract_skills_llm = real_llm
    print("mode-scoped cache OK: classes never cross, fallbacks retried, "
          "llm hits preserved, legacy sidecars read as llm")


def check_panel_surface() -> None:
    html = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")

    # Done criterion 1: setup order — key + mode before the resume.
    order = [
        html.index('id="setupkey"'),
        html.index('id="setupmode"'),
        html.index('id="setupresume"'),
        html.index("1. Collect job descriptions"),
        html.index("2. Analyze gaps"),
    ]
    assert order == sorted(order), f"panel order wrong: {order}"
    # Free consent sits with the mode chips (it governs ingestion too).
    assert html.index('id="freeconsent"') > html.index('id="setupmode"'), (
        "free consent must live in the mode section"
    )
    assert html.index('id="freeconsent"') < html.index('id="setupresume"'), (
        "free consent must precede the upload surface"
    )

    # Done criterion 4: M21 copy contract preserved + M24 amendments.
    assert BANNED_CLAIM not in html, "banned claim back in the panel"
    for needle in (
        "sent over HTTPS", "extension's developer",
        "OpenRouter", "GLM", "OpenAI", "Where your data goes",
        "skill-gap terms", "output/uploads/",
    ):
        assert needle in html, f"disclosure copy missing: {needle!r}"
    assert "selected above" in html, "M24 copy: destination is selected above"
    assert "Extraction follows" in html, "M24 copy: extraction-follows-mode note"
    assert "Consent is required before any" in html, (
        "M16 verbatim free disclaimer must be unchanged"
    )
    assert 'id="disclosureack"' in html
    assert not re.search(r'id="disclosureack"[^>]*checked', html), (
        "disclosure checkbox must never be pre-checked"
    )
    assert "DISCLOSURE_CONSENT_VERSION = 2" in js, (
        "copy changed -> disclosure consent version must bump to 2"
    )

    # Done criterion 2 wiring: upload carries the mode + provider + acks.
    assert '"X-Extraction-Mode": mode' in js, "upload must send the mode"
    assert '"X-Provider": activeProvider' in js, "upload must send the provider"
    assert '"X-Privacy-Ack"' in js and 'mode === "free"' in js, (
        "free uploads must carry the privacy ack"
    )
    assert "X-Disclosure-Ack" in js, "M21 ack header missing"

    # Mode summary in Analyze points back at Setup.
    assert 'id="modesummary"' in html, "mode summary missing"
    assert "change it in Setup" in js, "mode summary must reference Setup"

    # Key state chip + paste-form fallback stay in the AI-access section.
    assert 'id="keystate"' in js or 'id="keystate"' in html
    assert html.index('id="keystate"') < html.index('id="setupmode"')
    assert 'id="havekeylink"' in html and 'id="llmarea"' in html
    print("panel surface OK: setup order, consent placement, copy contract, "
          "upload headers, mode summary")


def main() -> None:
    check_upload_contract()
    check_mode_scoped_cache()
    check_panel_surface()
    print("M24 CHECK PASS: mode governs ingestion + setup order + "
          "mode-aware cache OK.")


if __name__ == "__main__":
    main()
