# Changelog (human tier)

> **Non-authoritative.** Per-task summaries only. Full history — decisions,
> verification records, learnings — lives in `specs/02-decisions.md` and
> `specs/03-milestones.md`.

Format: `- T-<id>: <what changed, one or two lines> (spec: <link>)`

Lines are added by the agent at task close (end-to-end pipeline, single
session). Milestone history M1–M15 predates this file and lives in
[specs/03-milestones.md](../specs/03-milestones.md) — not duplicated here.

## Entries

- M28-central-workspace: One central workspace, extension-only surface —
  the per-input session store is replaced by a single `output/` workspace
  (`store.py`), and `output/sessions/` is deleted. The resume identity
  survives as a **reuse guard** (`profile.source_sha256`, extraction
  sidecar) plus explicit invalidation on resume change, so one resume's
  depth answers still cannot reach another's analysis. New endpoints:
  `POST /api/jds/clear` (Clear list now deletes server-side),
  `POST /api/data/reset` (Delete all data), and
  `POST /api/session/{save,load,delete}` + `GET /api/session/{saved}` for
  user-named snapshots under `output/saved_sessions/`. The CLI interface
  is retired (`cli.py` keeps only the engine the server imports;
  `m5_plan`/`m4_gate`/`m3_judge` and the CLI-only checks deleted). Every
  offline check now runs against `checksupport.isolated_store()`, because
  a flat store means a check would otherwise overwrite real data.
  Verified: `pytest` 58 passed, `ruff` clean, all eight kept checks pass
  and leave `output/` byte-identical. (specs:
  [13-intake.md](../specs/13-intake.md) §Workspace store,
  [12-extension.md](../specs/12-extension.md) §Data controls,
  [03-milestones.md](../specs/03-milestones.md) M28)
- T-M27-artifact-placement: Diagnosis + design for "one session, one
  place" — the `output/` root held loose files duplicating the per-session
  folders. Three causes found: pre-M9 leftovers, root-**defaulted** write
  paths (the default was the bug, not the caller), and the deliberately
  shared `output/captured_jds/`. Two live defects reproduced: the README
  quickstart (`m5_plan --auto`) recreates the retired global
  `output/implied_skills.json`, and a leftover copy of that file is read
  back by the **sweep** and by two check harnesses — so one source's
  answers can be applied to a *different* source's session. The primary
  CLI and extension paths are unaffected (they delete the file at the
  start of a run). Target state and the three user decisions recorded; no
  code changed yet. (spec:
  [13-intake.md](../specs/13-intake.md) §Artifact placement,
  [03-milestones.md](../specs/03-milestones.md) M27)
- T-M15-fix-cache: Honest judge cache + Fresh analysis + debug log file —
  `reuse_judged` re-runs now make **zero** judge LLM calls for targets
  with a reusable stamped judgment (the M13 promise; previously every
  target was re-judged anyway) and a fresh judgment clears the `cached`
  marker explicitly (networkx keeps unmentioned edge attributes, so fresh
  scores were rendering as "LLM (cached)" after being paid for). New
  panel control **Fresh analysis** clears just the judgment caches
  (`graph.json`, `judge_report.json`, `questions.json`) via
  `POST /api/session/clear-cache` — chat answers and captured JDs
  survive. `--debug` mirrors the stage log to
  `output/logs/server-<timestamp>.log` (the console scrollback truncated
  the incident's own logs). (specs:
  [12-extension.md](../specs/12-extension.md) §Judge cache reuse + §Fresh
  analysis, [14-observability.md](../specs/14-observability.md) §Local
  debug mode)
