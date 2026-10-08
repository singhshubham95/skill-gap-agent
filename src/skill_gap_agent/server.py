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

M14 self-serve setup (specs/12-extension.md §M14):
  POST /api/resume  -> upload a resume (raw file bytes; original name in
                       X-Filename), validate (10 MB cap, .pdf/.docx/.txt,
                       magic bytes), store under output/uploads/, run the
                       M8 extraction immediately (blocks until done)
  GET  /api/providers -> [{id, model, key_set}] — key_set is a boolean;
                       key material is never returned by any endpoint
  POST /api/key     -> {provider, api_key, remember} — store the key in
                       the OS keyring ("remember") or the process env
                       ("session only"). Never echoes the key.

M15 LLM presence policy (specs/05-ai-caller.md §LLM presence policy):
  POST /api/run body gains use_llm (bool, default true). LLM mode with no
  stored key is refused up front (409, actionable message) — a run never
  silently produces non-LLM output. /api/status carries llm_mode
  ("llm" | "rule-based") and degraded_reasons [{touchpoint, error}]; every
  rendered section/row labels its source (llm.py vocabulary).

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

from . import llm as llm_mod
from . import secrets
from .llm import PROVIDERS, LLMConfig, LLMError, require_api_key

REPO_ROOT = Path(__file__).resolve().parents[2]
JD_DIR = REPO_ROOT / "data" / "jds"
OUTPUT_DIR = REPO_ROOT / "output"
CAPTURED_DIR = OUTPUT_DIR / "captured_jds"
UPLOAD_DIR = OUTPUT_DIR / "uploads"  # M14: uploaded resumes (output/ gitignored)
DEFAULT_SKILLS = REPO_ROOT / "data" / "skillsdataset.json"
MAX_RESUME_BYTES = 10 * 1024 * 1024  # M14 upload cap

_lock = threading.Lock()
_run: dict = {
    "status": "idle",
    "stage": None,
    "phase": None,
    "started_at": None,
    "finished_at": None,
    "error": None,
    # M15 LLM presence policy: the run's mode and any loud degradations.
    "llm_mode": None,
    "degraded_reasons": [],
    # M16 free-tier status fields (specs/05-ai-caller.md §Free-tier routing).
    "free_tier": False,
    "llm_model": None,
}
# The paused two-phase run (phase "gaps" -> waiting for "plan"). The
# SkillGraph lives in cli.py's process-bound runtime registry, so the resume
# must happen in this process — the app/config pair is kept here until then.
_paused: dict = {"app": None, "config": None}

# M14: the uploaded resume a run should use when the body carries no
# explicit skills_path. Never chrome.storage — this is server-side state.
_resume: dict = {"path": None, "filename": None, "count": None, "source": None}

# M16 OAuth connect (specs/12-extension.md §M16 A): the one-time code
# OpenRouter redirects back with, kept in memory keyed by the panel's
# state with a 10-minute TTL. No key material is ever stored here — only
# the pending code, and it never leaves the server.
OAUTH_CODE_TTL_SECONDS = 600
_oauth: dict = {"codes": {}, "expected_states": set()}

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


def _resolve_skills(options: dict) -> Path:
    """Skills input precedence (M14): body skills_path -> uploaded resume ->
    the server's --skills default."""
    explicit = options.get("skills_path")
    if explicit:
        return Path(explicit)
    with _lock:
        uploaded = _resume.get("path")
    if uploaded:
        return Path(uploaded)
    return Path(DEFAULT_SKILLS)


def _resolve_provider(options: dict) -> str:
    """Run provider (M14): body provider -> default. Unknown ids raise so
    the POST layer can answer 400 instead of silently using another key."""
    provider = str(options.get("provider") or "openrouter")
    if provider not in PROVIDERS:
        raise ValueError(f"unknown provider: {provider!r}")
    return provider


def _resolve_use_llm(options: dict) -> bool:
    """M15: run-level LLM mode (default on). use_llm:false = Rule-based."""
    return bool(options.get("use_llm", True))


def _sync_run_state(app, config: dict, status: str) -> dict:
    """M15: copy llm_mode + degraded_reasons from the graph state into _run.

    The banner must state the truth even when only part of the run used the
    LLM, so the accumulated degrade records ride in state and are read out
    at every status transition (paused/done/error).
    """
    with _lock:
        _run["status"] = status
        if app is not None:
            try:
                values = app.get_state(config).values or {}
            except Exception:  # noqa: BLE001 — no checkpointer: best effort
                values = {}
            if values.get("degraded_reasons"):
                _run["degraded_reasons"] = values["degraded_reasons"]
            if "use_llm" in values:
                _run["llm_mode"] = "llm" if values.get("use_llm", True) else "rule-based"
            # M16 status fields (specs/05-ai-caller.md §Free-tier routing):
            # free_tier + llm_model (the :free ID currently answering calls —
            # it moves when the fallback list rotates).
            _run["free_tier"] = bool(values.get("free_tier", False))
            if values.get("free_tier"):
                _run["llm_model"] = llm_mod.last_model()
        return dict(_run)


