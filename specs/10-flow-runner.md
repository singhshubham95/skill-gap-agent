# S7 — Flow Runner and Screen

Step order and display. Owns no domain logic — calls S1→S6.

**Status: Built** (M7 graph + M8 resume front-end); local UI Designed
(M11); extension shell unscheduled.

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
  reuse `output.py::render_plan()` to also emit `output/plan.html` (same
  data, clickable issue links) or one single-file FastAPI page.
  M10 already ships the thin-slice `plan.html` (static, no JS);
  M11 hardens it into the local UI.
  `cli.py` / `m5_plan.py` stay the runners. The HTML renderer later becomes
  the extension side-panel body.
- ASCII-safe console output (cp1252 guard).

## History (links, not copies)

- Decisions: `02-decisions.md` (M7 state-design + recalibration rows).
- Milestones: `03-milestones.md` M7, M8, M10 (oss node), M11 (local UI); extension shell
  unscheduled (end goal in S6 `09-practice-planner.md`).
- Deferred: `03-milestones.md` §Deferred #2 (done M7), #8 (web UI),
  #11 (JD scraping — extension prerequisite).
- Open items: `03-milestones.md` §Open (msgpack registration).
