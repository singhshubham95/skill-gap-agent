"""M11 minimal local UI + M13 extension run contract (stdlib server).

Stdlib-only HTTP server (no new dep — same rationale as M10's urllib):
  GET  /            -> JD folder list + Generate button + loading screen
  POST /api/run     -> start a pipeline run in a background thread
                       body: {phase?, jds?, top_n?, skip_judge?, reuse_judged?,
                              skip_oss?, no_llm_oss?, skills_path?}
                       phase "gaps" (M13): write captured jds to
                         output/captured_jds/, run the graph with two_phase
                         (pause after rank) -> status "paused"
                       phase "plan" (M13): resume the paused run through
                         synthesize -> oss -> output (409 if none paused)
                       no phase (M11): full one-shot run
  GET  /api/status  -> {status: idle|running|paused|done|error, ...} (poll target)
  GET  /api/gaps    -> output/gaps.json (M13: ranked gaps for the side panel)
  GET  /plan.html   -> serve output/plan.html (render_plan_html, GFI links)
  GET  /api/jds     -> JSON list of data/jds/*.txt|.md (folder contents)

Single-run guard: POST /api/run while running -> 409. Status carries
started_at/finished_at/error. Paths resolve from the repo root (this file's
parents), never hardcoded — data/ and output/ stay gitignored.

No CORS headers on purpose (decision in specs/02-decisions.md): the Chrome
extension (extension/) calls with host_permissions for localhost, which
bypasses CORS; absent ACAO + no OPTIONS handler keeps hostile web pages from
reading gaps or triggering runs. Server binds 127.0.0.1 only.

Run: python -m skill_gap_agent.server [--port 8000] [--skills <file>]
Then open http://localhost:8000/ — bookmarklet-saved JDs appear in the list.
"""

from __future__ import annotations

import html
import json
import os
import re
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JD_DIR = REPO_ROOT / "data" / "jds"
OUTPUT_DIR = REPO_ROOT / "output"
CAPTURED_DIR = OUTPUT_DIR / "captured_jds"
DEFAULT_SKILLS = REPO_ROOT / "data" / "skillsdataset.json"

_lock = threading.Lock()
_run: dict = {
    "status": "idle",
    "stage": None,
    "phase": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}
# The paused two-phase run (phase "gaps" -> waiting for "plan"). The
# SkillGraph lives in cli.py's process-bound runtime registry, so the resume
# must happen in this process — the app/config pair is kept here until then.
_paused: dict = {"app": None, "config": None}

# Human-readable stage labels for the loading screen. Keys are the node
# names cli.py reports via set_stage_listener(); values are plain words
# ("judging" not "node_judge") so a newcomer can follow the run.
STAGE_LABELS = {
    "ingest": "reading skills + JDs",
    "judge": "judging transferability (LLM, minutes)",
    "gate": "confidence gate",
    "rank": "ranking gaps",
    "pause": "gaps ready - awaiting Generate plan",
    "synthesize": "synthesizing projects (LLM, minutes)",
    "oss": "sourcing good-first-issues",
    "output": "writing plan",
}


def _set_stage(name: str) -> None:
    with _lock:
        _run["stage"] = name


def _jd_files() -> list[str]:
    if not JD_DIR.exists():
        return []
    return sorted(
        f.name
        for f in JD_DIR.iterdir()
        if f.is_file() and f.suffix.lower() in (".txt", ".md")
    )


def _find_jd(name: str) -> Path | None:
    """Resolve a JD-viewer filename against data/jds/ AND output/captured_jds/.

    plan.html's JD links are built from whichever folder the run ingested:
    bookmarklet saves land in data/jds/, extension captures in
    output/captured_jds/ (see _write_captured_jds). Exact-name match against
    the folder listing only — the caller has already rejected path
    separators, so no traversal can reach here.
    """
    for d in (JD_DIR, CAPTURED_DIR):
        if not d.exists():
            continue
        names = {
            f.name
            for f in d.iterdir()
            if f.is_file() and f.suffix.lower() in (".txt", ".md")
        }
        if name in names:
            return d / name
    return None


