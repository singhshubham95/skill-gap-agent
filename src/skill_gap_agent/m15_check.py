"""M15 offline verification — LLM presence policy (specs/05-ai-caller.md).

Silent non-LLM output is the bug M15 fixes; these checks pin the fix:

1. check_vocabulary_and_panel — the provenance labels are defined once in
   llm.py; the panel carries the LLM toggle + degraded banner + Source
   column; the key never reaches chrome.storage.
2. check_pre_flight_refusal — LLM mode with no key is refused (409) before
   any work; Rule-based mode (use_llm: false) runs and everything it
   produces says so (unjudged rows, plan header, synthesis note, labels).
3. check_loud_degradation — LLM mode with a key but every LLM call failing
   mid-run: the run completes, /api/status carries llm_mode +
   degraded_reasons, failed targets render "unjudged" with
   "Rule-based (LLM unavailable - ...)" — never a measured 0.0 gap — and
   plan.html carries the warning + labels.
4. check_llm_mode_labels — a working (stubbed) LLM labels rows/sections
   "LLM"; a cache-reusing re-run labels them "LLM (cached)".
5. check_extraction_provenance — the extraction sidecar records how the
   artifact was produced, so cache hits label honestly.

All LLM seams are stubbed at the llm module boundary (judge/synthesis/oss
each `from .llm import judge`); GitHub search is stubbed at
oss.github_search_issues. Real pipeline code runs. Real output artifacts
are preserved and restored (same convention as m13/m14).
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import ClassVar

from . import judge as judge_mod
from . import llm as llm_mod
from . import oss as oss_mod
from . import resume as resume_mod
from . import server
from . import synthesis as synthesis_mod

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"
OUTPUT_DIR = REPO_ROOT / "output"

VOCAB = ("LLM (cached)", "LLM", "Rule-based")

JD_FIXTURES = [
    {
        "title": "Streaming Engineer",
        "url": "https://example.com/jobs/1",
        "text": "kafka streaming data pipelines kafka streaming data",
    },
    {
        "title": "Governance Analyst",
        "url": "https://example.com/jobs/2",
        "text": "data governance responsible ai data governance policies",
    },
]
SKILLS = {
    "skills": [
        "Python programming experience",
        "SQL databases",
        "data pipelines engineering",
    ]
}

RESUME_TEXT = (
    "Experienced with Python programming and SQL databases and "
    "kafka streaming data pipelines."
)


# --- llm seam stubs (judge/synthesis/oss import judge from .llm) ------------


def _llm_down(*_a, **_k):
    raise RuntimeError("m15: simulated LLM outage")


def _judge_ok(prompt, system="", cfg=None):
    """Every current skill scores 0.6 -> a real TRANSFERS_TO edge ('partial')."""
    return {
        "scores": [
            {"skill": s, "confidence": 0.6, "rationale": "m15 stub transfer"}
            for s in ("data pipelines engineering", "SQL databases",
                      "Python programming experience")
        ]
    }


def _synth_ok(prompt, system="", cfg=None):
    return {"title": "M15 stub project", "description": "desc", "why": "why"}


def _oss_filter_ok(prompt, system="", cfg=None):
    """Keep the first two candidate URLs the search stub put in the prompt."""
    urls = re.findall(r"https://github\.com/example/repo/issues/\d+", prompt)
    seen: list[str] = []
    for u in urls:
        if u not in seen:
            seen.append(u)
        if len(seen) >= 2:
            break
    return {
        "relevant": [{"url": u, "why": "m15 stub relevance"} for u in seen[:2]]
    }


def _stub_search(query, token=None, **_kw):
    def item(i: int) -> dict:
        return {
            "title": f"Stub issue {i}",
            "html_url": f"https://github.com/example/repo/issues/{i}",
            "repository_url": "https://api.github.com/repos/example/repo",
            "labels": [{"name": "good first issue"}],
            "updated_at": "2026-09-01T00:00:00Z",
            "body": "stub body",
        }

    return [item(1), item(2), item(3)]


class _Preserve:
    """Save/restore the real output artifacts the stub runs overwrite."""

    NAMES: ClassVar[list[str]] = [
        "judge_report.json",
        "graph.json",
        "implied_skills.json",
        "gaps.json",
        "plan.md",
        "plan.html",
        "synthesis_report.json",
        "oss_issues.json",
    ]

    def __enter__(self):
        self._saved: dict[str, bytes | None] = {}
        for name in self.NAMES:
            p = OUTPUT_DIR / name
            self._saved[name] = p.read_bytes() if p.exists() else None
            if p.exists():
                p.unlink()
        return self

    def __exit__(self, *exc):
        for name, data in self._saved.items():
            p = OUTPUT_DIR / name
            if data is None:
                if p.exists():
                    p.unlink()
            else:
                p.write_bytes(data)
        return False


# --- http helpers -----------------------------------------------------------


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


def _wait_status(base: str, want: str, timeout: float = 60.0) -> str:
    deadline = time.time() + timeout
    status = "?"
    while time.time() < deadline:
        code, body = _get_json(base, "/api/status")
        assert code == 200, (code, body)
        status = body.get("status", "?")
        if status in (want, "error"):
            if status == "error":
                raise AssertionError(f"run errored: {body.get('error')}")
            return status
        time.sleep(0.2)
    raise AssertionError(f"status never reached {want!r} (last={status!r})")


def _start() -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with server._lock:
        server._run.update(
            status="idle", stage=None, phase=None,
            started_at=None, finished_at=None, error=None,
            llm_mode=None, degraded_reasons=[],
        )
    server._drop_paused()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _run_body(tmp: Path, use_llm: bool, **extra) -> dict:
    skills = tmp / "skills.json"
    if not skills.exists():
        skills.write_text(json.dumps(SKILLS), encoding="utf-8")
    body = {
        "phase": "gaps",
        "jds": JD_FIXTURES,
        "skills_path": str(skills),
        "top_n": 3,
        "use_llm": use_llm,
    }
    body.update(extra)
    return body


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="m15-skills-"))


def _set_key_present(present: bool):
    llm_mod.get_secret = (lambda name: "m15-fake-key") if present else (lambda name: None)


# --- checks -----------------------------------------------------------------


def check_vocabulary_and_panel() -> None:
    assert llm_mod.LABEL_LLM == "LLM", llm_mod.LABEL_LLM
    assert llm_mod.LABEL_LLM_CACHED == "LLM (cached)", llm_mod.LABEL_LLM_CACHED
    assert llm_mod.LABEL_RULE == "Rule-based", llm_mod.LABEL_RULE
    assert (
        llm_mod.rule_unavailable_label("boom")
        == "Rule-based (LLM unavailable — boom)"
    )

    real_get = llm_mod.get_secret
    llm_mod.get_secret = lambda name: None
    try:
        try:
            llm_mod.require_api_key("openrouter")
            raise AssertionError("expected refusal with no key")
        except llm_mod.LLMError as e:
            assert "API key" in str(e) and "openrouter" in str(e), e
    finally:
        llm_mod.get_secret = real_get

    panel = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    assert re.search(r'id="usellm"[^>]*checked', panel), "LLM toggle missing"
    assert 'id="degraded"' in panel, "degraded banner missing"
    assert 'id="llmarea"' in panel, "key area missing"
    assert 'id="apikey" type="password"' in panel, "key field must be type=password"
    assert 'id="provider"' in panel and 'id="remember"' in panel
    assert "<th>Source</th>" in panel, "gap table needs the Source column"

    js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")
    assert re.search(r"use_llm:\s*\$\(\"usellm\"\)\.checked", js), (
        "run body must carry use_llm from the toggle"
    )
    assert "showDegraded" in js, "degraded banner not wired"
    assert '"/api/run"' in js
    # The key must never reach extension storage (plaintext in the profile).
    assert not re.search(
        r"chrome\.storage\.local\.set\([^)]*key", js, re.IGNORECASE | re.DOTALL
    ), "key material must never go into chrome.storage"
    print("vocabulary + panel OK: labels, toggle, banner, Source column, no key in storage")


def check_pre_flight_refusal() -> None:
    _set_key_present(False)
    tmp = _tmp()
    httpd, base = _start()
    try:
        with _Preserve():
            # LLM mode without a key: refused before any work.
            code, body = _post(base, "/api/run", _run_body(tmp, True))
            assert code == 409, (code, body)
            assert "API key" in body.get("error", ""), body
            code, status = _get_json(base, "/api/status")
            assert status.get("status") == "idle", status  # nothing started

            # Rule-based mode runs — and says so everywhere.
            code, body = _post(
                base, "/api/run", _run_body(tmp, False, reuse_judged=True)
            )
            assert code == 202, (code, body)
            assert _wait_status(base, "paused") == "paused"
            code, status = _get_json(base, "/api/status")
            assert status.get("llm_mode") == "rule-based", status
            assert not status.get("degraded_reasons"), status

            code, gaps_body = _get_json(base, "/api/gaps")
            gaps = gaps_body.get("gaps") or []
            assert gaps, "expected ranked gaps"
            for g in gaps:
                assert g["provenance"] == "Rule-based", g
                if g["verdict"] == "unjudged":
                    assert g["top_transfer_confidence"] is None, g
                else:
                    assert g["verdict"] in ("held", "unjudged"), g
            assert any(g["verdict"] == "unjudged" for g in gaps), gaps
            print(f"rule-based gaps OK: {len(gaps)} rows all labeled Rule-based")

            code, body = _post(base, "/api/run", {"phase": "plan"})
            assert code == 202, (code, body)
            assert _wait_status(base, "done") == "done"
            code, plan = _get(base, "/plan.html")
            assert b"Rule-based mode" in plan, "plan header must state the mode"
            assert b"project synthesis needs the LLM" in plan, plan[:500]
            assert b"Source: Rule-based" in plan
            assert b"Source: LLM</em>" not in plan, "non-LLM output labeled LLM!"
            print("rule-based plan OK: mode header + synthesis note + labels")
    finally:
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


def check_loud_degradation() -> None:
    real = (llm_mod.get_secret, judge_mod.judge, synthesis_mod.judge, oss_mod.judge)
    _set_key_present(True)  # pre-flight passes; calls fail mid-run
    judge_mod.judge = _llm_down
    synthesis_mod.judge = _llm_down
    oss_mod.judge = _llm_down
    oss_mod.github_search_issues = _stub_search
    tmp = _tmp()
    httpd, base = _start()
    try:
        with _Preserve():
            code, body = _post(
                base, "/api/run", _run_body(tmp, True, reuse_judged=True)
            )
            assert code == 202, (code, body)  # starts (key present)
            assert _wait_status(base, "paused") == "paused"
            code, status = _get_json(base, "/api/status")
            assert status.get("llm_mode") == "llm", status
            reasons = status.get("degraded_reasons") or []
            assert any(r["touchpoint"].startswith("judge(") for r in reasons), reasons

            code, gaps_body = _get_json(base, "/api/gaps")
            gaps = gaps_body.get("gaps") or []
            unjudged = [g for g in gaps if g["verdict"] == "unjudged"]
            assert unjudged, gaps
            for g in unjudged:
                assert g["top_transfer_confidence"] is None, g
                assert g["provenance"].startswith("Rule-based (LLM unavailable"), g
            print(f"degraded gaps OK: {len(unjudged)} rows labeled, none fake-scored")

            code, body = _post(base, "/api/run", {"phase": "plan"})
            assert code == 202, (code, body)
            assert _wait_status(base, "done") == "done"
            code, status = _get_json(base, "/api/status")
            reasons = status.get("degraded_reasons") or []
            assert any(r["touchpoint"].startswith("synthesis(") for r in reasons), reasons
            assert any(r["touchpoint"].startswith("oss-filter(") for r in reasons), reasons

            code, plan = _get(base, "/plan.html")
            assert b"LLM mode" in plan
            assert b"fell back to rule-based output" in plan, "degraded warning missing"
            assert b"Not generated for" in plan, "failed synthesis placeholder missing"
            assert b"LLM unavailable" in plan, "loud label missing"
            assert b"Source: LLM</em>" not in plan, "failed output labeled LLM!"
            print("degraded plan OK: warning block + per-section labels")
    finally:
        (llm_mod.get_secret, judge_mod.judge, synthesis_mod.judge, oss_mod.judge) = real
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


def check_llm_mode_labels() -> None:
    real = (llm_mod.get_secret, judge_mod.judge, synthesis_mod.judge, oss_mod.judge)
    _set_key_present(True)
    judge_mod.judge = _judge_ok
    synthesis_mod.judge = _synth_ok
    oss_mod.judge = _oss_filter_ok
    oss_mod.github_search_issues = _stub_search
    tmp = _tmp()
    httpd, base = _start()
    try:
        with _Preserve():
            # Fresh LLM run -> labels "LLM".
            code, body = _post(
                base, "/api/run", _run_body(tmp, True, reuse_judged=True)
            )
            assert code == 202, (code, body)
            assert _wait_status(base, "paused") == "paused"
            code, gaps_body = _get_json(base, "/api/gaps")
            gaps = gaps_body.get("gaps") or []
            # "partial" rows come from real TRANSFERS_TO edges (held rows
            # are matched, not judged — they carry Rule-based labels).
            judged = [g for g in gaps if g["verdict"] == "partial"]
            assert judged, gaps
            assert all(g["top_transfer_skill"] for g in judged), judged
            assert all(g["provenance"] == "LLM" for g in judged), judged

            code, body = _post(base, "/api/run", {"phase": "plan"})
            assert code == 202, (code, body)
            assert _wait_status(base, "done") == "done"
            code, plan = _get(base, "/plan.html")
            assert b"Source: LLM</em>" in plan, plan[:800]
            assert b"LLM mode" in plan
            code, status = _get_json(base, "/api/status")
            assert not status.get("degraded_reasons"), status

            # Re-run reusing judge edges + the OSS cache -> "LLM (cached)".
            code, body = _post(
                base, "/api/run", _run_body(tmp, True, reuse_judged=True)
            )
            assert code == 202, (code, body)
            assert _wait_status(base, "paused") == "paused"
            code, gaps_body = _get_json(base, "/api/gaps")
            gaps = gaps_body.get("gaps") or []
            judged = [g for g in gaps if g["verdict"] == "partial"]
            assert judged, gaps
            assert all(g["provenance"] == "LLM (cached)" for g in judged), judged

            code, body = _post(base, "/api/run", {"phase": "plan"})
            assert code == 202, (code, body)
            assert _wait_status(base, "done") == "done"
            code, plan = _get(base, "/plan.html")
            assert b"Source: LLM (cached)</em>" in plan, plan[:800]
            print("llm labels OK: fresh 'LLM', cache-reuse 'LLM (cached)'")
    finally:
        (llm_mod.get_secret, judge_mod.judge, synthesis_mod.judge, oss_mod.judge) = real
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


def check_extraction_provenance() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="m15-resume-"))
    real_llm = resume_mod.extract_skills_llm
    resume_mod.extract_skills_llm = _llm_down  # force the regex path
    try:
        resume = tmp / "r.txt"
        resume.write_text(RESUME_TEXT, encoding="utf-8")
        artifact = tmp / "extracted_skills.json"
        approvals = tmp / "approvals.json"
        kwargs = {
            "artifact_path": artifact,
            "approvals_path": approvals,
            "use_llm": True,
            "auto": True,
            "ask_fn": None,
        }
        _json_path, stats = resume_mod.resume_to_skills_json(resume, **kwargs)
        assert stats["source"] == "regex", stats
        assert stats["provenance"] == "Rule-based", stats
        assert resume_mod.extracted_provenance(artifact) == "regex"

        # Cache hit of a regex artifact must not read as LLM output.
        _json_path, stats = resume_mod.resume_to_skills_json(resume, **kwargs)
        assert stats["source"] == "artifact", stats
        assert stats["provenance"] == "Rule-based", stats

        # An artifact produced by the LLM reports "LLM (cached)" when reused.
        sha = hashlib.sha256(resume.read_bytes()).hexdigest()
        artifact.with_suffix(".sha256").write_text(sha + "\nllm\n", encoding="utf-8")
        _json_path, stats = resume_mod.resume_to_skills_json(resume, **kwargs)
        assert stats["source"] == "artifact", stats
        assert stats["provenance"] == "LLM (cached)", stats
        print("extraction provenance OK: sidecar line 2 labels cache hits")
    finally:
        resume_mod.extract_skills_llm = real_llm
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    check_vocabulary_and_panel()
    check_pre_flight_refusal()
    check_loud_degradation()
    check_llm_mode_labels()
    check_extraction_provenance()
    print("M15 CHECK PASS: LLM presence policy — refusal, loud degradation, labels OK.")


if __name__ == "__main__":
    main()
