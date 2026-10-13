"""M26 verification: local debug-mode checks (offline, no network).

Checks (stubbed LLM, no network):
1. Off by default — dbg/stage/llm_call are silent no-ops until
   configure(); one console handler on the skill_gap_agent.debug logger.
2. Line format + run-id — `<level> <time> [run-id] <message>`; err()
   carries the traceback; set_run_id binds every line.
3. Payload gating — `--debug` never prints prompt/response bodies;
   `--debug-payloads` prints them and implies `--debug`.
4. Stage decorator — enter/exit with counts summary, fail line + re-raise;
   all 8 cli node_* functions carry the wrapper.
5. Graph run — real two-phase rule-based run (seed data, isolated session
   dir, stubbed OSS seam) emits enter/exit/interrupt lines for every node
   with one shared run-id.
6. LLM summary — one `llm:` line per llm.chat() (tok=, attempts=, ok=1;
   error= on failure) via a stubbed client.
7. Server lifecycle — POST /api/run (stubbed pipeline) mints the run_id,
   returns it in the 202 body and /api/status; req + run lines share it;
   silent when off.
8. Boundary — debuglog.py imports no network/`langsmith` module (M17's
   §Scope boundary holds: nothing leaves the machine).

Run: python -m skill_gap_agent.m26_check
"""

from __future__ import annotations

import ast
import inspect
import json
import logging
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from http.server import ThreadingHTTPServer
from pathlib import Path

from . import cli, debuglog, server
from . import llm as llm_mod
from .ingest import build_seed_graph
from .taxonomy import load_taxonomy

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_SKILLS = REPO_ROOT / "data" / "skillsdataset.json"
DATA_JDS = REPO_ROOT / "data" / "jds"


