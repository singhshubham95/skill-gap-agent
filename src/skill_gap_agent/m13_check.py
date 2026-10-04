"""M13 verification: extension server-contract checks (offline — no LLM, no network).

Checks:
1. cli.py wiring complete (the M10/M11 completion): set_stage_listener/_stage
   exist and the graph contains the oss + pause nodes.
2. extension/manifest.json is valid MV3 with side panel + content script and
   every referenced file exists; the plan iframe allows popups (so plan
   links can open in new tabs) and a Reopen plan control exists.
3. Two-phase flow through the real server + real graph (stubbed
   judge/synthesis/oss at the cli seams): POST /api/run phase "gaps" with
   captured JDs -> status "paused", output/captured_jds/ written in the
   bookmarklet shape, GET /api/gaps serves ranked gaps; POST phase "plan" ->
   done, plan.html carries projects + Good-First-Issues with every link
   targeting a new tab (link-policy fix 2026-10-04), captured JD links
   resolve via /jds/; a second phase "plan" -> 409 (no paused run). The
   judge-reuse path runs with output/graph.json absent (deterministic stub
   scores).

Run: python -m skill_gap_agent.m13_check

Note (same as m11_check): this check rewrites output/plan.md, plan.html,
gaps.json, synthesis_report.json and output/captured_jds/ with stub content.
judge_report.json, graph.json and implied_skills.json are saved and restored.
"""

from __future__ import annotations

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

from . import server
from .judge import JudgeResult
from .oss import OssIssue
from .synthesis import SynthesizedProject

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"
OUTPUT_DIR = REPO_ROOT / "output"

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


# --- stubs for the LLM-touching seams (cli module globals) ------------------


def _fake_judge_all(sg, cfg=None, **kwargs):
    """One TRANSFERS_TO edge per unmatched target at a fixed 0.5 -> 'partial'."""
    results = []
    for t in sorted(sg.unmatched_target_skills()):
        cur = sg.current_skills()
        scores = []
        if cur:
            sg.add_transfers_to(cur[0], t, 0.5, "fake transfer")
            scores = [{"skill": cur[0], "confidence": 0.5, "rationale": "fake transfer"}]
        results.append(JudgeResult(target=t, scores=scores))
    return results


def _fake_synthesize(sg, gaps, top_n=5, cfg=None):
    out = []
    for g in gaps:
        if g.verdict in ("bridge", "alt-bridged", "held"):
            continue
        if len(out) >= top_n:
            break
        out.append(
            SynthesizedProject(
                gap=g,
                title=f"Project for {g.target}",
                description=f"Reuse existing skills while learning {g.target}.",
                why="fake",
            )
        )
    return out


def _fake_oss(sg, gaps, top_n=5, cfg=None, use_llm=True, **kwargs):
    out: dict[str, list] = {}
    for g in gaps:
        if g.verdict in ("bridge", "alt-bridged", "held"):
            continue
        if len(out) >= top_n:
            break
        out[g.target] = [
            OssIssue(
                gap=g.target,
                title=f"Good first issue for {g.target}",
                url=f"https://github.com/example/repo/issues/{len(out) + 1}",
                repo="example/repo",
                labels=["good first issue"],
                updated_at="2026-09-01T00:00:00Z",
            )
        ]
    return out


class _Preserve:
    """Save/restore real output artifacts the stub run overwrites."""

    NAMES: ClassVar[list[str]] = [
        "judge_report.json",
        "graph.json",
        "implied_skills.json",
    ]

    def __enter__(self):
        self._saved: dict[str, bytes | None] = {}
        for name in self.NAMES:
            p = OUTPUT_DIR / name
            self._saved[name] = p.read_bytes() if p.exists() else None
        # graph.json must be absent during the run: judge-reuse copies its
        # TRANSFERS_TO edges, and real seed edges would make stub scores
        # non-deterministic.
        for name in self.NAMES:
            p = OUTPUT_DIR / name
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


# --- checks -----------------------------------------------------------------


def check_cli_wiring() -> None:
    from . import cli as _cli

    assert hasattr(_cli, "set_stage_listener"), "cli.set_stage_listener missing"
    assert hasattr(_cli, "_stage"), "cli._stage missing"
    seen: list[str] = []
    _cli.set_stage_listener(seen.append)
    try:
        _cli._stage("judge")
    finally:
        _cli.set_stage_listener(None)
    assert seen == ["judge"], seen

    nodes = set(_cli.build_app().get_graph().nodes)
    assert {"pause", "synthesize", "oss", "output"} <= nodes, nodes
    print("cli wiring OK: stage listener + pause/oss nodes in the graph")


