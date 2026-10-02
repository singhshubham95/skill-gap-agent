# S7 — Flow Runner and Screen

Step order and display. Owns no domain logic — calls S1→S6.

**Status: Built** (M7 graph + M8 resume front-end + M11 local UI);
extension shell unscheduled.

## Runners

- `cli.py` (primary): LangGraph graph
  ingest → judge → [gate?] → rank → [synthesize?] → oss → output.
  State = serializable TypedDict only; S3 map in runtime registry keyed
  by `thread_id`. Human prompts via `ask_fn` → `interrupt()`; optional
  SQLite checkpointer (`--resume`). Replay-safe by design (resumes
  re-execute nodes; prints repeat — not a bug). Pending interrupts via
  `tasks[*].interrupts`, never `get_state().next`.
- `m5_plan.py`: sequential runner, still works.
- M8 front-end: non-JSON input → `resume_to_skills_json()` before graph
  starts. Flags: `--auto`, `--no-judge`, `--no-llm`, `--top N`,
  `--no-oss`, `--no-llm-oss` (M10).
- M10 node: `oss` runs after synthesis on the same top-n actionable gaps
  (cache-first; zero API calls on re-runs); `output` also emits
  `plan.html` (thin slice).

## Screens

- CLI console today. M11 (minimal local UI, **not** a Chrome extension):
  `server.py` (stdlib `http.server`, no new dep — same rationale as M10
  `urllib`): `GET /` lists `data/jds/*.txt|*.md` + Generate button;
  `POST /api/run` starts the `cli.py` graph `--auto` in a background
  thread (poll `GET /api/status`; loading screen until `node_output`
  finishes); `GET /plan.html` serves `output/plan.html` (same
  `render_plan_html` data, clickable GFI links). Options via JSON body:
  `top_n`, `skip_judge`, `skip_oss`, `no_llm_oss` (defaults mirror
  `cli.py`). Single-run guard (409 while running); status is
  `idle|running|done|error` with timestamps. Paths resolve from repo root,
  never hardcoded. `cli.py` / `m5_plan.py` stay the runners. The HTML
  renderer later becomes the extension side-panel body.
  M10 already ships the thin-slice `plan.html` (static, no JS);
  M11 hardens it into the local UI. Revised scope (user 2026-10-01):
  bookmarklet saves JD → `data/jds/` (S1 helper, Built) + local page lists
  folder contents + Regenerate button runs the `cli.py` graph `--auto`
  with a loading screen (judge/synthesis/OSS take minutes; poll status,
  show `plan.html` when `node_output` finishes). Built 2026-10-01:
  `m11_check.py` offline PASS (16 JDs listed, 202 + 409 guard,
  running → done, plan served); `ruff` clean.
  Enhancement 2026-10-02: nodes report via `cli.set_stage_listener()`
  (`ingest|judge|gate|rank|synthesize|oss|output`); `/api/status` carries
  `stage`, the index poll shows it. `GET /jds/<name>` (exact-name match)
  renders JD text; `render_plan_html(..., jd_files={title: filename})`
  links each gap's source JDs; `node_output` builds the map when state
  `link_jds` is set (server sets it; CLI default plain text).
- ASCII-safe console output (cp1252 guard).

## History (links, not copies)

- Decisions: `02-decisions.md` (M7 state-design + recalibration rows).
- Milestones: `03-milestones.md` M7, M8, M10 (oss node), M11 (local UI); extension shell
  unscheduled (end goal in S6 `09-practice-planner.md`).
- Deferred: `03-milestones.md` §Deferred #2 (done M7), #8 (web UI),
  #11 (JD scraping — extension prerequisite).
- Open items: `03-milestones.md` §Open (msgpack registration).
