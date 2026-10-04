# C2 — Chrome Extension Shell

Browser surface for the pipeline: capture job descriptions on LinkedIn,
analyze gaps, and generate the learning plan in a side panel — with the
pipeline running in the local `server.py` process. The extension is a thin
client.

**Status: Built** (M13, 2026-10-03; link-navigation fix 2026-10-04 —
verification record in [03-milestones.md](03-milestones.md) M13). Code:
[../extension/](../extension/), `m13_check.py`. End goal (why this exists):
S6 [09-practice-planner.md](09-practice-planner.md) §End goal.

## End-user flow

The user browses LinkedIn job descriptions in Chrome. Clicking the extension
action opens a **side panel** — window-level, it stays open while the user
switches tabs or navigates between JDs. Per JD: click **Capture JD**
(append to an only-growing list shown in the panel). Then **Analyze gaps**
→ the ranked gap table renders in the panel. Then **Generate plan** →
projects + good-first-issues render below the gaps. Nothing navigates away;
the local pipeline does the thinking.

## UI surface = Chrome side panel

(decision rows in [02-decisions.md](02-decisions.md)). The popup was
rejected: it closes on any click-away, which kills the capture loop (browse
JD → return to panel). The in-page overlay was rejected: navigating to the
next JD destroys the DOM node, so state must survive in extension storage
anyway. The side panel is the platform's answer to exactly this workflow.

## Capture

A content script on `https://www.linkedin.com/jobs/*` ports the extraction
logic of
[../tools/linkedin_jd_bookmarklet.js](../tools/linkedin_jd_bookmarklet.js)
(find the `[id^="JobDetails_AboutTheJob_"]` block, click its expand button,
take `innerText` + `document.title` + `location.href`). The panel asks the
active tab via `chrome.tabs.sendMessage`; the content script answers with
`{title, url, text}`. The list lives in `chrome.storage.local`
(`capturedJds`, deduped by URL, re-capture updates text). No `tabs` /
`activeTab` permissions: the content script returns everything the panel
needs. JD text is **untrusted web content** — the panel renders it with
`textContent` only, never `innerHTML`.

## Run contract (extension → local server)

`POST /api/run` body:
`{phase, jds, top_n, skills_path?, skip_judge?, skip_oss?, no_llm_oss?}`.

| `phase` | Behaviour |
|---|---|
| `"gaps"` | Write each captured JD to `output/captured_jds/*.txt` (same `title\nurl\n\ntext` shape as the bookmarklet; `ingest.py::ingest_jds` reads the folder unchanged — it replaces `data/jds/` as `jds_path`), then run the `cli.py` graph with `two_phase=True`: the graph pauses at a `pause` node right after `rank` via `interrupt()`; status becomes `paused`. `GET /api/gaps` then serves `output/gaps.json` (written by the rank node). |
| `"plan"` | Resume the paused run (`Command(resume=...)`) through `synthesize` → `oss` → `output`; `GET /plan.html` serves the result. 409 if no run is paused. |
| (absent — legacy M11) | Full one-shot run, as before. |

Single-run guard unchanged (409 while `running`). `skills_path` defaults to
`data/skillsdataset.json` (server `--skills` flag); a resume file works too
(M8 extraction runs before the graph).

## Why one graph with a pause, not two runs

The pause is the same `interrupt()` machinery the confidence gate uses (M7):
state continuity is free — the same `SkillGraph` instance and the same
`gaps` list flow from phase 1 into phase 2. A second full run would
re-ingest and re-judge (or require cache plumbing to avoid it). The
checkpointer records the pause; the SkillGraph itself stays in the in-memory
runtime registry (decision in [02-decisions.md](02-decisions.md)), so both
phases must run in one server process — true for the side-panel workflow.

## Judge cache reuse for re-analysis (`reuse_judged`)

The M12 insight (see [11-sweep.md](11-sweep.md)) — the judge's score for
target `T` is a pure function of `T` — means that re-analyzing after adding
one JD must not re-pay ~20 LLM calls. With `reuse_judged`, the judge node
first copies `TRANSFERS_TO` edges from `output/graph.json`, then judges only
targets still unmatched; the judge report merges by target. The CLI default
stays fresh-judging (the M6 validation semantics); the extension sets the
flag.

## Rendering

The gap table is rendered natively in the panel from `/api/gaps` JSON. The
full plan renders in an
`<iframe sandbox="allow-popups allow-popups-to-escape-sandbox">` pointed at
`/plan.html` — the M10 renderer (self-contained, escaped, no JS) becomes the
side-panel body as S6 predicted. Every plan link carries
`target='_blank' rel='noopener noreferrer'`, so clicking one opens a new
browser tab and can never navigate the iframe away from the plan (amended
2026-10-04 after a user-reported mis-click lost the plan — fix note in
[03-milestones.md](03-milestones.md) M13). The two `allow-popups*` tokens
are what make `target='_blank'` work inside a sandbox at all (without them
the popup is silently blocked or inherits the no-script sandbox);
`allow-scripts` stays off. A **Reopen plan** control re-points the iframe at
`/plan.html` — the file stays on disk, so recovery costs no re-run. JD links
resolve against `data/jds/` **and** `output/captured_jds/` (exact-name
matches only), so extension-run links work too.

## Security posture

Server binds `127.0.0.1` only. **No CORS headers on purpose**: the extension
calls with `host_permissions` for `http://localhost:8000/*` +
`http://127.0.0.1:8000/*` (which bypass CORS entirely), while absent
`Access-Control-Allow-*` + no `OPTIONS` handler means hostile web pages can
neither read resume-derived gaps nor trigger runs (JSON `Content-Type`
forces a preflight, which fails). Trust model: any local process can reach
the server — same as M11, acceptable for a personal tool.

## Explicit non-goals (M13)

In-page gap marking on the JD text
([03-milestones.md](03-milestones.md) §Deferred #12), generic non-LinkedIn
JD pages (content-script matches are LinkedIn-only, like the bookmarklet),
run history, hosting, multi-user auth, Chrome Web Store packaging.

## Done criteria (met at M13 — verification record in roadmap M13)

1. Capture → analyze → plan completes from the extension against the local
   server.
2. `phase: "gaps"` produces `/api/gaps` and pauses, `phase: "plan"` resumes
   to `plan.html` with GFI links.
3. `m13_check.py` verifies the flow offline (stubbed judge/synthesis/search)
   — two-phase pause/resume, captured-JD ingestion, gaps artifact, manifest
   validity.
4. `ruff check .` and `pytest` clean.

## History (links, not copies)

- Decisions: [02-decisions.md](02-decisions.md) (M13 rows — side panel,
  two-phase pause, captured JDs, no-CORS, M13-before-M9, gap table,
  `reuse_judged`, link fix, JD viewer fix).
- Milestones: [03-milestones.md](03-milestones.md) M13 (verification record
  + learnings).
- Deferred: [03-milestones.md](03-milestones.md) §Deferred #12 (in-page gap
  marking).
- Install / load-unpacked instructions: [../extension/README.md](../extension/README.md).