def _describe_skills() -> dict:
    """What the next run will use, for GET /api/status (M14)."""
    with _lock:
        if _resume.get("path"):
            return {
                "filename": _resume["filename"],
                "count": _resume["count"],
                "source": _resume["source"],
            }
    return {"filename": Path(DEFAULT_SKILLS).name, "count": None, "source": "default"}


def _oauth_pending_code(state: str) -> str | None:
    """The code stored for this state, or None if absent/expired (10-min
    TTL). The code is keyed by the panel's state (specs/12-extension.md
    §M16 A step 3) and never leaves the server."""
    with _lock:
        entry = _oauth["codes"].get(state)
        if not entry:
            return None
        code, created = entry["code"], entry["created_at"]
        if not code or created is None:
            return None
        if time.time() - created > OAUTH_CODE_TTL_SECONDS:
            del _oauth["codes"][state]
            return None
        return code


def _oauth_consume_code(state: str) -> str | None:
    """Pop the one-time code for this state (used by the exchange)."""
    with _lock:
        entry = _oauth["codes"].pop(state, None)
        if not entry:
            return None
        code, created = entry["code"], entry["created_at"]
        if not code or created is None:
            return None
        if time.time() - created > OAUTH_CODE_TTL_SECONDS:
            return None
        return code


def _exchange_openrouter_code(code: str, code_verifier: str) -> dict:
    """Exchange the OAuth code for a user-owned key at OpenRouter.

    Server-side only (specs/12-extension.md §M16 A): the key transits this
    handler once and goes straight into the OS keyring — never echoed,
    never chrome.storage. Returns the parsed JSON response.
    """
    import urllib.request

    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/auth/keys",
        data=json.dumps({"code": code, "code_verifier": code_verifier}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


OAUTH_CALLBACK_PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Skill-Gap Agent</title></head>
<body style="font-family: system-ui; padding: 24px;">
<h1>Connected — return to the side panel</h1>
<p>OpenRouter sent the key to the local agent. You can close this tab and
go back to the Skill-Gap Agent side panel.</p>
</body></html>"""


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
    skills_path = _resolve_skills(options)
    provider = _resolve_provider(options)
    use_llm = _resolve_use_llm(options)
    free_tier = bool(options.get("free_tier", False))
    if use_llm:
        # Race-safe backstop for the POST-layer pre-flight (M15): never
        # start a run that would silently degrade the whole pipeline.
        try:
            require_api_key(provider)
        except LLMError as e:
            with _lock:
                _run.update(status="error", finished_at=time.time(), error=str(e))
            return
    if Path(skills_path).suffix.lower() != ".json":
        # M8 resume front-end (same as cli.main()): resume -> skills JSON
        # before the graph starts; the artifact is reused only for the same
        # resume (SHA-256 sidecar), so the extraction cost is per-resume.
        from .resume import resume_to_skills_json

        try:
            skills_path = str(
                resume_to_skills_json(
                    skills_path,
                    use_llm=use_llm,
                    auto=True,
                    ask_fn=None,
                    cfg=LLMConfig(provider=provider, free_tier=free_tier),
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
        "provider": provider,
        "use_llm": use_llm,
        "free_tier": free_tier,
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
            _sync_run_state(app, config, "paused")
            with _lock:
                _run.update(stage=None, finished_at=time.time(), error=None)
                _paused["app"] = app
                _paused["config"] = config
            return
    except Exception as e:  # noqa: BLE001 — surfaced via /api/status
        traceback.print_exc()
        with _lock:
            _run.update(status="error", finished_at=time.time(), error=str(e))
        return
    finally:
        set_stage_listener(None)
    _sync_run_state(app, config, "done")
    with _lock:
        _run.update(stage=None, finished_at=time.time(), error=None)


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
    _sync_run_state(app, config, "done")
    with _lock:
        _run.update(stage=None, finished_at=time.time(), error=None)


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
                payload = dict(_run)
            payload["skills"] = _describe_skills()
            self._json(200, payload)
        elif path == "/api/providers":
            # Key material is never returned — key_set is a boolean only.
            self._json(200, {
                "providers": [
                    {
                        "id": pid,
                        "model": info["model"],
                        "key_set": bool(secrets.get_secret(info["key_env"])),
                    }
                    for pid, info in PROVIDERS.items()
                ]
            })
        elif path == "/api/oauth/callback":
            # M16 A step 3: OpenRouter redirects the tab here with the
            # one-time code + the panel's state. The state is validated
            # server-side: missing or unknown state -> reject, store
            # nothing. The code is stored keyed by state with a 10-minute
            # TTL and consumed by the panel's exchange call.
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if query.get("error"):
                self._send(
                    200,
                    b"<h1>Connection not completed</h1><p>Return to the side "
                    b"panel and try again.</p>",
                    "text/html; charset=utf-8",
                )
                return
            code = (query.get("code") or [""])[0]
            state = (query.get("state") or [""])[0]
            if not code or not state:
                self._send(400, b"missing code or state", "text/plain")
                return
            # The state must have been minted by the panel (it is present
            # in the pending-poll set) — a callback with an unknown state
            # stores nothing.
            with _lock:
                known = state in _oauth["expected_states"]
                if known:
                    _oauth["codes"][state] = {
                        "code": code, "created_at": time.time(),
                    }
            if not known:
                self._send(
                    400,
                    "<h1>Connection not completed</h1><p>Unknown state — "
                    "return to the side panel and try again.</p>".encode(),
                    "text/html; charset=utf-8",
                )
                return
            self._send(
                200, OAUTH_CALLBACK_PAGE.encode("utf-8"), "text/html; charset=utf-8"
            )
        elif path == "/api/oauth/pending":
            # M16 A step 4: the panel polls this with its state; a pending
            # flag is returned only for a matching state — never the code
            # itself (the code stays server-side).
            state = (urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query
            ).get("state") or [""])[0]
            with _lock:
                known = state in _oauth["expected_states"]
            pending = known and _oauth_pending_code(state) is not None
            self._json(200, {"pending": pending})
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
        if path == "/api/resume":
            self._handle_resume(int(self.headers.get("Content-Length", 0) or 0))
            return
        if path == "/api/key":
            self._handle_key(int(self.headers.get("Content-Length", 0) or 0))
            return
        if path == "/api/oauth/exchange":
            self._handle_oauth_exchange(int(self.headers.get("Content-Length", 0) or 0))
            return
        if path == "/api/oauth/state":
            self._handle_oauth_state(int(self.headers.get("Content-Length", 0) or 0))
            return
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
        try:
            _resolve_provider(options)
        except ValueError as e:
            self._json(400, {"error": str(e)})
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
        # M15 pre-flight (specs/05-ai-caller.md §Availability): LLM mode
        # with no stored key refuses before any work — never a silent
        # rule-based run. Rule-based mode (use_llm: false) always starts.
        if phase != "plan" and _resolve_use_llm(options):
            try:
                require_api_key(_resolve_provider(options))
            except LLMError as e:
                self._json(409, {"error": str(e)})
                return
        # M16 consent enforcement (specs/05-ai-caller.md §Free-tier
        # routing): a free_tier run is refused unless privacy_ack rides in
        # the body — the gate must not be UI-only.
        if options.get("free_tier") and not options.get("privacy_ack"):
            self._json(409, {
                "error": "free_tier requires privacy_ack: true — free models "
                "may log or train on inputs; consent is required before any "
                "free-mode run (see the panel's consent checkbox).",
            })
            return
        with _lock:
            _run.update(
                status="running", stage=None, phase=phase, started_at=time.time(),
                finished_at=None, error=None,
                llm_mode="llm" if _resolve_use_llm(options) else "rule-based",
                degraded_reasons=[],
                free_tier=bool(options.get("free_tier", False)),
                llm_model=None,
            )
        worker = _resume_pipeline if phase == "plan" else _run_pipeline
        t = threading.Thread(target=worker, args=(options,), daemon=True)
        t.start()
        with _lock:
            self._json(202, dict(_run))

    def _handle_resume(self, length: int) -> None:
        """M14 resume upload: raw bytes in, extraction runs immediately."""
        if length <= 0:
            self._json(400, {"error": "empty upload"})
            return
        if length > MAX_RESUME_BYTES:
            self._json(413, {"error": f"resume too large (max {MAX_RESUME_BYTES} bytes)"})
            return
        raw_name = urllib.parse.unquote(self.headers.get("X-Filename", ""))
        # Sanitized basename only — no separators, no traversal, ever.
        # Spaces are kept (harmless, and the name doubles as display text).
        name = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(raw_name.replace("\\", "/")).name)
        suffix = Path(name).suffix.lower()
        if name in ("", ".", "..") or suffix not in (".pdf", ".docx", ".txt"):
            self._json(415, {"error": f"unsupported resume type (want .pdf/.docx/.txt): {raw_name!r}"})
            return
        data = self.rfile.read(length)
        if suffix == ".pdf" and not data.startswith(b"%PDF"):
            self._json(415, {"error": "not a PDF (missing %PDF header)"})
            return
        if suffix == ".docx" and not data.startswith(b"PK\x03\x04"):
            self._json(415, {"error": "not a DOCX (missing zip header)"})
            return
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        target = UPLOAD_DIR / name
        target.write_bytes(data)
        from .resume import resume_to_skills_json

        try:
            _json_path, stats = resume_to_skills_json(
                target, use_llm=True, auto=True, ask_fn=None
            )
        except Exception as e:  # noqa: BLE001 — surfaced as 500
            traceback.print_exc()
            self._json(500, {"error": f"extraction failed: {e}"})
            return
        with _lock:
            _resume.update(
                path=str(target),
                filename=target.name,
                count=stats.get("phrases"),
                source=stats.get("source"),
            )
        resp = {
            "ok": True,
            "filename": target.name,
            "skills": stats.get("phrases"),
            "source": stats.get("source"),
            "provenance": stats.get("provenance"),
        }
        if stats.get("provenance") == "Rule-based":
            resp["warning"] = (
                "Skills extracted without the LLM (regex scan, lower fidelity)."
            )
        self._json(200, resp)

    def _handle_key(self, length: int) -> None:
        """M14 key entry: keyring ("remember") or session env. Never echoed."""
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise TypeError("body must be a JSON object")
        except (ValueError, TypeError) as e:
            self._json(400, {"error": f"bad JSON body: {e}"})
            return
        provider = str(body.get("provider") or "")
        api_key = body.get("api_key")
        remember = bool(body.get("remember", True))
        if provider not in PROVIDERS:
            self._json(400, {"error": f"unknown provider: {provider!r}"})
            return
        if not isinstance(api_key, str) or not api_key.strip():
            self._json(400, {"error": "api_key must be a non-empty string"})
            return
        key_env = PROVIDERS[provider]["key_env"]
        try:
            if remember:
                secrets.set_secret(key_env, api_key.strip())
                stored = "keyring"
            else:
                os.environ[key_env] = api_key.strip()
                stored = "session"
        except Exception as e:  # noqa: BLE001 — keyring backend missing etc.
            self._json(500, {"error": f"could not store key: {e}"})
            return
        self._json(200, {"ok": True, "key_set": True, "stored": stored})

    def _handle_oauth_state(self, length: int) -> None:
        """M16 A step 2/3: the panel registers its freshly minted state so
        the server can validate the callback's state server-side. Only the
        state value is registered — no secret material."""
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise TypeError("body must be a JSON object")
        except (ValueError, TypeError) as e:
            self._json(400, {"error": f"bad JSON body: {e}"})
            return
        state = body.get("state")
        if not isinstance(state, str) or not state or len(state) > 256:
            self._json(400, {"error": "state must be a non-empty string (<=256 chars)"})
            return
        with _lock:
            _oauth["expected_states"].add(state)
        self._json(200, {"ok": True})

    def _handle_oauth_exchange(self, length: int) -> None:
        """M16 A step 4: exchange the server-held code (paired with the
        panel's state) for a user-owned key and store it in the
        OPENROUTER_API_KEY keyring slot (same slot as the M14 paste form).
        The panel sends {code_verifier, state} — never the code. The key
        transits this handler only — never echoed, never chrome.storage.
        State mismatch or exchange failure -> nothing stored."""
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise TypeError("body must be a JSON object")
        except (ValueError, TypeError) as e:
            self._json(400, {"error": f"bad JSON body: {e}"})
            return
        state = body.get("state")
        code_verifier = body.get("code_verifier")
        if not isinstance(state, str) or not state:
            self._json(400, {"error": "state must be a non-empty string"})
            return
        if not isinstance(code_verifier, str) or not code_verifier:
            self._json(400, {"error": "code_verifier must be a non-empty string"})
            return
        # State must match a callback the server actually stored (checked
        # at exchange time, per §M16 A step 5).
        code = _oauth_consume_code(state)
        if code is None:
            self._json(409, {
                "error": "no pending OAuth code for this state (expired, "
                "already used, or the callback never completed)",
            })
            return
        try:
            resp = _exchange_openrouter_code(code, code_verifier)
        except Exception as e:  # noqa: BLE001 — surfaced as 502
            self._json(502, {"error": f"key exchange failed: {e}"})
            return
        key = resp.get("key")
        if not isinstance(key, str) or not key.strip():
            self._json(502, {"error": "exchange response carried no key"})
            return
        try:
            secrets.set_secret("OPENROUTER_API_KEY", key.strip())
        except Exception as e:  # noqa: BLE001 — keyring backend missing etc.
            self._json(500, {"error": f"could not store key: {e}"})
            return
        with _lock:
            _oauth["expected_states"].discard(state)
        self._json(200, {"ok": True, "key_set": True, "stored": "keyring"})

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