def _write_captured_jds(jds: list) -> dict[str, str]:
    """Write the extension's captured JDs to output/captured_jds/ and return
    the {title-stem: filename} map used for plan.html JD links.

    File shape mirrors the bookmarklet: "title\\nurl\\n\\ntext", so
    ingest.py::ingest_jds reads the folder unchanged (the stem becomes the JD
    title, exactly like bookmarklet saves into data/jds/). The folder is
    replaced wholesale — the panel's list IS the run's JD set.
    """
    if CAPTURED_DIR.exists():
        for f in CAPTURED_DIR.iterdir():
            if f.is_file():
                f.unlink()
    CAPTURED_DIR.mkdir(parents=True, exist_ok=True)
    jd_files: dict[str, str] = {}
    for item in jds:
        title = str(item.get("title") or "jd").strip() or "jd"
        url = str(item.get("url") or "")
        text = str(item.get("text") or "")
        stem = re.sub(r"[^a-z0-9]+", "_", title, flags=re.IGNORECASE)[:80] or "jd"
        name = stem
        n = 2
        while name in jd_files:
            name = f"{stem}-{n}"
            n += 1
        (CAPTURED_DIR / f"{name}.txt").write_text(
            f"{title}\n{url}\n\n{text}", encoding="utf-8"
        )
        jd_files[name] = f"{name}.txt"
    return jd_files


def _drop_paused() -> None:
    _paused["app"] = None
    _paused["config"] = None


def _run_pipeline(options: dict) -> None:
    """Background worker: same graph cli.py runs, forced --auto (no prompts).

    With phase == "gaps" the run gets two_phase state and pauses right after
    ranking (interrupt() + in-memory checkpointer); the app/config pair stays
    in _paused for _resume_pipeline. The SkillGraph lives in cli.py's
    process-bound runtime registry, so both phases must run here.
    """
    from langgraph.checkpoint.memory import InMemorySaver

    from .cli import AgentState, build_app, pending_interrupt, set_stage_listener

    # cli.py writes artifacts to repo-root-relative output/; run from the
    # repo root so GET /api/gaps (REPO_ROOT/output) sees them regardless of
    # where the server was started.
    os.chdir(REPO_ROOT)
    set_stage_listener(_set_stage)
    _drop_paused()
    top_n = int(options.get("top_n", 5))
    phase = str(options.get("phase") or "full")
    two_phase = phase == "gaps"
    skills_path = str(options.get("skills_path") or DEFAULT_SKILLS)
    if Path(skills_path).suffix.lower() != ".json":
        # M8 resume front-end (same as cli.main()): resume -> skills JSON
        # before the graph starts; reuses output/extracted_skills.json, so
        # the one-time extraction cost is paid only on the first resume.
        from .resume import resume_to_skills_json

        try:
            skills_path = str(
                resume_to_skills_json(
                    skills_path, use_llm=True, auto=True, ask_fn=None
                )[0]
            )
        except Exception as e:  # noqa: BLE001 — surfaced via /api/status
            traceback.print_exc()
            with _lock:
                _run.update(status="error", finished_at=time.time(), error=str(e))
            return
    captured = options.get("jds") or []
    jds_path = str(JD_DIR)
    jd_files = (
        {p.stem: p.name for p in JD_DIR.iterdir() if p.is_file()}
        if JD_DIR.exists()
        else {}
    )
    if captured:
        jd_files = _write_captured_jds(captured)
        jds_path = str(CAPTURED_DIR)
    state: AgentState = {
        "skills_path": skills_path,
        "jds_path": jds_path,
        "auto": True,
        "skip_judge": bool(options.get("skip_judge", False)),
        "reuse_judged": bool(options.get("reuse_judged", False)),
        "skip_oss": bool(options.get("skip_oss", False)),
        "no_llm_oss": bool(options.get("no_llm_oss", False)),
        "top_n": top_n,
        "link_jds": True,
        "jd_files": jd_files,
    }
    checkpointer = None
    if two_phase:
        state["two_phase"] = True
        checkpointer = InMemorySaver()
    config = {"configurable": {"thread_id": f"server-{time.time_ns()}"}}
    try:
        app = build_app(checkpointer=checkpointer)
        app.invoke(state, config=config)
        if two_phase and pending_interrupt(app, config) is not None:
            with _lock:
                _paused["app"] = app
                _paused["config"] = config
                _run.update(
                    status="paused", stage=None,
                    finished_at=time.time(), error=None,
                )
            return
    except Exception as e:  # noqa: BLE001 — surfaced via /api/status
        traceback.print_exc()
        with _lock:
            _run.update(status="error", finished_at=time.time(), error=str(e))
        return
    finally:
        set_stage_listener(None)
    with _lock:
        _run.update(status="done", stage=None, finished_at=time.time(), error=None)