class _Capture(logging.Handler):
    """Records exactly what the console handler would print."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []
        self.setFormatter(debuglog._handler.formatter)

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@contextmanager
def _captured():
    """Attach a capture handler; always restore off/none state afterwards."""
    cap = _Capture()
    logger = logging.getLogger(debuglog.LOGGER_NAME)
    logger.addHandler(cap)
    try:
        yield cap
    finally:
        logger.removeHandler(cap)
        debuglog.configure()
        debuglog.set_run_id(None)


def _get(base: str, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(base + path, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


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


# --- checks -----------------------------------------------------------------


def check_off_by_default() -> None:
    logger = logging.getLogger(debuglog.LOGGER_NAME)
    assert debuglog.enabled() is False, "debug logging must start off"
    assert debuglog.payloads_enabled() is False
    # The M26 invariant is about handlers debuglog OWNS (decision M26:
    # one console handler). Pytest's logging plugin attaches its own
    # capture handlers to every logger — including propagate=False ones —
    # so foreign handlers are framework machinery, never counted here.
    assert logger.handlers.count(debuglog._handler) == 1, (
        "debuglog must own exactly one console handler"
    )
    assert logger.propagate is False, "no doubling via the root logger"
    debuglog.configure(debug=True)
    debuglog.configure()
    assert logger.handlers.count(debuglog._handler) == 1, (
        "configure() must never add handlers"
    )

    with _captured() as cap:
        debuglog.dbg("run", "must not print")

        @debuglog.stage("probe")
        def probe(x: int) -> dict:
            return {"x": x}

        assert probe(7) == {"x": 7}
        debuglog.llm_call(provider="p", model="m", ms=1.0, attempts=1)
        debuglog.err("must not print")
    assert cap.lines == [], f"off must be silent: {cap.lines}"
    print("off-by-default OK: hooks are silent no-ops; one console handler")


def check_line_format() -> None:
    with _captured() as cap:
        debuglog.configure(debug=True)
        debuglog.set_run_id("server-42")
        debuglog.dbg("run", "hello world")
        try:
            raise ValueError("boom")
        except ValueError:
            debuglog.err("run failed: boom")
        debuglog.set_run_id(None)
        debuglog.dbg("req", "GET /api/status received")
    assert len(cap.lines) == 3, cap.lines
    assert re.fullmatch(
        r"info \d\d:\d\d:\d\d \[server-42\] run: hello world", cap.lines[0]
    ), cap.lines[0]
    assert "[server-42] run failed: boom" in cap.lines[1], cap.lines[1]
    assert cap.lines[1].startswith("error "), cap.lines[1]
    assert "Traceback (most recent call last)" in cap.lines[1], (
        "err() must carry the traceback: " + cap.lines[1]
    )
    assert "ValueError: boom" in cap.lines[1], cap.lines[1]
    assert re.fullmatch(
        r"info \d\d:\d\d:\d\d \[-\] req: GET /api/status received", cap.lines[2]
    ), cap.lines[2]
    assert debuglog.run_id() is None
    print("line format OK: <level> <time> [run-id] <message>, traceback on err()")


def check_payload_gating() -> None:
    with _captured() as cap:
        debuglog.configure(debug=True)  # payloads off
        debuglog.llm_call(
            provider="openrouter",
            model="deepseek/deepseek-v4-flash-0731",
            ms=12.0,
            attempts=2,
            rotations=1,
            usage={"prompt_tokens": 11, "completion_tokens": 5},
            prompt="SECRET-PROMPT",
            system="SECRET-SYSTEM",
            response="SECRET-RESPONSE",
        )
    assert len(cap.lines) == 1, cap.lines
    assert "SECRET" not in cap.lines[0], f"--debug must not print bodies: {cap.lines[0]}"
    assert "attempts=2" in cap.lines[0] and "rotations=1" in cap.lines[0], cap.lines[0]
    assert "tok=11/5" in cap.lines[0] and "ok=1" in cap.lines[0], cap.lines[0]

    with _captured() as cap:
        debuglog.configure(debug=False, payloads=True)  # implies --debug
        assert debuglog.enabled() and debuglog.payloads_enabled()
        debuglog.llm_call(
            provider="openrouter",
            model="m",
            ms=1.0,
            attempts=1,
            error="LLMError: boom",
            prompt="SECRET-PROMPT",
            system="SECRET-SYSTEM",
            response=None,
        )
    joined = "\n".join(cap.lines)
    assert "llm prompt: SECRET-PROMPT" in joined, cap.lines
    assert "llm system: SECRET-SYSTEM" in joined, cap.lines
    assert "error=LLMError: boom" in joined, cap.lines
    assert "ok=1" not in joined, cap.lines
    print("payload gating OK: bodies only under --debug-payloads (implies --debug)")


def check_stage_decorator() -> None:
    assert debuglog._counts({"gaps": [1, 2, 3], "stats": {"a": 1}, "flag": True}) == (
        "[gaps=3 stats={a=1} flag=True]"
    ), debuglog._counts({"gaps": [1, 2, 3], "stats": {"a": 1}, "flag": True})
    with _captured() as cap:
        debuglog.configure(debug=True)
        debuglog.set_run_id("server-1")

        @debuglog.stage("probe")
        def ok_node() -> dict:
            return {"gaps": [1, 2, 3], "stats": {"a": 1}, "flag": True}

        @debuglog.stage("probe")
        def bad_node() -> dict:
            raise RuntimeError("kaboom")

        ok_node()
        try:
            bad_node()
        except RuntimeError:
            pass
    joined = "\n".join(cap.lines)
    assert "stage: probe enter" in joined, cap.lines
    assert "stage: probe exit" in joined, cap.lines
    assert "out=[gaps=3 stats={a=1} flag=True]" in joined, cap.lines
    assert "stage: probe fail" in joined and "RuntimeError: kaboom" in joined, cap.lines
    print("stage decorator OK: enter/exit with counts, fail line + re-raise")


def check_node_hooks_attached() -> None:
    names = ("ingest", "judge", "gate", "rank", "pause", "synthesize", "oss", "output")
    for name in names:
        fn = getattr(cli, f"node_{name}")
        assert getattr(fn, "__wrapped__", None) is not None, (
            f"node_{name} lacks the @debuglog.stage wrapper"
        )
    print(f"node hooks OK: all {len(names)} graph nodes carry @debuglog.stage")


def check_graph_stage_lines() -> None:
    """Real two-phase rule-based run: every node's stage lines share one
    run-id (specs/14-observability.md §Local debug mode). No LLM, no
    network (use_llm=False; the OSS seam is stubbed like m13_check)."""
    from langgraph.checkpoint.memory import InMemorySaver

    tmp_root = Path(tempfile.mkdtemp(prefix="m26-graph-"))
    real_oss = cli.source_oss_for_gaps
    real_sessions_env = os.environ.get("SKILL_GAP_SESSIONS_DIR")

    def _stub_oss(sg, gaps, **kwargs):
        return {}

    cli.source_oss_for_gaps = _stub_oss  # type: ignore[assignment]
    try:
        # Pre-scan the seed graph for real target names: auto mode runs the
        # gate node only when profile decisions exist to apply
        # (cli.gate_needed), so seed an intent answer per target.
        sg0, _stats = build_seed_graph(
            DATA_SKILLS, DATA_JDS, taxonomy=load_taxonomy(), auto_accept_implied=True
        )
        targets = sorted(sg0.target_skills())
        assert targets, "seed data has no target skills"
        os.environ["SKILL_GAP_SESSIONS_DIR"] = str(tmp_root / "sessions")
        from . import sessions as sessions_mod

        sessions_mod.save_profile(
            str(DATA_SKILLS), {"intent": {t: "count" for t in targets}}
        )
        state = {
            "skills_path": str(DATA_SKILLS),
            "jds_path": str(DATA_JDS),
            "auto": True,
            "top_n": 3,
            "skip_oss": False,  # node_oss runs against the stubbed seam
            "use_llm": False,  # rule-based: zero LLM calls
            "link_jds": False,
            "source_input": str(DATA_SKILLS),
            "session_dir": str(tmp_root / "artifacts"),
            "two_phase": True,
        }
        config = {"configurable": {"thread_id": "server-m26-check"}}
        with _captured() as cap:
            debuglog.configure(debug=True)
            debuglog.set_run_id("server-m26-check")
            app = cli.build_app(checkpointer=InMemorySaver())
            app.invoke(state, config=config)
            assert cli.pending_interrupt(app, config) is not None, (
                "two-phase run must pause after rank"
            )
            app.invoke(cli.Command(resume={"phase": "plan"}), config=config)
        lines = cap.lines
        assert lines, "debug run emitted nothing"
        for ln in lines:
            assert "[server-m26-check]" in ln, f"line lost the run-id: {ln}"
        for name in (
            "ingest", "judge", "gate", "rank", "pause",
            "synthesize", "oss", "output",
        ):
            assert any(f"stage: {name} enter" in ln for ln in lines), (
                f"missing enter line for node {name}: {lines}"
            )
            assert any(f"stage: {name} exit" in ln for ln in lines), (
                f"missing exit line for node {name}: {lines}"
            )
        assert any("stage: pause interrupt" in ln for ln in lines), lines
        assert any("gate: overrides=" in ln for ln in lines), lines
        joined = "\n".join(lines)
        assert "out=[judged=False unjudged=" in joined, "judge counts missing"
        assert "out=[gaps=" in joined, "rank counts missing"
        print(
            "graph stages OK: all 8 nodes logged enter/exit with counts + "
            "one shared run-id (pause interrupt covered)"
        )
    finally:
        cli.source_oss_for_gaps = real_oss
        if real_sessions_env is None:
            os.environ.pop("SKILL_GAP_SESSIONS_DIR", None)
        else:
            os.environ["SKILL_GAP_SESSIONS_DIR"] = real_sessions_env


def check_llm_summary() -> None:
    class _FakeUsage:
        prompt_tokens = 11
        completion_tokens = 5

    def _fake_response(text: str):
        message = type("M", (), {"content": text})()
        choice = type("C", (), {"message": message})()
        return type("R", (), {"choices": [choice], "usage": _FakeUsage()})()

    class _FakeError(Exception):
        def __init__(self, status_code: int):
            super().__init__(f"Error {status_code}")
            self.status_code = status_code
            self.headers: dict = {}

    class _Completions:
        def __init__(self, outcomes: list):
            self.outcomes = list(outcomes)

        def create(self, **kwargs):
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    class _FakeClient:
        def __init__(self, outcomes: list):
            self.chat = type("CH", (), {})()
            self.chat.completions = _Completions(outcomes)

    def _patch(outcomes: list) -> _FakeClient:
        fake = _FakeClient(outcomes)
        llm_mod._client = lambda cfg: (fake, llm_mod.PROVIDERS["openrouter"])  # type: ignore[assignment]
        return fake

    real_client = llm_mod._client
    real_sleep = time.sleep
    time.sleep = lambda s: None
    try:
        with _captured() as cap:
            debuglog.configure(debug=True)
            debuglog.set_run_id("server-9")
            _patch([_fake_response("hello")])
            out = llm_mod.chat("hi", system="sys", cfg=llm_mod.LLMConfig())
            assert out == "hello"
        joined = "\n".join(cap.lines)
        assert "llm: openrouter/deepseek/deepseek-v4-flash-0731" in joined, cap.lines
        assert "attempts=1" in joined and "tok=11/5" in joined and "ok=1" in joined, (
            cap.lines
        )

        with _captured() as cap:
            debuglog.configure(debug=True)
            _patch([_FakeError(429), _FakeError(429), _fake_response("retried")])
            llm_mod.chat("hi", cfg=llm_mod.LLMConfig(max_retries=3))
        assert any("attempts=3" in ln and "ok=1" in ln for ln in cap.lines), cap.lines

        with _captured() as cap:
            debuglog.configure(debug=True)
            _patch([_FakeError(400)])
            try:
                llm_mod.chat("hi", cfg=llm_mod.LLMConfig())
                raise AssertionError("expected non-transient failure")
            except llm_mod.LLMNonTransientError:
                pass
        assert any(
            "error=LLMNonTransientError" in ln and "attempts=1" in ln
            for ln in cap.lines
        ), cap.lines
        print("llm summary OK: one line per chat() with attempts/tokens/error")
    finally:
        llm_mod._client = real_client
        time.sleep = real_sleep


def check_server_lifecycle() -> None:
    src_main = inspect.getsource(server.main)
    assert "--debug" in src_main and "--debug-payloads" in src_main, (
        "server.main must expose the debug flags"
    )
    real_worker = server._run_pipeline

    def stub(options: dict) -> None:
        with server._lock:
            server._run.update(
                status="done", stage=None, finished_at=time.time(), error=None
            )

    server._run_pipeline = stub  # type: ignore[assignment]
    with server._lock:
        server._run.update(
            status="idle", stage=None, started_at=None, finished_at=None,
            error=None, run_id=None,
        )
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with _captured() as cap:
            debuglog.configure(debug=True)
            code, body = _post(base, "/api/run", {"top_n": 3, "use_llm": False})
            assert code == 202, (code, body)
            run_id = body.get("run_id")
            assert run_id and run_id.startswith("server-"), body
            status: dict = {}
            deadline = time.time() + 10
            while time.time() < deadline:
                _, status = _get(base, "/api/status")
                if status.get("status") == "done":
                    break
                time.sleep(0.1)
            assert status.get("status") == "done", status
            assert status.get("run_id") == run_id, (status, run_id)
        lines = cap.lines
        assert lines, "debug server emitted nothing"
        joined = "\n".join(lines)
        assert "run: start phase=full" in joined, lines
        assert "req: POST /api/run received" in joined, lines
        assert "req: POST /api/run -> 202" in joined, lines
        assert "req: GET /api/status" in joined, lines
        # Correlation: the run-id is minted when the run is accepted, so
        # every line from "run: start" on carries it — including the
        # triggering request's -> 202 line. Its "received" line precedes
        # the run's existence and shows [-] (truthful ordering).
        start_at = next(i for i, ln in enumerate(lines) if "run: start" in ln)
        assert lines[start_at - 1].endswith("req: POST /api/run received"), lines
        for ln in lines[start_at:]:
            assert f"[{run_id}]" in ln, f"line lost the run-id: {ln}"
        assert any("req: POST /api/run -> 202" in ln for ln in lines[start_at:]), lines
        with _captured() as cap2:
            debuglog.configure()  # off
            _get(base, "/api/status")
        assert cap2.lines == [], f"server must be silent when off: {cap2.lines}"
        print(
            "server lifecycle OK: run_id minted, exposed in /api/status, "
            "shared by req/run lines; silent when off"
        )
    finally:
        server._run_pipeline = real_worker
        httpd.shutdown()
        httpd.server_close()
        with server._lock:
            server._run.update(
                status="idle", stage=None, started_at=None, finished_at=None,
                error=None, run_id=None,
            )


def check_debuglog_imports() -> None:
    """M26 boundary: debuglog.py stays local-only (no network, no langsmith)."""
    src = Path(debuglog.__file__).read_text(encoding="utf-8")
    roots: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    banned = {
        "langsmith", "urllib", "socket", "http", "requests", "httpx",
        "aiohttp", "openai", "ssl", "ftplib", "smtplib", "websocket", "asyncio",
    }
    hit = roots & banned
    assert not hit, f"debuglog.py must stay local-only, found: {sorted(hit)}"
    print(f"boundary OK: debuglog.py imports only {sorted(roots)}")


def main() -> None:
    check_off_by_default()
    check_line_format()
    check_payload_gating()
    check_stage_decorator()
    check_node_hooks_attached()
    check_llm_summary()
    check_server_lifecycle()
    check_graph_stage_lines()
    check_debuglog_imports()
    print(
        "M26 CHECK PASS: off-by-default, line format + run-id, payload "
        "gating, stage decorator, node hooks, llm summary, server lifecycle, "
        "graph stages, local-only boundary OK."
    )


if __name__ == "__main__":
    main()
