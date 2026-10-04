# S7 — Flow Runner and Screen

Step order and display. Owns no domain logic — calls S1→S6.

**Status: Built** (M7 graph + M8 resume front-end + M11 local UI + M12 sweep
harness + M13 extension shell); M12/M13 verification harnesses Built;
M9 intake Designed; M14 `--trace` flag Designed.

## Runners

- `cli.py` (primary): LangGraph graph
  ingest → judge → [gate?] → rank → [synthesize?] → oss → output.
  State = serializable TypedDict only; S3 map in runtime registry keyed
  by `thread_id`. Human prompts via `ask_fn` → `interrupt()`; optional
  SQLite checkpointer (`--resume`). Replay-safe by design (resumes
  re-execute nodes; prints repeat — not a bug). Pending interrupts via
  `tasks[*].interrupts`, never `get_state().next`.
  M13 two-phase mode: `two_phase` state routes rank → `pause` (an
  `interrupt()` after ranking); a `Command(resume=...)` continues through
  synthesize → oss → output — the extension's Analyze/Generate buttons.
  Nodes report progress via `set_stage_listener()` (M13 completion of the
  M11 seam); `rank` writes `output/gaps.json` (served as `GET /api/gaps`).
- `m5_plan.py`: sequential runner, still works.
- `sweep.py` (M12): evaluation harness — runs the same stage functions once
  per seeded JD subset, sharing judge/gate/OSS caches across subsets
  (they are subset-independent) and writing per-subset plans under
  `output/sweeps/<sweep-id>/sNN/`. Not a pipeline stage; it owns no domain
  logic. Design in `01-system-overview.md` §M12 design.
- M8 front-end: non-JSON input → `resume_to_skills_json()` before graph
  starts. Flags: `--auto`, `--no-judge`, `--no-llm`, `--top N`, `--resume`.
- M14 (🎯 Designed): `--trace` on `cli.py` / `server.py` / `sweep.py` calls
  `tracing.enable_tracing()` before the graph is built and merges
  `tracing.run_config()` (run name, tags, model metadata) into the
  `thread_id` config. Off by default. Design in `01-system-overview.md`
  §M14 design.
  The M10 OSS flags (`--no-oss`, `--no-llm-oss`) live on `m5_plan.py`; the
  `cli.py` graph honors the same options as state fields (`skip_oss`,
  `no_llm_oss` — settable via `server.py`'s run contract).
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
  renderer became the extension side-panel body at M13.
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
  (The listener seam itself landed in `cli.py` with M13 — see the M13
  discovery note in `03-milestones.md`.)
- Chrome extension side panel (M13, Built): `extension/` (manifest v3,
  `chrome.sidePanel`). Capture JD (content script extracts the active
  LinkedIn JD, append-only `chrome.storage.local` list) → **Analyze gaps**
  (`POST /api/run` `phase: "gaps"` with the captured list; JDs land in
  `output/captured_jds/`, run pauses after rank, gap table from
  `GET /api/gaps`) → **Generate plan** (`phase: "plan"` resumes; `plan.html`
  in a sandboxed iframe). Every plan link opens in a new browser tab
  (`target='_blank'`) so clicking one cannot navigate the iframe away from
  the plan; a **Reopen plan** control re-points the iframe at the on-disk
  `plan.html` if the view is lost anyway. `GET /jds/<name>` (exact-name
  match) serves both `data/jds/` and `output/captured_jds/`. The panel
  renders JD text with `textContent` only; no CORS headers on the server —
  the extension calls with `host_permissions`. Design:
  `01-system-overview.md` §M13 design; install: `extension/README.md`.
- ASCII-safe console output (cp1252 guard).

## History (links, not copies)

- Decisions: `02-decisions.md` (M7 state-design + recalibration rows; M13
  side-panel / two-phase / no-CORS rows).
- Milestones: `03-milestones.md` M7, M8, M10 (oss node), M11 (local UI),
  M13 (extension shell + cli wiring completion).
- Deferred: `03-milestones.md` §Deferred #2 (done M7), #8 (web UI — done
  M11 + M13), #11 (JD scraping — manual capture covered by M13, automatic
  discovery still deferred), #12 (in-page gap marking).
- Open items: `03-milestones.md` §Open (msgpack registration, sweep ground
  truth).