def _resume_pipeline(options: dict) -> None:
    """Phase 2 worker: resume the paused run through synthesize -> oss -> output."""
    from .cli import Command, set_stage_listener

    os.chdir(REPO_ROOT)
    app = _paused["app"]
    config = _paused["config"]
    if app is None or config is None:
        with _lock:
            _run.update(
                status="error", finished_at=time.time(),
                error="no paused run to resume",
            )
        return
    set_stage_listener(_set_stage)
    try:
        app.invoke(Command(resume={"phase": "plan"}), config=config)
    except Exception as e:  # noqa: BLE001 — surfaced via /api/status
        traceback.print_exc()
        with _lock:
            _run.update(status="error", finished_at=time.time(), error=str(e))
        return
    finally:
        set_stage_listener(None)
        _drop_paused()
    with _lock:
        _run.update(status="done", stage=None, finished_at=time.time(), error=None)


INDEX_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Skill-Gap Agent</title></head><body>
<h1>Skill-Gap Agent (M11 local UI)</h1>
<p>JD folder: <code>data/jds/</code> — save LinkedIn JDs with the bookmarklet
(<code>tools/linkedin_jd_bookmarklet.js</code>), then Generate.</p>
<h2>Job descriptions (<span id="count">?</span>)</h2>
<ul id="jds"><li>loading…</li></ul>
<p>
<label>Top gaps: <input id="top_n" type="number" value="5" min="1" max="23"></label>
<label><input id="skip_judge" type="checkbox"> reuse judge edges (--no-judge)</label>
<label><input id="skip_oss" type="checkbox"> skip OSS (--no-oss)</label>
<label><input id="no_llm_oss" type="checkbox"> raw OSS, no filter (--no-llm-oss)</label>
</p>
<p><button id="go" onclick="startRun()">Generate plan</button></p>
<p id="status">idle</p>
<p><a id="planlink" href="/plan.html" style="display:none">Open plan.html</a></p>
<script>
async function refreshJds(){
  const r = await fetch('/api/jds'); const j = await r.json();
  document.getElementById('count').textContent = j.jds.length;
  document.getElementById('jds').innerHTML =
    j.jds.map(n => '<li>' + n.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</li>').join('')
    || '<li><em>no JD files — save one with the bookmarklet first</em></li>';
}
async function poll(){
  const r = await fetch('/api/status'); const s = await r.json();
  const el = document.getElementById('status');
  const labels = {ingest:'reading skills + JDs', judge:'judging transferability (LLM, minutes)', gate:'confidence gate', rank:'ranking gaps', pause:'gaps ready - awaiting Generate plan', synthesize:'synthesizing projects (LLM, minutes)', oss:'sourcing good-first-issues', output:'writing plan'};
  const stage = s.stage ? (' — ' + (labels[s.stage] || s.stage)) : '';
  el.textContent = s.status + stage + (s.error ? (': ' + s.error) : '');
  if (s.status === 'running') { setTimeout(poll, 3000); }
  if (s.status === 'done') {
    document.getElementById('planlink').style.display = '';
    document.getElementById('go').disabled = false;
  }
  if (s.status === 'error') { document.getElementById('go').disabled = false; }
}
async function startRun(){
  const btn = document.getElementById('go'); btn.disabled = true;
  document.getElementById('planlink').style.display = 'none';
  const body = {
    top_n: parseInt(document.getElementById('top_n').value || '5', 10),
    skip_judge: document.getElementById('skip_judge').checked,
    skip_oss: document.getElementById('skip_oss').checked,
    no_llm_oss: document.getElementById('no_llm_oss').checked,
  };
  const r = await fetch('/api/run', {method:'POST',
    headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)});
  if (r.status === 409) {
    document.getElementById('status').textContent = 'already running';
    setTimeout(poll, 3000); return;
  }
  document.getElementById('status').textContent = 'running… (judge/synthesis/OSS take minutes)';
  poll();
}
refreshJds();
</script>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    server_version = "SkillGapM11/1.0"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

    def do_GET(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/jds":
            self._json(200, {"jds": _jd_files()})
        elif path == "/api/status":
            with _lock:
                self._json(200, dict(_run))
        elif path == "/api/gaps":
            gaps = OUTPUT_DIR / "gaps.json"
            if not gaps.exists():
                self._json(404, {"error": "no gaps yet - run phase 'gaps' first"})
                return
            self._send(200, gaps.read_bytes(), "application/json")
        elif path == "/plan.html":
            plan = OUTPUT_DIR / "plan.html"
            if not plan.exists():
                self._send(
                    404,
                    b"<h1>No plan yet</h1><p>Click Generate plan first.</p>",
                    "text/html; charset=utf-8",
                )
                return
            self._send(200, plan.read_bytes(), "text/html; charset=utf-8")
        elif path.startswith("/jds/"):
            # JD viewer: exact-name match only (no path traversal — the
            # filename must equal a real file in data/jds/ or, for
            # extension-captured runs, output/captured_jds/).
            name = urllib.parse.unquote(path[len("/jds/"):])
            if "/" in name or "\\" in name:
                self._send(400, b"bad jd name", "text/plain")
                return
            target = _find_jd(name)
            if target is None:
                self._send(404, b"jd not found", "text/plain")
                return
            text = target.read_text(encoding="utf-8", errors="replace")
            page = (
                "<!doctype html><html><head><meta charset='utf-8'><title>"
                + html.escape(name)
                + "</title></head><body><h1>"
                + html.escape(name)
                + "</h1><pre>"
                + html.escape(text)
                + "</pre><p><a href='/plan.html'>Back to plan</a></p>"
                + "</body></html>"
            )
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/run":
            self._send(404, b"not found", "text/plain")
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        try:
            options = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(options, dict):
                raise TypeError("body must be a JSON object")
        except (ValueError, TypeError) as e:
            self._json(400, {"error": f"bad JSON body: {e}"})
            return
        phase = options.get("phase") or "full"
        if phase not in ("full", "gaps", "plan"):
            self._json(400, {"error": f"bad phase: {phase!r}"})
            return
        jds = options.get("jds")
        if jds is not None and (
            not isinstance(jds, list) or not all(isinstance(x, dict) for x in jds)
        ):
            self._json(400, {"error": "jds must be a list of objects"})
            return
        with _lock:
            if _run["status"] == "running":
                self._json(409, {"error": "run already in progress"})
                return
            if phase == "plan" and _paused["app"] is None:
                self._json(409, {"error": "no paused run - run phase 'gaps' first"})
                return
            _run.update(
                status="running", stage=None, phase=phase, started_at=time.time(),
                finished_at=None, error=None,
            )
        worker = _resume_pipeline if phase == "plan" else _run_pipeline
        t = threading.Thread(target=worker, args=(options,), daemon=True)
        t.start()
        with _lock:
            self._json(202, dict(_run))

    def log_message(self, fmt: str, *args: object) -> None:
        safe = (fmt % args).encode("ascii", "replace").decode("ascii")
        print(f"[m11] {html.escape(safe)}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="M11/M13 local UI + extension backend (stdlib server)"
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--skills",
        default=None,
        help="skills JSON or resume file for runs (default data/skillsdataset.json)",
    )
    args = parser.parse_args()
    if args.skills:
        global DEFAULT_SKILLS
        DEFAULT_SKILLS = Path(args.skills)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"M11 UI: http://localhost:{args.port}/  (JD folder: {JD_DIR})")
    print("Bookmarklet: tools/linkedin_jd_bookmarklet.js -> save JDs into data/jds/")
    print("Extension: load extension/ unpacked (see extension/README.md)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
