"""M14 verification: self-serve setup checks (offline — no LLM, no keyring,
no network beyond localhost).

Checks:
1. Resume upload endpoint: raw-bytes POST validates size/type/magic bytes,
   stores under output/uploads/, extracts immediately (forced regex path —
   deterministic), reports {filename, skills, source}; the SHA-256 sidecar
   keys the extraction artifact (same resume -> cache hit, new resume ->
   re-extract); sanitized filenames only (traversal rejected).
2. Key endpoint: "remember" -> secrets.set_secret (stubbed — the real OS
   keyring is never touched), "session" -> process env; unknown provider /
   empty key -> 400; GET /api/providers reports key_set booleans and no
   endpoint ever returns key material.
3. Skills/provider resolution precedence: body skills_path -> uploaded
   resume -> --skills default; provider validated against llm.PROVIDERS.
4. Panel + launcher surface: resume file input, password key field,
   provider dropdown, no key material in chrome.storage, and
   tools/start-server.bat exists.

Run: python -m skill_gap_agent.m14_check

Note (same as m11/m13 checks): rewrites output/extracted_skills* with stub
extraction content and output/uploads/ test files; both are restored or
cleaned up afterwards.
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
from typing import ClassVar

from . import resume as resume_mod
from . import server

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"
TOOLS_DIR = REPO_ROOT / "tools"
OUTPUT_DIR = REPO_ROOT / "output"

RESUME_A = "Experienced with Python programming and SQL databases and kafka streaming data pipelines."
RESUME_B = "Worked on graph databases neo4j and data governance policies."


class _Preserve:
    """Save/restore the extraction artifacts + uploads dir the checks use."""

    NAMES: ClassVar[list[str]] = [
        "extracted_skills.json",
        "extracted_skills.sha256",
        "extracted_skills.reviewed.json",
        "extracted_approvals.json",
    ]

    def __enter__(self):
        self._saved: dict[str, bytes | None] = {}
        for name in self.NAMES:
            p = OUTPUT_DIR / name
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
            p = OUTPUT_DIR / name
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


# --- http helpers -----------------------------------------------------------


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


def _upload(base: str, name: str, data: bytes) -> tuple[int, dict]:
    code, body = _request(
        base,
        "/api/resume",
        data,
        {
            "Content-Type": "application/octet-stream",
            "X-Filename": urllib.parse.quote(name),
        },
    )
    return code, json.loads(body.decode("utf-8") or "{}")


def _get(base: str, path: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return resp.status, resp.read()


def _get_json(base: str, path: str) -> tuple[int, dict]:
    code, body = _get(base, path)
    return code, json.loads(body.decode("utf-8"))


def _start_server() -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


# --- checks -----------------------------------------------------------------


def check_resume_endpoint() -> None:
    # Force the deterministic no-LLM extraction path even on machines that
    # have a real key configured (the check must stay offline and fast).
    real_llm = resume_mod.extract_skills_llm

    def _offline(*_a, **_k):
        raise RuntimeError("m14_check: LLM extraction disabled")

    resume_mod.extract_skills_llm = _offline
    real_max = server.MAX_RESUME_BYTES
    httpd, base = _start_server()
    try:
        with _Preserve():
            code, body = _upload(base, "resume a.txt", RESUME_A.encode("utf-8"))
            assert code == 200, (code, body)
            assert body["source"] == "regex", body  # offline -> regex fallback
            assert body["skills"] and body["skills"] > 0, body
            sha_a = hashlib.sha256(RESUME_A.encode("utf-8")).hexdigest()
            sidecar = OUTPUT_DIR / "extracted_skills.sha256"
            assert sidecar.exists(), "hash sidecar missing"
            # Sidecar line 1 = source hash, line 2 = extraction source (M15).
            assert sidecar.read_text(encoding="utf-8").splitlines()[0] == sha_a
            artifact_a = (OUTPUT_DIR / "extracted_skills.json").read_bytes()

            # Same resume again -> cache hit (artifact path, no re-extract).
            code, body = _upload(base, "resume a.txt", RESUME_A.encode("utf-8"))
            assert code == 200 and body["source"] == "artifact", (code, body)

            # Different resume -> hash mismatch -> re-extract.
            code, body = _upload(base, "resume b.txt", RESUME_B.encode("utf-8"))
            assert code == 200, (code, body)
            assert body["source"] == "regex", body
            artifact_b = (OUTPUT_DIR / "extracted_skills.json").read_bytes()
            assert artifact_b != artifact_a, "second resume reused stale extraction"
            assert b"Graph" in artifact_b and b"Graph" not in artifact_a, (
                "extraction did not follow the new resume"
            )
            sha_b = hashlib.sha256(RESUME_B.encode("utf-8")).hexdigest()
            assert sidecar.read_text(encoding="utf-8").splitlines()[0] == sha_b

            # Status reports what a run will use.
            code, status = _get_json(base, "/api/status")
            assert code == 200, (code, status)
            assert status["skills"]["filename"] == "resume b.txt", status["skills"]

            # Type + size validation.
            code, body = _upload(base, "evil.exe", b"MZ junk")
            assert code == 415, (code, body)
            code, body = _upload(base, "fake.pdf", b"not a pdf")
            assert code == 415, (code, body)  # magic-byte sniff
            server.MAX_RESUME_BYTES = 64
            code, body = _upload(base, "big.txt", b"x" * 128)
            assert code == 413, (code, body)
            server.MAX_RESUME_BYTES = real_max

            # Filename sanitization: traversal name lands inside uploads/.
            code, body = _upload(
                base, "..\\..\\evil.txt", RESUME_A.encode("utf-8")
            )
            assert code == 200, (code, body)
            assert body["filename"] == "evil.txt", body
            assert (server.UPLOAD_DIR / "evil.txt").is_file()
            assert not (REPO_ROOT / "evil.txt").exists()
            assert not (REPO_ROOT.parent / "evil.txt").exists()
            print(
                "resume endpoint OK: upload + cache hit + re-extract + "
                "validation + sanitized names"
            )
    finally:
        resume_mod.extract_skills_llm = real_llm
        server.MAX_RESUME_BYTES = real_max
        httpd.shutdown()


def check_key_endpoint() -> None:
    from . import secrets as secrets_mod

    store: dict[str, str] = {}
    real_set, real_get = secrets_mod.set_secret, secrets_mod.get_secret

    def fake_set(env_name: str, value: str) -> None:
        store[env_name] = value

    def fake_get(env_name: str) -> str | None:
        return store.get(env_name) or real_get(env_name)

    secrets_mod.set_secret = fake_set
    secrets_mod.get_secret = fake_get
    httpd, base = _start_server()
    key = "sk-m14-test-not-a-real-key"
    try:
        # remember -> keyring seam (stubbed; real OS keyring never touched).
        code, body = _post_json(
            base,
            "/api/key",
            {"provider": "openrouter", "api_key": key, "remember": True},
        )
        assert code == 200, (code, body)
        assert body["stored"] == "keyring", body
        assert store.get("OPENROUTER_API_KEY") == key
        assert key not in json.dumps(body), "response echoed the key!"

        code, raw = _get(base, "/api/providers")
        assert code == 200, code
        assert key.encode("utf-8") not in raw, "providers endpoint leaked the key"
        providers = json.loads(raw.decode("utf-8"))["providers"]
        ids = {p["id"]: p for p in providers}
        assert ids["openrouter"]["key_set"] is True, providers
        assert set(ids) == {"openrouter", "glm", "openai"}, providers

        # session -> process env only, nothing stored anywhere.
        code, body = _post_json(
            base,
            "/api/key",
            {"provider": "glm", "api_key": "sk-session", "remember": False},
        )
        assert code == 200, (code, body)
        assert body["stored"] == "session", body
        assert "GLM_API_KEY" not in store, "session key must not be stored"
        try:
            assert server.os.environ.get("GLM_API_KEY") == "sk-session"
            code, providers = _get_json(base, "/api/providers")
            assert code == 200, (code, providers)
            assert key.encode("utf-8") not in json.dumps(providers).encode()
        finally:
            server.os.environ.pop("GLM_API_KEY", None)

        # Validation.
        code, body = _post_json(
            base, "/api/key", {"provider": "nope", "api_key": "x"}
        )
        assert code == 400, (code, body)
        code, body = _post_json(
            base, "/api/key", {"provider": "openrouter", "api_key": "  "}
        )
        assert code == 400, (code, body)
        print("key endpoint OK: keyring/session modes, validation, no key leakage")
    finally:
        secrets_mod.set_secret, secrets_mod.get_secret = real_set, real_get
        httpd.shutdown()


def check_skills_provider_resolution() -> None:
    server._resume.update(path=None, filename=None, count=None, source=None)
    assert server._resolve_skills({}) == Path(server.DEFAULT_SKILLS)

    fake = OUTPUT_DIR / "uploads" / "fake-resume.txt"
    server._resume.update(path=str(fake), filename="fake-resume.txt", count=3, source="regex")
    try:
        assert server._resolve_skills({}) == fake, "uploaded resume must win"
        assert server._resolve_skills({"skills_path": "data/x.json"}) == Path(
            "data/x.json"
        ), "explicit skills_path must win over the upload"
        described = server._describe_skills()
        assert described == {"filename": "fake-resume.txt", "count": 3, "source": "regex"}
    finally:
        server._resume.update(path=None, filename=None, count=None, source=None)

    assert server._resolve_provider({}) == "openrouter"
    assert server._resolve_provider({"provider": "glm"}) == "glm"
    try:
        server._resolve_provider({"provider": "nope"})
        raise AssertionError("expected ValueError for unknown provider")
    except ValueError:
        pass
    print("resolution OK: skills precedence + provider validation")


def check_panel_and_launcher() -> None:
    panel = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    assert 'id="resume"' in panel and ".pdf,.docx,.txt" in panel, "resume input missing"
    assert 'id="apikey" type="password"' in panel, "key field must be type=password"
    assert 'id="provider"' in panel, "provider dropdown missing"
    assert 'id="remember"' in panel, "remember checkbox missing"

    js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")
    # The key must never reach extension storage (plaintext in the profile).
    assert not re.search(
        r"chrome\.storage\.local\.set\([^)]*key", js, re.IGNORECASE | re.DOTALL
    ), "key material must never go into chrome.storage"
    assert '"/api/resume"' in js and '"/api/key"' in js, "panel missing setup calls"

    bat = (TOOLS_DIR / "start-server.bat").read_text(encoding="utf-8", errors="replace")
    assert "skill_gap_agent.server" in bat, "launcher must start the server"
    assert ".venv" in bat, "launcher should prefer the project venv"
    print("panel + launcher OK: resume input, key form, no key in storage, bat")


def main() -> None:
    check_resume_endpoint()
    check_key_endpoint()
    check_skills_provider_resolution()
    check_panel_and_launcher()
    print("M14 CHECK PASS: resume upload + key entry + resolution + panel/launcher OK.")


if __name__ == "__main__":
    main()
