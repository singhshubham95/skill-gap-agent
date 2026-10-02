"""M11 minimal local UI (specs/10-flow-runner.md S7).

Stdlib-only HTTP server (no new dep — same rationale as M10's urllib):
  GET  /            -> JD folder list + Generate button + loading screen
  POST /api/run     -> start the cli.py graph --auto in a background thread
  GET  /api/status  -> {status: idle|running|done|error, ...} (poll target)
  GET  /plan.html   -> serve output/plan.html (render_plan_html, GFI links)
  GET  /api/jds     -> JSON list of data/jds/*.txt|*.md (folder contents)

Single-run guard: POST /api/run while running -> 409. Status carries
started_at/finished_at/error. Paths resolve from the repo root (this file's
parents), never hardcoded — data/ and output/ stay gitignored.

Run: python -m skill_gap_agent.server [--port 8000]
Then open http://localhost:8000/ — bookmarklet-saved JDs appear in the list.
"""

from __future__ import annotations

import html
import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
JD_DIR = REPO_ROOT / "data" / "jds"
OUTPUT_DIR = REPO_ROOT / "output"
DEFAULT_SKILLS = REPO_ROOT / "data" / "skillsdataset.json"

_lock = threading.Lock()
_run: dict = {
    "status": "idle",
    "stage": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
}

# Human-readable stage labels for the loading screen. Keys are the node
# names cli.py reports via set_stage_listener(); values are plain words
# ("judging" not "node_judge") so a newcomer can follow the run.
STAGE_LABELS = {
    "ingest": "reading skills + JDs",
    "judge": "judging transferability (LLM, minutes)",
    "gate": "confidence gate",
    "rank": "ranking gaps",
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


def _run_pipeline(options: dict) -> None:
    """Background worker: same graph cli.py runs, forced --auto (no prompts)."""
    from .cli import AgentState, build_app, set_stage_listener

    set_stage_listener(_set_stage)
    top_n = int(options.get("top_n", 5))
    state: AgentState = {
        "skills_path": str(DEFAULT_SKILLS),
        "jds_path": str(JD_DIR),
        "auto": True,
        "skip_judge": bool(options.get("skip_judge", False)),
        "skip_oss": bool(options.get("skip_oss", False)),
        "no_llm_oss": bool(options.get("no_llm_oss", False)),
        "top_n": top_n,
        "link_jds": True,
        "jd_files": {p.stem: p.name for p in JD_DIR.iterdir() if p.is_file()},
    }
    try:
        app = build_app()
        app.invoke(state, config={"configurable": {"thread_id": "m11-ui"}})
    except Exception as e:  # noqa: BLE001 — surfaced via /api/status
        with _lock:
            _run.update(status="error", finished_at=time.time(), error=str(e))
        return
    finally:
        set_stage_listener(None)
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
  const labels = {ingest:'reading skills + JDs', judge:'judging transferability (LLM, minutes)', gate:'confidence gate', rank:'ranking gaps', synthesize:'synthesizing projects (LLM, minutes)', oss:'sourcing good-first-issues', output:'writing plan'};
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
            # filename must equal a real file in data/jds/).
            name = urllib.parse.unquote(path[len("/jds/"):])
            if "/" in name or "\\" in name:
                self._send(400, b"bad jd name", "text/plain")
                return
            target = JD_DIR / name
            if (
                not target.is_file()
                or target.suffix.lower() not in (".txt", ".md")
                or target.name not in _jd_files()
            ):
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
        with _lock:
            if _run["status"] == "running":
                self._json(409, {"error": "run already in progress"})
                return
            _run.update(
                status="running", stage=None, started_at=time.time(),
                finished_at=None, error=None,
            )
        t = threading.Thread(target=_run_pipeline, args=(options,), daemon=True)
        t.start()
        with _lock:
            self._json(202, dict(_run))

    def log_message(self, fmt: str, *args: object) -> None:
        safe = (fmt % args).encode("ascii", "replace").decode("ascii")
        print(f"[m11] {html.escape(safe)}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="M11 minimal local UI (stdlib server)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"M11 UI: http://localhost:{args.port}/  (JD folder: {JD_DIR})")
    print("Bookmarklet: tools/linkedin_jd_bookmarklet.js -> save JDs into data/jds/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