- T-M9-fix-ux: Phrase-review UX + safety — the phrase question no longer
  dumps every extracted phrase in one 80-line prompt: gap-relevant phrases
  are listed first under the extractor's own category headers, the rest
  kept automatically (`show background` reviews them). Answer grammar is
  closed: bare `none`/`n`/`no`/prose is rejected with a hint, whole-set
  dropping requires the explicit `drop all` (a bare "none" silently emptied
  a user's 80-phrase skill graph in the live run). Panel send gives
  immediate feedback (pending hint, single-flight, inline errors); depth
  and checklist answers reject pasted prose instead of scraping digits
  out of it; cached transfer edges whose source skill was dropped no
  longer replay as "LLM (cached)" rows; `--debug` now logs why an intake
  answer was rejected and the kept/dropped counts (spec:
  [13-intake.md](../specs/13-intake.md) §Phrase review)
- T-M26: Local debug mode for extension testing — `server.py --debug
  [--debug-payloads]` (also `start-server.bat --debug`) adds local-only
  stage logs (request → run → all 8 LangGraph nodes → LLM call summaries)
  correlated by the run's `thread_id` (in `/api/status`); prompt/response
  bodies (resume/JD PII) behind `--debug-payloads`; normal output
  byte-stable (spec: [14-observability.md](../specs/14-observability.md)
  §Local debug mode)
- T-M9-fix-intake: Item-level intake freshness — a `completed` profile no
  longer silently skips the chat (it hid new items after an extraction
  change, and a scripted validation run had polluted the real session);
  re-opened chats derive completion from the turn machine (never the stale
  flag); "use as-is" is sticky + terminal; extraction class unified across
  chat/graph halves (M24 rule-mode respected); skipped chats surface
  `intake_note`; `SKILL_GAP_SESSIONS_DIR` isolates validation runs
  (spec: [13-intake.md](../specs/13-intake.md) §Freshness)
- T-M25: Fix gate-profiling crash on equal-confidence ties — `max()` over
  `(confidence, edge_dict)` tuples compared dicts on ties (TypeError right
  after judging; found by the M24 live pass 2026-10-12); compares plain
  floats now, red→green regression in `m7_check` (spec:
  [03-milestones.md](../specs/03-milestones.md) M24 learning (c))
- T-M9-impl: Conversational intake + skill validation (C3) built —
  in-panel intake chat at Analyze gaps, SHA-keyed session store
  (`output/sessions/<sha>/profile.json`), depth-aware judge with
  profile-stamped caches, gate no-double-count rule, legacy global
  decision files retired; upload is rule-only (extraction moves to
  analyze). Verified: m9_check FULL PASS, ruff clean, pytest 51 passed,
  full check sweep green, live end-to-end run (degradation paths —
  provider key expired) (spec: [13-intake.md](../specs/13-intake.md))
- T-M24: Mode governs ingestion — free/paid/rule now applies to resume
  extraction too (rule = local regex, nothing leaves the machine); Setup
  order = AI access → mode + consent → resume; mode-aware extraction
  cache; `POST /api/resume` gains mode/provider/consent headers; live
  pass pending (spec: [12-extension.md](../specs/12-extension.md) §M24)
- T-M23: LinkedIn posture — assist, don't act: the content script never
  clicks page controls; truncated JDs get the "…see more" button scrolled
  into view, focused and highlighted (Ctrl+F-style) for the user to click
  themselves; capture guardrails explicit; mitigates L3 (spec:
  [12-extension.md](../specs/12-extension.md) §Capture)
- T-M22: Store readiness — hosted privacy policy (`docs/`, GitHub Pages)
  with the Limited Use statement + named destinations,
  `CHROMEWEBSTORE.md` submission register (per-permission justifications,
  declarations, listing copy with LinkedIn + AI disclaimers), generated
  placeholder icons + manifest wiring, `THIRD-PARTY-NOTICES`; prepares
  blockers L1/L2/L6/L7 (spec:
  [12-extension.md](../specs/12-extension.md) §Data disclosure)
- T-M21: Honest data disclosure — banned the "stays on your machine" claim
  (the file is local; the extracted text goes over HTTPS to the selected
  AI provider, never to the developer), named destinations (OpenRouter →
  DeepSeek, Z.ai GLM, OpenAI; GitHub gets skill-gap terms only), first-use
  consent gating upload + analyze with a server-enforced
  `X-Disclosure-Ack`; fixes S2 + the disclosure side of L5 (spec:
  [12-extension.md](../specs/12-extension.md) §Data disclosure)
- T-M20: Public-release hardening — request-origin gate (web pages can no
  longer call the local agent), Content-Type enforcement, `skills_path`
  containment, https-only non-loopback `serverBase`; closes security
  findings S1/L4 (spec:
  [12-extension.md](../specs/12-extension.md) §Security posture)
- T-M19: Light/dark theme — panel + plan follow the OS theme
  (`prefers-color-scheme`) with a minimal Auto/Light/Dark override button;
  plan follows via serve-time `?theme=` injection (plan.html stays
  JS-free); visual pass confirmed 2026-10-11 (spec:
  [12-extension.md](../specs/12-extension.md) §M19)
- T-M18: Panel simplification — state-driven side panel (key check →
  free/paid/rule mode chips or "Create free LLM key"; paste form behind
  "I already have a key"), key validation via the free key-info endpoint
  (status chip only), collapsed Settings, merged gap-table provenance
  captions; live interactive pass pending (spec:
  [12-extension.md](../specs/12-extension.md) §M18)
- T-M16: Free-tier LLM access — panel "Connect free LLM" (OpenRouter OAuth
  PKCE → OS keyring, no pasting), opt-in free-model mode behind a consent
  gate, retry hardening (classification, bounded attempts, `:free`
  fallback, per-touchpoint timeouts); live interactive pass closed
  2026-10-11 via the M18 live pass (spec:
  [05-ai-caller.md](../specs/05-ai-caller.md) §Free-tier routing)
