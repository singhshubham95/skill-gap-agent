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
  GET  /api/gaps    -> the run session's gaps.json (M13: ranked gaps for the
                       side panel; M9: served from output/sessions/<sha>/)
  GET  /api/intake/turn  -> M9 intake chat: the current question
  POST /api/intake/answer -> M9 intake chat: answer ({turn_id,text} |
                       {answers:{...}} | {skip:true}); completion continues
                       the run automatically into the graph half
  GET  /plan.html   -> serve output/plan.html (render_plan_html, GFI links)
  GET  /api/jds     -> JSON list of data/jds/*.txt|.md (folder contents)

M14 self-serve setup (specs/12-extension.md §M14):
  POST /api/resume  -> upload a resume (raw file bytes; original name in
                       X-Filename), validate (10 MB cap, .pdf/.docx/.txt,
                       magic bytes), store under output/uploads/, run the
                       M8 extraction immediately (blocks until done).
                       M24: X-Extraction-Mode (rule|paid|free, default
                       paid) governs the extraction call (rule = local
                       regex), X-Provider picks the LLM endpoint, and
                       free extraction requires X-Privacy-Ack: 1 (409
                       otherwise). X-Disclosure-Ack: 1 required (M21)..
                       M21: requires X-Disclosure-Ack: 1 (409 otherwise) —
                       the panel's data-disclosure consent, enforced
                       server-side (specs/12-extension.md §Data disclosure)
  GET  /api/providers -> [{id, model, key_set}] — key_set is a boolean;
                       key material is never returned by any endpoint
  GET  /api/key/status?provider=<id> -> M18 panel chip: {key_set, ok,
                       detail, checked_at}. ok is true/false/null
                       (verified / rejected / couldn't verify) from the
                       provider's auth-only key-info endpoint — no
                       billable call, no key material, TTL-cached.
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

Request protection (M20, specs/12-extension.md §Security posture): every
request passes a request-origin gate — if an `Origin` header is present it
must be the extension's (`chrome-extension://…`) or the server's own origin
(`http://127.0.0.1:<port>` / `http://localhost:<port>`); anything else
(including `Origin: null`) is refused 403 before any handler runs.
Headerless requests (navigations, CLI, mN_check harnesses) pass unchanged.
POSTs enforce Content-Type (`application/json`; `/api/resume`:
`application/octet-stream`), and an explicit run-body `skills_path` must be
an existing `.json` under the repo root or the OS temp dir. No CORS headers
on purpose — absent ACAO means even allowed cross-origin callers cannot
*read* responses. Server binds 127.0.0.1 only.

Run: python -m skill_gap_agent.server [--port 8000] [--skills <file>]
Then open http://localhost:8000/ — bookmarklet-saved JDs appear in the list.
"""

from __future__ import annotations

import html
import json
import os
import re
import tempfile
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


# --- M20 request protection (specs/12-extension.md §Security posture) ------


def _origin_ok(origin: str | None, port: int) -> bool:
    """Request-origin gate (pure — unit-tested in test_m20).

    No Origin header = browser navigation or non-browser client (CLI,
    mN_check harnesses) — allowed. Otherwise only the extension's own
    origin or the server's own origin (the M11 index page) may pass;
    web pages cannot omit or forge this header.
    """
    if origin is None:
        return True
    if origin.startswith("chrome-extension://"):
        return True
    return origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")


def _validate_skills_path(value) -> str | None:
    """M20 containment: an explicit run-body skills_path must be an
    existing .json under the repo root or the OS temp dir (check fixtures
    live there). Returns an error message, or None when acceptable.

    Defense in depth — the origin gate is the primary barrier; this kills
    the file-ingest primitive (arbitrary local file -> LLM prompt) even if
    the gate were bypassed. cli.py keeps unrestricted paths (terminal-side).
    """
    if not isinstance(value, str) or not value.strip():
        return "skills_path must be a non-empty string"
    p = Path(value).expanduser().resolve()
    if p.suffix.lower() != ".json":
        return f"skills_path must be a .json file: {value!r}"
    roots = (REPO_ROOT.resolve(), Path(tempfile.gettempdir()).resolve())
    if not any(p.is_relative_to(root) for root in roots):
        return (
            "skills_path must live under the repo root or the OS temp dir: "
            f"{value!r}"
        )
    if not p.is_file():
        return f"skills_path not found: {value!r}"
    return None

_lock = threading.Lock()
_run: dict = {
    "status": "idle",
    "stage": None,
    "phase": None,
    "pause_phase": None,  # M9: "intake" (chat) | "gaps" (M13 preview) | None
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

# M9 intake chat (specs/13-intake.md §In-panel intake): the paused
# conversation at Analyze gaps — its turn/answer endpoints read this state.
# A completed conversation auto-continues into the graph half.
_INTAKE: dict = {"sess": None, "options": None, "jds_path": None, "jd_files": None}

# M14: the uploaded resume a run should use when the body carries no
# explicit skills_path. Never chrome.storage — this is server-side state.
# M9: extraction runs at analyze, so the upload also stashes the M24
# extraction mode/provider chosen at upload time.
_resume: dict = {
    "path": None, "filename": None, "count": None, "source": None,
    "mode": None, "provider": None,
}

# M16 OAuth connect (specs/12-extension.md §M16 A): the one-time code
# OpenRouter redirects back with, kept in memory keyed by the panel's
# state with a 10-minute TTL. No key material is ever stored here — only
# the pending code, and it never leaves the server.
OAUTH_CODE_TTL_SECONDS = 600
_oauth: dict = {"codes": {}, "expected_states": set()}

# M18 key validation (specs/12-extension.md §M18): per-provider status
# cache so the panel's key chip never triggers a provider call per render.
KEY_STATUS_TTL_SECONDS = 120
_key_status_cache: dict[str, dict] = {}

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


def _key_status(provider: str) -> dict:
    """M18: key presence + validation status for the panel's state chip.

    Validation is llm.validate_api_key — the provider's key-info endpoint
    (auth-only, no billable call) — checked at most once per TTL window
    and cached per provider. The payload is booleans + short status text
    only: never key material. ok: None means "couldn't verify", which
    never blocks a run (specs/12-extension.md §M18)."""
    key_set = llm_mod.key_present(provider)
    now = time.time()
    with _lock:
        cached = _key_status_cache.get(provider)
    if key_set and cached and now - cached.get("checked_at", 0) < KEY_STATUS_TTL_SECONDS:
        return dict(cached)
    if not key_set:
        with _lock:
            _key_status_cache.pop(provider, None)
        return {"key_set": False, "ok": None, "detail": "no key stored",
                "checked_at": now}
    v = llm_mod.validate_api_key(provider)
    result = {
        "key_set": True,
        "ok": v.get("ok"),
        "detail": str(v.get("detail") or ""),
        "checked_at": now,
    }
    with _lock:
        _key_status_cache[provider] = dict(result)
    return result


def _invalidate_key_status(provider: str) -> None:
    """Drop the cached validation after a key change (save or OAuth)."""
    with _lock:
        _key_status_cache.pop(provider, None)


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


def _build_intake(source: Path, session: Path, jds_path: str, options: dict):
    """M9 intake prep at Analyze gaps (placement revision 2026-10-12).

    Extraction runs here (rule-only at upload since M9), the phrase/implied
    proposals and JD-aware triage feed the conversation, and an incomplete
    profile pauses the run at the intake chat. Returns the IntakeSession to
    pause on, or None when the profile is already complete (re-analysis asks
    nothing — same-input sessions resume).
    """
    from . import sessions
    from .implied import detect_implied
    from .ingest import jd_target_weights
    from .intake import IntakeSession
    from .normalize import canonical_term
    from .resume import extract_to_artifact, flatten_phrases
    from .validate import Validator, triage_skills

    profile = sessions.load_profile(source)
    if profile and profile.get("completed"):
        return None

    mode = (_resume.get("mode") or "paid").strip().lower()
    provider = _resolve_provider(options)
    use_llm = _resolve_use_llm(options)
    free_tier = bool(options.get("free_tier", False))
    cfg = LLMConfig(provider=provider, free_tier=free_tier)

    if source.suffix.lower() == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
    else:
        data, _src = extract_to_artifact(
            source,
            artifact_path=session / "extracted_skills.json",
            use_llm=(mode != "rule") and use_llm,
            cfg=cfg,
        )
    phrases = flatten_phrases(data)
    canonical = {canonical_term(p) for p in phrases}
    canonical.discard("")
    implied_list = [
        {"skill": i.skill, "evidence": i.evidence}
        for i in detect_implied(phrases, canonical, None)
    ]
    weights = jd_target_weights(Path(jds_path)) if Path(jds_path).is_dir() else {}
    triaged = triage_skills(weights, sorted(canonical)) if weights else []
    validator = None if not use_llm else Validator(session / "questions.json", cfg=cfg)
    sess = IntakeSession(
        source_sha=session.name,
        source_path=source,
        phrases=phrases,
        implied=implied_list,
        triaged=triaged,
        validator=validator,
        use_llm=use_llm,
    )
    first = sess.next_turn()
    return None if first is None or first.kind == "complete" else sess


def _run_pipeline(options: dict) -> None:
    """Background worker (phase "gaps"/"full"): M9 intake first, then the graph.

    Intake (specs/13-intake.md): extraction + chat pause at Analyze gaps;
    the conversation's /api/intake/answer completion continues into
    _run_graph_part automatically. With phase == "gaps" the graph run then
    pauses after ranking (the M13 two-phase preview).
    """
    from .cli import set_stage_listener

    os.chdir(REPO_ROOT)
    set_stage_listener(_set_stage)
    _drop_paused()
    source = _resolve_skills(options)
    provider = _resolve_provider(options)
    use_llm = _resolve_use_llm(options)
    if use_llm:
        # Race-safe backstop for the POST-layer pre-flight (M15): never
        # start a run that would silently degrade the whole pipeline.
        try:
            require_api_key(provider)
        except LLMError as e:
            with _lock:
                _run.update(status="error", finished_at=time.time(), error=str(e))
            return

    from . import sessions

    session = sessions.session_dir(source, create=True)
    sessions.retire_legacy_files(OUTPUT_DIR)  # M9 migration: retired globals
    with _lock:
        _run.update(session_dir=str(session))

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
        _copy_captured_to_session(session)

    try:
        sess = _build_intake(source, session, jds_path, options)
    except Exception as e:  # noqa: BLE001 — surfaced via /api/status
        traceback.print_exc()
        with _lock:
            _run.update(status="error", finished_at=time.time(), error=str(e))
        return
    if sess is not None:
        # Pause at the intake chat: the panel asks turns via /api/intake/*;
        # the completing answer continues this run (see _intake_answer).
        _INTAKE.update(
            sess=sess, options=options, jds_path=jds_path, jd_files=jd_files
        )
        with _lock:
            _run.update(
                status="paused", stage="intake", pause_phase="intake",
                finished_at=time.time(), error=None,
            )
        return
    _run_graph_part(options, session, jds_path, jd_files)


def _run_graph_part(
    options: dict, session: Path, jds_path: str, jd_files: dict
) -> None:
    """The graph half of a run (after any intake chat): ingest -> ... -> output."""
    from langgraph.checkpoint.memory import InMemorySaver

    from .cli import AgentState, build_app, pending_interrupt, set_stage_listener

    set_stage_listener(_set_stage)
    top_n = int(options.get("top_n", 5))
    phase = str(options.get("phase") or "full")
    two_phase = phase == "gaps"
    skills_path = _resolve_skills(options)
    provider = _resolve_provider(options)
    use_llm = _resolve_use_llm(options)
    free_tier = bool(options.get("free_tier", False))
    source_path = Path(skills_path)

    if source_path.suffix.lower() != ".json":
        # M8/M9 resume front-end: the extraction artifact lives in the
        # session (M14 SHA sidecar — same resume reuses it), and the phrase
        # review applies the intake chat's answers from the profile.
        from . import sessions as _sessions
        from .resume import resume_to_skills_json

        profile = _sessions.load_profile(source_path) or {}
        try:
            skills_path = str(
                resume_to_skills_json(
                    source_path,
                    artifact_path=session / "extracted_skills.json",
                    use_llm=use_llm,
                    auto=True,
                    ask_fn=None,
                    cfg=LLMConfig(provider=provider, free_tier=free_tier),
                    review_decisions=profile.get("phrases") or None,
                )[0]
            )
        except Exception as e:  # noqa: BLE001 — surfaced via /api/status
            traceback.print_exc()
            with _lock:
                _run.update(status="error", finished_at=time.time(), error=str(e))
            return

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
        "source_input": str(source_path),
        "session_dir": str(session),
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
                _run.update(
                    stage=None, pause_phase="gaps", finished_at=time.time(), error=None
                )
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
        _run.update(stage=None, pause_phase=None, finished_at=time.time(), error=None)


def _copy_captured_to_session(session: Path) -> None:
    """Audit copy of this run's captured JDs into the session store.

    The shared output/captured_jds/ stays (plan.html JD-link resolution,
    M13 fix); the session copy keeps the per-run record the M9 layout
    promises (specs/13-intake.md §Session store).
    """
    dest = session / "captured_jds"
    dest.mkdir(parents=True, exist_ok=True)
    for p in CAPTURED_DIR.iterdir():
        if p.is_file():
            (dest / p.name).write_bytes(p.read_bytes())


def _session_artifact(name: str) -> Path | None:
    """Run artifact path: the run's session dir (M9), output/ fallback.

    /api/gaps and /plan.html serve from the session the current run used.
    Strict once a session is set: a missing file is missing — never fall
    back to another run's stale artifact.
    """
    with _lock:
        sess = _run.get("session_dir")
    if sess:
        return Path(sess) / name
    legacy = OUTPUT_DIR / name
    return legacy


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

    def _origin_gate_ok(self) -> bool:
        """M20 request-origin gate — see §Security posture in the spec."""
        return _origin_ok(self.headers.get("Origin"), self.server.server_address[1])

    def do_GET(self) -> None:
        if not self._origin_gate_ok():
            self._send(403, b"forbidden origin", "text/plain")
            return
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
        elif path == "/api/key/status":
            # M18: key presence + validation chip for the panel. Booleans
            # and short status text only — never key material.
            provider = (urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query
            ).get("provider") or ["openrouter"])[0]
            if provider not in PROVIDERS:
                self._json(400, {"error": f"unknown provider: {provider!r}"})
                return
            self._json(200, _key_status(provider))
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
            gaps = _session_artifact("gaps.json")
            if gaps is None or not gaps.exists():
                self._json(404, {"error": "no gaps yet - run phase 'gaps' first"})
                return
            self._send(200, gaps.read_bytes(), "application/json")
        elif path == "/api/intake/turn":
            self._handle_intake_turn()
        elif path == "/plan.html":
            plan = _session_artifact("plan.html")
            if not plan.exists():
                self._send(
                    404,
                    b"<h1>No plan yet</h1><p>Click Generate plan first.</p>",
                    "text/html; charset=utf-8",
                )
                return
            # M19 (specs/12-extension.md §M19): theme override from the
            # panel's iframe URL — inject data-theme at serve time for
            # exactly the two valid values; anything else is ignored and
            # the on-disk file is never modified.
            data = plan.read_bytes()
            theme = (urllib.parse.parse_qs(
                urllib.parse.urlparse(self.path).query
            ).get("theme") or [""])[0]
            if theme in ("light", "dark"):
                data = data.replace(
                    b"<html>", f"<html data-theme='{theme}'>".encode(), 1
                )
            self._send(200, data, "text/html; charset=utf-8")
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
        if not self._origin_gate_ok():
            self._send(403, b"forbidden origin", "text/plain")
            return
        path = urllib.parse.urlparse(self.path).path
        # M20 Content-Type enforcement: a browser "simple request" cannot
        # carry these types cross-origin without a failing preflight, so
        # even a hypothetical origin-gate bypass cannot smuggle a body in.
        json_endpoints = (
            "/api/run", "/api/key", "/api/oauth/exchange", "/api/oauth/state",
            "/api/intake/answer",
        )
        if path == "/api/resume" or path in json_endpoints:
            expected = (
                "application/octet-stream" if path == "/api/resume"
                else "application/json"
            )
            ctype = (self.headers.get("Content-Type") or "").split(";")[0]
            if ctype.strip().lower() != expected:
                self._send(415, b"unsupported content type", "text/plain")
                return
        if path == "/api/resume":
            self._handle_resume(int(self.headers.get("Content-Length", 0) or 0))
            return
        if path == "/api/intake/answer":
            self._handle_intake_answer(int(self.headers.get("Content-Length", 0) or 0))
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
            if phase != "plan" and _run.get("pause_phase") == "intake":
                self._json(409, {
                    "error": "intake conversation in progress - answer the "
                    "chat first (/api/intake/*); it continues automatically",
                })
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
        # M20 containment (specs/12-extension.md §Security posture): an
        # explicit skills_path is refused outside the repo root / OS temp
        # dir before any run starts — the HTTP API never becomes a
        # local-file-ingest primitive. Checked after the gates above so the
        # M15/M16 refusals keep their exact ordering.
        if "skills_path" in options:
            err = _validate_skills_path(options.get("skills_path"))
            if err:
                self._json(400, {"error": err})
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

    def _handle_intake_turn(self) -> None:
        """M9: the current intake chat question (or completed)."""
        sess = _INTAKE.get("sess")
        if sess is None:
            self._json(409, {"error": "no intake conversation in progress"})
            return
        turn = sess.next_turn()
        if turn is None or turn.kind == "complete":
            sess.mark_completed()
            self._json(200, {"completed": True, "turn": None})
            return
        self._json(200, {
            "completed": False,
            "turn": {
                "id": turn.id, "kind": turn.kind, "prompt": turn.prompt,
                "payload": turn.payload,
            },
        })

    def _handle_intake_answer(self, length: int) -> None:
        """M9: answer one intake turn.

        Body: {turn_id, text} | {answers: {turn_id: answer}} (scripted) |
        {skip: true} ("use my resume as-is"). Every answer persists
        immediately (panel-close safe). When the conversation completes, the
        run continues automatically into the graph half (extract -> judge ->
        rank -> gaps pause).
        """
        sess = _INTAKE.get("sess")
        if sess is None:
            self._json(409, {"error": "no intake conversation in progress"})
            return
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise TypeError("body must be a JSON object")
        except (ValueError, TypeError) as e:
            self._json(400, {"error": f"bad JSON body: {e}"})
            return

        from .intake import drive

        try:
            if body.get("skip"):
                sess.skip()
            elif isinstance(body.get("answers"), dict):
                drive(sess, answers=body["answers"])
            else:
                turn = sess.next_turn()
                if turn is None or turn.kind == "complete":
                    sess.mark_completed()
                else:
                    turn_id = str(body.get("turn_id") or turn.id)
                    if turn_id != turn.id:
                        self._json(400, {
                            "error": f"turn {turn_id!r} is not current ({turn.id})",
                        })
                        return
                    result = sess.answer(turn.id, str(body.get("text") or ""))
                    if not result["ok"]:
                        self._json(400, {"error": result.get("error") or "bad answer"})
                        return
        except (KeyError, ValueError) as e:
            self._json(400, {"error": str(e)})
            return

        completed = bool(sess.profile.get("completed"))
        nxt = None if completed else sess.next_turn()
        if nxt is not None and nxt.kind == "complete":
            completed = True
            sess.mark_completed()
        if completed:
            self._continue_after_intake()
        self._json(200, {
            "ok": True,
            "completed": completed,
            "turn": None if completed else {
                "id": nxt.id, "kind": nxt.kind, "prompt": nxt.prompt,
                "payload": nxt.payload,
            },
        })

    def _continue_after_intake(self) -> None:
        """Kick the graph half of the run once the intake chat completes."""
        options = _INTAKE.get("options") or {}
        jds_path = _INTAKE.get("jds_path") or str(JD_DIR)
        jd_files = _INTAKE.get("jd_files") or {}
        session = Path(_run.get("session_dir") or OUTPUT_DIR)
        _INTAKE.update(sess=None, options=None)
        with _lock:
            _run.update(
                status="running", stage="ingest", pause_phase=None, error=None,
                started_at=time.time(),
            )
        threading.Thread(
            target=_run_graph_part, args=(options, session, jds_path, jd_files),
            daemon=True,
        ).start()

    def _handle_resume(self, length: int) -> None:
        """M14 resume upload. M9 (placement revision 2026-10-12): rule-only —
        save + readability check; extraction + intake chat run at Analyze."""
        # M21 (specs/12-extension.md §Data disclosure): the disclosure
        # consent gate is not UI-only — no client uploads without it.
        if self.headers.get("X-Disclosure-Ack") != "1":
            self._json(409, {
                "error": "disclosure consent required: confirm the panel's "
                "data disclosure before uploading (X-Disclosure-Ack: 1).",
            })
            return
        # M24 (specs/12-extension.md §M24): the mode governs extraction —
        # rule = local regex (nothing leaves the machine), paid/free = LLM
        # via the chosen provider. Extraction runs at Analyze (M9), so the
        # mode is stashed here and applied there.
        mode = (self.headers.get("X-Extraction-Mode") or "paid").strip().lower()
        if mode not in ("paid", "free", "rule"):
            self._json(400, {"error": f"bad extraction mode: {mode!r}"})
            return
        provider = (self.headers.get("X-Provider") or "openrouter").strip().lower()
        if provider not in PROVIDERS:
            self._json(400, {"error": f"unknown provider: {provider!r}"})
            return
        # M16's consent gate covers free-mode ingestion too (M24): free
        # providers may log/train on inputs — the resume is the most
        # sensitive data the product touches. Gate is not UI-only.
        if mode == "free" and self.headers.get("X-Privacy-Ack") != "1":
            self._json(409, {
                "error": "free extraction requires privacy consent "
                "(X-Privacy-Ack: 1) — free models may log or use inputs for "
                "training; confirm the consent checkbox first.",
            })
            return
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
        from .resume import save_upload

        try:
            target = save_upload(data, name, UPLOAD_DIR)
        except Exception as e:  # noqa: BLE001 — unreadable file (scanned PDF)
            self._json(415, {"error": f"resume unreadable: {e}"})
            return
        with _lock:
            _resume.update(
                path=str(target),
                filename=target.name,
                count=None,
                source=None,
                mode=mode,
                provider=provider,
            )
        self._json(200, {
            "ok": True,
            "filename": target.name,
            "stored": True,
            "mode": mode,
            "extract_at_analyze": True,
        })

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
        _invalidate_key_status(provider)  # M18: re-validate the new key
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
        _invalidate_key_status("openrouter")  # M18: re-validate the new key
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
    from . import sessions

    sessions.retire_legacy_files(OUTPUT_DIR)  # M9 migration: retired globals
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
