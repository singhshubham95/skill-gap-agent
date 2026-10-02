"""M11 verification: local UI server checks (offline-friendly).

Checks (no network beyond localhost, no LLM required):
1. server.py imports; _jd_files() lists data/jds/*.txt|*.md.
2. GET / returns HTML with JD list slot + Generate button + status poll.
3. GET /api/jds returns the folder contents as JSON.
4. POST /api/run starts a background run (stubbed pipeline) -> 202;
   second POST while running -> 409; GET /api/status carries stage -> done.
5. GET /plan.html serves output/plan.html once the stub writes it.
6. GET /jds/<name> serves JD text; render_plan_html links source JDs
   when jd_files is passed, plain text without it.

Run: python -m skill_gap_agent.m11_check
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from . import server


def _get(base: str, path: str) -> tuple[int, bytes, str]:
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return resp.status, resp.read(), resp.headers.get("Content-Type", "")


def _post(base: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def main() -> None:
    # 1. JD folder listing (real folder — bookmarklet target).
    jds = server._jd_files()
    assert jds, "_jd_files() found no JD files in data/jds/"
    assert all(n.endswith((".txt", ".md")) for n in jds), jds[:3]
    print(f"jds OK: {len(jds)} files (e.g. {jds[0]!r})")

    # Stub the pipeline: no LLM/graph — write a fake plan.html fast, but
    # hold the 'running' state briefly so the 409 guard can be exercised.
    real_worker = server._run_pipeline

    def stub(options: dict) -> None:
        from . import cli as _cli

        time.sleep(0.3)
        _cli.set_stage_listener(server._set_stage)
        _cli._stage("judge")
        _cli.set_stage_listener(None)
        with server._lock:
            assert server._run["stage"] == "judge", server._run
        time.sleep(0.7)
        plan = server.OUTPUT_DIR / "plan.html"
        plan.parent.mkdir(exist_ok=True)
        plan.write_text("<html><body><h1>stub plan</h1></body></html>", encoding="utf-8")
        with server._lock:
            server._run.update(status="done", stage=None, finished_at=time.time(), error=None)

    server._run_pipeline = stub  # type: ignore[assignment]
    with server._lock:
        server._run.update(
            status="idle", stage=None, started_at=None, finished_at=None, error=None
        )

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        # 2. Index page: Generate button + poll loop + plan link.
        code, body, ctype = _get(base, "/")
        assert code == 200 and "text/html" in ctype, (code, ctype)
        text = body.decode("utf-8")
        assert "Generate plan" in text, "index missing Generate button"
        assert "/api/status" in text and "/api/jds" in text, "index missing poll/refresh"
        assert 'id="planlink"' in text, "index missing plan link"
        print("index OK: Generate button + poll + plan link present")

        # 3. JD list endpoint mirrors the folder.
        code, body, ctype = _get(base, "/api/jds")
        assert code == 200 and "application/json" in ctype, (code, ctype)
        payload = json.loads(body.decode("utf-8"))
        assert payload["jds"] == jds, "api/jds mismatch with folder"
        print(f"api/jds OK: {len(payload['jds'])} names match data/jds/")

        # 4. Run start -> 202; immediate second start -> 409; poll -> done.
        code, first = _post(base, "/api/run", {"top_n": 5})
        assert code == 202, (code, first)
        assert first["status"] == "running", first
        code2, second = _post(base, "/api/run", {"top_n": 5})
        assert code2 == 409, (code2, second)
        print("api/run OK: 202 start + 409 single-run guard")

        deadline = time.time() + 15
        status = ""
        saw_stage = False
        while time.time() < deadline:
            _, body, _ = _get(base, "/api/status")
            payload = json.loads(body.decode("utf-8"))
            status = payload["status"]
            if payload.get("stage") == "judge":
                saw_stage = True
            if status == "done":
                break
            time.sleep(0.5)
        assert status == "done", f"status never reached done (last={status})"
        assert saw_stage, "status never carried stage='judge' while running"
        print("api/status OK: running (+stage) -> done")

        # 5. plan.html served after the run.
        code, body, ctype = _get(base, "/plan.html")
        assert code == 200 and "text/html" in ctype, (code, ctype)
        assert b"stub plan" in body, "plan.html content mismatch"
        print("plan.html OK: served after run")

        # 6. JD viewer + plan verdict links.
        from urllib.parse import quote

        first = jds[0]
        code, body, ctype = _get(base, f"/jds/{quote(first)}")
        assert code == 200 and "text/html" in ctype, (code, ctype)
        assert first.encode("utf-8")[:20] in body, "JD viewer missing title"
        try:
            _get(base, "/jds/../cli.py")
            raise AssertionError("path traversal should be rejected")
        except urllib.error.HTTPError as e:
            assert e.code in (400, 404), e.code
        print(f"jd viewer OK: /jds/{first!r} served, traversal blocked")

        from .output import render_plan_html
        from .ranking import Gap

        demo = [
            Gap(target="LangGraph", weight=4, top_transfer_skill="Python",
                top_transfer_confidence=0.2, verdict="gap", gap_score=3.2,
                rationale="weak", source_jds=[first.removesuffix(".txt")]),
        ]
        linked = render_plan_html(
            demo, [], {"canonical": 1, "implied": 0, "jds": 1},
            jd_files={first.removesuffix(".txt"): first},
        )
        assert f"/jds/{first}" in linked, "verdict JD not linked with map"
        plain = render_plan_html(
            demo, [], {"canonical": 1, "implied": 0, "jds": 1}
        )
        assert "/jds/" not in plain, "verdict JD linked without map"
        print("verdict links OK: linked with jd_files, plain without")
    finally:
        httpd.shutdown()
        httpd.server_close()
        server._run_pipeline = real_worker  # type: ignore[assignment]
        with server._lock:
            server._run.update(
                status="idle", stage=None, started_at=None,
                finished_at=None, error=None,
            )
        # Restore: re-render is a pipeline job; just note the stub wrote it.
        print("(note: output/plan.html currently holds stub content from this check)")

    print(f"M11 CHECK PASS: {len(jds)} JDs listed, run+guard+stage+plan+jds OK.")


if __name__ == "__main__":
    main()