def check_extension_manifest() -> None:
    manifest = json.loads(
        (EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["manifest_version"] == 3, manifest["manifest_version"]
    assert manifest["side_panel"]["default_path"] == "sidepanel.html"
    assert "sidePanel" in manifest["permissions"], manifest["permissions"]
    assert "storage" in manifest["permissions"], manifest["permissions"]
    hosts = manifest["host_permissions"]
    assert any("localhost" in h for h in hosts), hosts
    assert any("127.0.0.1" in h for h in hosts), hosts
    refs = ["background.js", "content.js", "sidepanel.html", "sidepanel.js",
            "sidepanel.css"]
    for cs in manifest.get("content_scripts", []):
        refs.extend(cs.get("js", []))
    for rel in refs:
        assert (EXTENSION_DIR / rel).is_file(), f"missing extension/{rel}"

    panel = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    iframe = re.search(r'<iframe\b[^>]*id="planframe"[^>]*>', panel)
    assert iframe, "sidepanel.html: planframe iframe missing"
    assert "allow-popups" in iframe.group(0), iframe.group(0)
    assert "allow-popups-to-escape-sandbox" in iframe.group(0), iframe.group(0)
    assert 'id="reopen"' in panel, "sidepanel.html: Reopen plan control missing"
    js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")
    assert "$(\"reopen\")" in js, "sidepanel.js: Reopen plan not wired"
    print(f"manifest OK: MV3 side panel + content script ({len(refs)} files)")


def check_two_phase_flow() -> None:
    from . import cli as _cli

    tmp = Path(tempfile.mkdtemp(prefix="m13-"))
    skills = tmp / "skills.json"
    skills.write_text(
        json.dumps({"skills": ["Python programming experience", "SQL databases"]}),
        encoding="utf-8",
    )

    real = (
        _cli.judge_all_unmatched,
        _cli.synthesize_for_gaps,
        _cli.source_oss_for_gaps,
    )
    _cli.judge_all_unmatched = _fake_judge_all
    _cli.synthesize_for_gaps = _fake_synthesize
    _cli.source_oss_for_gaps = _fake_oss

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    with server._lock:
        server._run.update(
            status="idle", stage=None, phase=None,
            started_at=None, finished_at=None, error=None,
        )
    server._drop_paused()

    try:
        with _Preserve():
            # Phase 1: analyze gaps over two captured JDs.
            code, body = _post(
                base,
                "/api/run",
                {
                    "phase": "gaps",
                    "jds": JD_FIXTURES,
                    "skills_path": str(skills),
                    "top_n": 2,
                    "reuse_judged": True,
                },
            )
            assert code == 202, (code, body)
            assert _wait_status(base, "paused") == "paused"

            captured = sorted(server.CAPTURED_DIR.glob("*.txt"))
            assert len(captured) == 2, [f.name for f in captured]
            lines = captured[0].read_text(encoding="utf-8").splitlines()
            assert lines[1].startswith("https://example.com/jobs/"), lines[:2]
            assert JD_FIXTURES[0]["text"] in captured[0].read_text(
                encoding="utf-8"
            ) or JD_FIXTURES[1]["text"] in captured[0].read_text(encoding="utf-8")

            code, gaps_body = _get_json(base, "/api/gaps")
            assert code == 200, (code, gaps_body)
            gaps = gaps_body.get("gaps") or []
            assert gaps, "expected ranked gaps"
            assert any(g["verdict"] == "partial" for g in gaps), gaps
            assert all("source_jds" in g and "gap_score" in g for g in gaps)
            targets = {g["target"] for g in gaps}
            assert len(targets) == len(gaps), "duplicate gap targets"
            print(f"gaps OK: {len(gaps)} ranked ({', '.join(sorted(targets))})")

            # Phase 2: generate plan from the paused run.
            code, body = _post(base, "/api/run", {"phase": "plan"})
            assert code == 202, (code, body)
            assert _wait_status(base, "done") == "done"

            code, html_doc = _get(base, "/plan.html")
            assert code == 200, code
            assert b"Recommended Projects" in html_doc, "plan.html missing projects"
            assert b"Good-First-Issues" in html_doc, "plan.html missing GFI section"
            assert b"https://github.com/example/repo/issues/" in html_doc

            # Link policy (2026-10-04 fix): every plan link must open in a
            # new tab, so a mis-click cannot navigate the side-panel iframe
            # away from the plan.
            anchors = re.findall(rb"<a\b[^>]*>", html_doc)
            assert anchors, "plan.html has no links"
            for a in anchors:
                assert b"target='_blank'" in a, a
                assert b"rel='noopener noreferrer'" in a, a
            print(f"link policy OK: {len(anchors)} links target new tabs")

            # Captured JD links resolve from output/captured_jds/ (not
            # data/jds/), and unknown names still 404.
            code, page = _get(base, "/jds/" + urllib.parse.quote(captured[0].name))
            assert code == 200, (code, captured[0].name)
            assert b"<pre>" in page, "jd viewer page malformed"
            try:
                _get(base, "/jds/no_such_jd.txt")
                raise AssertionError("expected 404 for unknown jd name")
            except urllib.error.HTTPError as e:
                assert e.code == 404, e.code
            print("jd viewer OK: captured JDs served from output/captured_jds/")
            print("plan OK: projects + Good-First-Issues rendered")

            # Phase 2 again: nothing left to resume.
            code, body = _post(base, "/api/run", {"phase": "plan"})
            assert code == 409, (code, body)
            assert "gaps" in body.get("error", ""), body
            print("guard OK: second phase 'plan' rejected with 409")
    finally:
        _cli.judge_all_unmatched, _cli.synthesize_for_gaps, _cli.source_oss_for_gaps = (
            real
        )
        httpd.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    check_cli_wiring()
    check_extension_manifest()
    check_two_phase_flow()
    print(
        "M13 CHECK PASS: cli wiring + manifest + two-phase gaps/plan flow OK."
    )


if __name__ == "__main__":
    main()
