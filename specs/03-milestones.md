# Roadmap — Build Order, Trade-offs, Open Questions

Build order, deferred trade-offs, and open questions in one place
(merged 2026-09-27 from `5-milestones.md` + `6-deferred-enhancements.md`
+ `7-open-items.md`: all three talked about timeline — what is built,
what is next, what is deliberately postponed — so they are one file now).
Each milestone ends with something runnable.

1. **Repo scaffold + seed data.** ✅ Done. Python package (`src/skill_gap_agent/`),
   networkx + pydantic deps, `SkillGraph` schema module (all node/edge types,
   queries, JSON round-trip), seed loaders, smoke test. Verified against real
   seed data: 155 current skills + 13 JDs load; graph round-trips through
   `output/graph.json`. Seed data lives in `data/` (gitignored).
   - **Discovery for milestone 2:** the skills JSON contains long descriptive
     phrases (e.g. "Binary classification (large-scale, one-model-per-class
     reformulation...)"), not clean skill names — normalization must extract
     canonical skill terms.
2. **Ingestion + target-ingestion + normalization.** ✅ Done. `normalize.py`
   (canonical-term extraction + ~130-entry alias table), `ingest.py`
   (ingestion + target-ingestion with a curated, auditable JD keyword
   lexicon), `implied.py` (implied-skill detection + interactive y/n/a
   proposal flow with persisted approvals — replaces an earlier static
   `IMPLIED_SKILLS` set after the user identified it as a design gap),
   `taxonomy.py` (ESCO loader with graceful fallback; data file not yet
   downloaded). Verified: 146 raw phrases → 119 canonical + 23 user-approved
   implied skills; 13 JDs → 23 target skills; frequency tally matches the
   hand analysis's shape (RAG 12/13, LLMs 12/13, Python 11/13, GenAI 11/13).
3. **Transferability judge.** ✅ Core built and calibration-checked. LLM-scored
   `TRANSFERS_TO` edges with pairwise pruning (top-5 keyword-overlap candidates
   per target skill → ~1 call per target). Default model: DeepSeek V4 Flash
   0731 via OpenRouter. Calibration sample (5 skills): 0 errors, 7 edges,
   top-confidence spread 0.45–0.75 (mean 0.57) — no clustering. Rationales are
   well-calibrated (e.g. "Data quality gates → Data governance @ 0.75:
   directly supports a core pillar, though not security/metadata").
   **Known issue:** pruning missed the best candidates for LangGraph (should
   surface "Agentic application development (Google ADK)" and "NL-to-SQL
   agents" — keyword overlap is too weak for framework-adjacent skills) and
   AWS (should surface GCP skills as partial transfer). Fix: augment pruner
   with category/lexicon hints before the full run.
   **Status after fix + full run:** ✅ 21/21 skills judged, 122 edges, 0
   errors. Ground truth reproduced: LangGraph ← Google ADK @ 0.9 (partial-gap
   reasoning matches the hand analysis). **Open concern:** full-run top
   confidences cluster high (min 0.65, mean 0.84) vs. the sample's 0.45–0.75 —
   the judge is generous when many candidates are shown. Milestone 4's
   confidence gate + possible threshold raise (0.5 → ~0.7) must handle this;
   revisit before gap ranking.
4. **Confidence gate (stdin loop).** ✅ Implemented. **Design decisions from
   milestone-3 data:** scope = top edge per target skill (the top edge
   determines the verdict); threshold = 0.75 (at 0.5/0.6 nothing was flagged —
   the judge clusters high; 0.75 surfaces exactly the ambiguous cases:
   Streaming data, AWS, Data governance, Fine-tuning). **Design revision
   during validation (user feedback):** the first version asked the user to
   "correct the judge's numeric score" — flawed, because the user lacks the
   target skill by definition and cannot judge semantic transfer. Redesigned:
   the gate now asks **self-assessment questions only the user can answer** —
   depth of experience with the *source* skill (final confidence = judge
   score × depth factor) and intent (does the user want this skill area
   counted; "no" = explicit user-declared gap). The LLM scores semantic
   similarity; the gate injects self-assessed proficiency and intent the LLM
   cannot know. Bug fixed during testing: edge-direction mixup (in-edges for
   TRANSFERS_TO) and double `skill:` prefix on override writes.
   **Redesigned flow implemented** (`gate.py`): depth question (1–5 scale →
   multiplier 0.3/0.6/0.85/1.0/1.0 on the judge score) + intent question
   (count vs. user-declared gap); decisions persist to
   `output/gate_overrides.json` and apply silently on re-runs; decisions
   written onto the edge as `gate_depth`/`gate_intent`/`gate_note` properties.
   **Interactive validation run: ✅ complete.** User reviewed all 4
   sub-threshold targets: AWS (Cloud SQL depth 4 → 0.70 confirmed), Data
   governance (depth 4 → 0.70 confirmed), Fine-tuning (depth 3 → 0.59
   depth-adjusted), Streaming data (depth 3 → 0.55 depth-adjusted). The flow
   worked as designed — the user answered only self-assessment questions
   (their own depth + intent), never judged the unknown target skills.
   Decisions persisted to `output/gate_overrides.json`. **Milestone 4 done.**
5. **Gap ranking + project synthesis + output.** ✅ Done. `ranking.py`
   (transferability-aware: gap score = JD weight × (1 − top transfer
   confidence); verdict bands bridge ≥0.7 / partial ≥0.4 / gap below;
   gate-declared gaps keep full urgency), `synthesis.py` (one LLM call per
   top gap; prompt includes the gap's top TRANSFERS_TO edges with rationales
   + broader background so ideas reuse existing skills; writes Project nodes
   + CLOSES_GAP edges), `output.py` (ranked plan.md with verdict breakdowns
   + gate notes), `m5_plan.py` runner. Verified end-to-end on seed data:
   23 targets ranked (Azure 10.0 and Spark 4.0 top true gaps; AWS correctly a
   bridge at 2.7 despite 9 JDs thanks to the gate-adjusted transfer); 4
   projects synthesized grounded in existing skills (e.g. "Fine-Tuning BERT
   for Multi-Label Classification with Airflow Pipelines" — reuses their
   classification + Airflow background); plan.md + graph.json written.
6. **Validation pass.** ✅ Done. Full fresh pipeline run (judge re-called, no
   reuse) on the seed data; output compared against the sealed hand analysis
   per the rubric (now in S5 `08-gap-measurer.md` §Validation rubric). All three pass
   criteria met — the full comparison is recorded in that rubric (the README
   case study write-up was removed 2026-10-03 as redundant with it; evidence
   kept in the specs). The
   hand analysis's headline buckets (GenAI/LLM depth, framework breadth, cloud
   platforms) all appear in the ranked output; ADK→LangGraph partial-gap
   reproduced independently; the AWS ambiguous case was surfaced by the gate
   and correctly demoted below lower-demand true gaps in the final ranking.
   **Post-validation revision (user review of plan.md):** two ranking fixes —
   (a) held-skill bug: targets already resolved by the matching ladder were
   ranking as confidence-0 gaps (Azure #1, Spark #2 demanding "foundational
   learning" — flatly wrong); (b) alternative groups (`requirements.py`):
   JDs list capability categories as interchangeable brands ("Azure OpenAI,
   AWS Bedrock, GCP Vertex AI" = any-of), so holding GCP satisfies the
   cloud-platform intent — but groups NEVER erase specific gaps (LangChain
   stays full-urgency despite ADK; per-group mention policies are hand-set).
   Honest limitation recorded: per-JD mention-modality classification via LLM
   is the proper fix (deferred — see §Open: mention-modality below).
   Plan output now includes per-verdict JD traceability.

**v1 COMPLETE** — all six milestones done. The LangGraph wiring has since
been designed and scheduled as milestone M7 (below).

Model pick resolved at milestone 3: DeepSeek V4 Flash 0731 via OpenRouter
(see §Open: model pick below).

## Milestones (linear and global — M1…M13; M9 is the only one still Designed)

Versions are labels on milestone ranges (v1 = M1–M6 shipped; v2 = M7+
target), not spec boundaries. Numbering stays linear and global. M12 is an
evaluation harness over the built pipeline and M13 is the browser surface —
neither is a new pipeline stage.

7. **LangGraph orchestration.** ✅ Done. The v1 nodes are wired into a real
   LangGraph graph (`cli.py`): conditional gate as a branch (skipped when no
   sub-threshold targets remain), conditional synthesis (skipped when no
   actionable gaps), `interrupt()`-based human-in-the-loop via the `ask_fn`
   seam in `gate.py`/`implied.py`, optional SQLite checkpointer (`--resume`,
   `output/checkpoints.sqlite`). State is a TypedDict of serializable
   fields; the `SkillGraph` lives in a runtime registry keyed by `thread_id`
   (decision in [02-decisions.md](02-decisions.md) — the checkpointer
   serializes state channels, so a live networkx graph cannot live in
   state). **Learnings (verified against LangGraph 1.2.11):**
   - **Pending-interrupt detection quirk:** after a resume that immediately
     hits another `interrupt()` in the same node, `get_state().next` is
     empty even though a question is pending. The first m7_check run FAILED
     on exactly this (1 of 8 interrupts handled, run stalled). Fix: detect
     pending interrupts via `get_state().tasks[*].interrupts` — now a
     shared helper (`cli.py::pending_interrupt`) used by both the runner
     and the verification script. Documented in §9 so it isn't reintroduced.
   - **Replay semantics:** resuming re-executes the node from the top, so
     prints before a pending `interrupt()` repeat on every resume (visible
     as duplicated gate headers in the first failing run's log). This is
     load-bearing LangGraph behavior — nodes must stay replay-safe; do not
     suppress repeated side effects with state flags.
   - **Checkpoint serialization warning:** LangGraph warns that
     `GateDecision`/`Gap`/`SynthesizedProject` are unregistered msgpack
     types ("will be blocked in a future version"). Works today; registering
     them as allowed msgpack modules is a recorded open item
     (see §Open: checkpoint msgpack below).
   **Validation:** `m7_check.py` scripted-interrupt run — 8/8 interrupts
   surfaced and answered (4 skills × depth + intent), decisions persisted to
   `output/gate_overrides.json`, run completed to plan output. PASS. Lint
   clean. The judge-recalibration loop from the original §9 design was
   explicitly deferred during this milestone (decision in
   [02-decisions.md](02-decisions.md); trigger in
   §Open: judge calibration below).
8. **Resume ingestion.** ✅ Done. New `resume.py` + `vocab_bridge.py`;
   `pypdf`/`python-docx` added as required deps. Flow: resume file
   (PDF/DOCX/TXT) → text (scanned-PDF guard raises a clear error on
   image-only PDFs) → one LLM extraction call (noun-phrase evidence phrases,
   hierarchical, quote-anchored) → artifact persisted to
   `output/extracted_skills.json` → first-run y/n/a approval flow
   (`output/extracted_approvals.json`, silent after) → existing ingest
   unchanged. Regex fallback via existing lexicon tables (`--no-llm` or no
   API key). Not a graph node — the runner converts resume→JSON before the
   graph starts; `cli.py` branches on the input file's extension. Verified
   end-to-end: `cli.py data/Shubham_Singh.pdf data/jds --auto --no-judge`
   produces a ranked plan (Spark, Fine-tuning top gaps) from the PDF.
   **Learnings:**
   - **Prompt grammar matters more than prompt honesty.** The first
     extraction prompt asked for "evidence phrases" and the model returned
     resume SENTENCES ("Built NL-to-SQL agent...") — canonicalization
     collapsed and naive seed recall was 0%. The fix was teaching the model
     the seed's noun-phrase grammar with concrete style examples ("Agentic
     application development (Google ADK)"); recall rose to 40% (string
     metric) with the same underlying content.
   - **Validation metric correction (user decision):** naive recall vs. the
     seed JSON is the WRONG metric — the seed (146 phrases) aggregates
     resume versions + PSE documents + older material; the one-page resume
     is a current-role snapshot, so ~half the seed is not in the extraction
     input at all (verified by string search: no SAP/DAX/NumPy/KNN/PySpark/
     ONNX etc. in the resume text). Honest metric = resume content covered,
     which is high by inspection. Canonical M8-run counts (single source):
     76 extracted phrases → 59 canonical distinct + 41 implied accepted =
     100 skills in the resume graph; string-metric overlap with the seed is
     40% (47 of the seed's 118 canonical terms), with the missed set
     dominated by non-resume content.
   - **Vocabulary-bridge gap (designed + built):** the alias table was
     seed-vocabulary-specific ("Airflow orchestration" ≠ "Apache Airflow").
     Fix in two parts: ~50 manual alias entries for the observed variants,
     plus a new LLM-assisted bridge (`vocab_bridge.py`) that classifies
     canonical terms unmatched against the FULL existing vocabulary
     (seed canonical + implied + JD lexicon + alias values) as merge-or-new,
     persisting decisions to `output/vocab_bridge.json`. Validated on the
     resume data: 2 genuinely-new terms correctly identified; batched
     prompt (verdicts list) after the single-term shape proved unreliable.
   - **Umbrella phrases swallow sub-skills:** "Google Cloud Platform
     (BigQuery, Composer, GCS, Cloud Run, Vertex AI, GKE, IAM)" canonicalizes
     to GCP only; sub-skills survive via implied-skill detection — which
     needed a GKE pattern added. General pattern to watch for new inputs.
   - **Extraction latency:** the one extraction call took ~19 min on
     DeepSeek V4 Flash / OpenRouter (see §Open: extraction latency below);
     artifact reuse makes it a one-time cost per resume.
   **Status: built and validated on the user's real resume.**
9. **Conversational intake + skill validation.** 🎯 Designed
   (full design in [13-intake.md](13-intake.md)). Chat agent collects
   evidence (resume / JSON / JDs) and pre-fills gate questions; triaged
   skills validated via concept checklist + applied question with hidden
   rubric; grades persist to `output/proficiency.json` on the gate's 1–5
   depth scale; gate shrinks to unvalidated skills.
10. **OSS issue sourcing (GFI thin slice).** ✅ Built 2026-09-28
    (mechanics in S6 `09-practice-planner.md`). New `oss.py`
    consumed from `rank_gaps()` `Gap` objects: 2-attempt search loop
    (strict → broadened fallback) over GitHub Search Issues
    (`good first issue`) with curated-repo preference re-rank → S2
    relevance filter → persist `output/oss_issues.json` (query +
    attempts + timestamp). `Project` gains `type="oss_issue"`
    (`url, repo, labels, updated_at`); `CLOSES_GAP` reused. Wired as a
    `cli.py` node after synthesis (`--no-oss` / `--no-llm-oss` flags);
    `plan.md` + thin-slice `plan.html` render per-gap issue links.
    Verified: `m10_check.py` offline PASS (stub search, cache reuse,
    md+html); live seed run (`--auto --no-judge --top 2 --no-llm-oss`)
    sourced 5+5 issues with HTTP-200 links; second run zero API calls;
    `ruff` clean. Known limit: global search returns variably-relevant
    off-curated issues — quality ranking stays deferred (§Deferred #3);
    the search-and-reason refinement loop is the follow-up.
11. **Minimal local UI.** ✅ Built 2026-10-01
    (mechanics in S7 `10-flow-runner.md`). `server.py` (stdlib
    `http.server`, no new dep): `GET /` lists `data/jds/` + Generate
    button; `POST /api/run` runs the `cli.py` graph `--auto` in a
    background thread (poll `GET /api/status`; loading screen until
    `node_output` finishes); `GET /plan.html` serves `output/plan.html`
    (same `render_plan_html` data, clickable GFI links). Single-run guard
    (409 while running). Verified: `m11_check.py` offline PASS (16 JDs
    listed, 202 + 409 guard, running → done, plan served); `ruff` clean.
    Order held: M10 → M11 → then M9 and the extension shell
    (GFI-first pivot 2026-09-27). Bookmarklet saver
    (`tools/linkedin_jd_bookmarklet.js`, Built) drops JDs into `data/jds/`.
    **2026-10-03 M13 discovery (applies to M10 + this entry):** the
    `cli.py` wiring these entries describe (oss node after synthesis with
    `--no-oss`/`--no-llm-oss`-equivalent state flags, `plan.html` output,
    `cli.set_stage_listener()`, `jd_files` linking) was **not actually in
    `cli.py`** — it lived only in `m5_plan.py`, `sweep.py` and the
    `output.py` renderers, and `m11_check.py` failed on that tree. The
    wiring landed with M13 (the extension's backend is exactly this path);
    `m11_check.py` passes since. History kept as written above — the claims
    were accurate for `m5_plan.py`-driven runs, ahead of the code for
    `cli.py`.
12. **JD-subset sweep evaluation.** ✅ Built 2026-10-03
    (design in [11-sweep.md](11-sweep.md)). An **evaluation harness**
    (`sweep.py`), not a pipeline stage: it runs the existing pipeline once
    per JD subset and writes a reviewable record so the user can inspect
    which subset produced which plan. Design (sampling, shared caches,
    runner shape, output layout, manifest, metrics, two-pass review, done
    criteria) lives in [11-sweep.md](11-sweep.md) — not repeated here.
    - **Verified 2026-10-03:** `m12_check.py` offline PASS (sampling
      determinism + contrastive ordering, per-subset output isolation, judge
      cache sharing 4 new + 16 replays on the fixture, manifest/index
      completeness, metrics fixtures); `ruff check .` clean; live smoke sweep
      `python -m skill_gap_agent.sweep --seed 42 --n 2 --singletons 1 --top 2
      --id m12-smoke` completed end-to-end — 6 subsets, 0 new + 54 cached
      judge calls, 7 synthesized projects, mean top-5 Jaccard 0.833, 0
      superset violations, `output/sweeps/m12-smoke/index.md` reviewable.
    - **Learnings:**
      - **Judge-cache warm start confirmed on real data.** Seeding
        `_shared/judge_report.json` from `output/` made the smoke sweep spend
        **0** new judge calls (54 replays across 6 subsets) — the
        subset-independence property that justifies the shared cache holds
        against the real 16-JD data, not just fixtures. New targets cost one
        call each and persist per-call, so an interrupted sweep resumes
        without re-spending.
      - **Contrastive sampling found real structure.** The near-identical
        triple came out as three Optum postings (same-company near-duplicates)
        — token-Jaccard over JD text is enough to construct the contrastive
        subsets on real data.
      - **Scores are not comparable across subsets of different sizes.**
        `gap_score = weight × (1 − conf)` scales with how many subset JDs
        demand the skill: Fine-tuning scored 0.41 on triples vs 2.46 on the
        full set. Reviewers must compare ranks/verdicts across subsets, never
        raw scores (worth remembering when reading `index.md`).
      - **Ingestion counts drift from code, not just data.** The fresh
        snapshot (118 canonical / 41 implied / 19 targets) differs from the
        M2-era counts (119 / 23 / 23) on the same skills file — M8's
        normalize/implied work plus the persisted approval record (41
        accepted names, of which today's patterns re-propose 23). The
        manifest's per-JD + per-input hashes exist so drift is attributable.
      - **Offline check needed no monkeypatching.** `run_sweep` takes
        `judge_fn` / `synthesize_fn` / `search_fn` seams (defaults = real
        functions), so `m12_check.py` drives the true end-to-end path with
        fakes — including manifest/index writing.
13. **Chrome extension shell.** ✅ Built 2026-10-03
    (design in [12-extension.md](12-extension.md); end goal in S6
    `09-practice-planner.md` §End goal). MV3 side panel in `extension/`:
    capture JDs on LinkedIn → analyze gaps → generate the plan, with the
    pipeline running in the local `server.py` process. Design (side-panel
    choice, capture, run contract, two-phase pause, `reuse_judged`,
    rendering, security posture, non-goals, done criteria) lives in
    [12-extension.md](12-extension.md) — not repeated here. Per user
    priority 2026-10-03 the locked sequence was reordered: the extension
    shell jumped ahead of M9 (decision rows in `02-decisions.md`); M9
    remains the next milestone.
    - **M10/M11 wiring completed here (discovery).** The M10/M11 entries
      described the `cli.py` wiring as built, but the code had never landed
      there: `set_stage_listener`/`_stage`, the `oss` node, `plan.html`
      output and `jd_files` linking existed only in `m5_plan.py` /
      `sweep.py` / `output.py`'s renderers, and `m11_check.py` **failed**
      on the pre-M13 tree (`cli` had no `set_stage_listener`). Completed as
      part of M13 — the extension's backend is exactly this path — and
      `m11_check.py` now passes.
    - **Verified 2026-10-03:** `m13_check.py` offline PASS (cli wiring,
      manifest validity, two-phase flow through the real server + real graph
      with stubbed judge/synthesis/oss — captured-JD ingestion, `paused` →
      `/api/gaps`, `plan.html` with projects + GFI links, 409 on a stray
      phase `"plan"`); `m11_check.py` PASS (was failing pre-M13); `ruff
      check .` clean; `pytest` 3 passed (`test_m13.py` wrappers — the
      repo's first pytest tests); `node --check` clean on all three
      extension scripts. The extension shell is statically validated
      (manifest + JS + panel logic against the same endpoints); the first
      human click-through in Chrome is the user's one-time step
      (`extension/README.md`).
    - **Live smoke (2026-10-03, real data through the `server.py` contract):**
      three runs. (1–2) Seed profile + two captured JDs: capture → `paused`
      after rank → `/api/gaps` → `plan.html`; every gap came out
      bridge/alt-bridged (the seed profile genuinely covers those JDs), so
      synthesis/OSS correctly skipped — also a live check of the
      "no actionable gaps" path. (3) **Resume profile** (`skills_path:
      data/Shubham_Singh.pdf`, extraction artifact reused — 0 extraction
      LLM calls) + the Adobe/Optum JDs: 39 TRANSFERS_TO edges reused, 6
      targets freshly judged, gaps `Spark 0.8 partial` (actionable),
      `Data governance 0.6 bridge`, `Fine-tuning 0.3 bridge` …; phase
      `"plan"` resumed through synthesize → oss → `plan.html` (5.4 KB) with
      a Spark project + **2 live good-first-issue links**
      (apache/airflow#39184, kubeflow/spark-operator#2958) with LLM
      relevance rationales. The Spark/Fine-tuning ordering matches the M8
      resume-run record.
    - **Live-validation learning: the run contract needed a resume
      pre-step.** The first resume-profile run failed at ingest with a
      UTF-8 decode error — the pre-fix server passed the **PDF path**
      straight into the JSON reader (PDF binary byte `0xb5` at position
      11). Fix: `_run_pipeline` now runs the M8 `resume_to_skills_json()`
      before the graph for non-`.json` input (artifact reuse makes it
      free), exactly as `cli.main()` does — the design line "a resume file
      works too" was true of `cli.py` but not yet of the server path.
      Tracebacks are now printed in the server's error handlers for
      debuggability.
    - **Fix 2026-10-04 — plan links navigated the iframe away
      (user-reported).** Clicking any link in `plan.html` inside the side
      panel navigated the sandboxed iframe itself (external GFI links hit
      GitHub's `X-Frame-Options: deny`; nothing brought the plan back).
      Root cause: plain anchors navigate their containing frame, and
      `sandbox` blocks scripts/popups but not self-navigation. Fix: every
      `render_plan_html` link gets `target='_blank' rel='noopener
      noreferrer'`, the iframe carries
      `sandbox="allow-popups allow-popups-to-escape-sandbox"`, plus a
      **Reopen plan** control. Second bug found on the way: captured-JD
      links always 404'd — the viewer now serves both `data/jds/` and
      `output/captured_jds/`. Design detail in
      [12-extension.md](12-extension.md) §Rendering; decision rows in
      `02-decisions.md`. Verified 2026-10-04: `m13_check.py` extended;
      `ruff check .` clean, `pytest` clean, `m10_check`–`m13_check` PASS.

## Deferred — every v1 simplification + restore trigger (folded from `6-deferred-enhancements.md`, 2026-09-27)

This file churns; `02-decisions.md` is append-only. Entries marked
**→ Designed (Mn)** keep their v1 trade-off text for history.

| # | Deferred | v1 Simplification | Why deferred / trigger to restore |
|---|---|---|---|
| 1 | **Neo4j graph store** (Docker dev / AuraDB hosted) | networkx in-memory, persisted as JSON | Setup cost before any pipeline signal. Restore when persistence across sessions or Cypher demo value matters (v1.1). Schema in `06-skill-map.md` §Schema is already Neo4j-shaped. |
| 2 | **True LangGraph `interrupt()` + checkpointer** → Done (M7) | stdin prompt loop in the confidence gate | Resumable runtime adds complexity for a CLI. Restored for long-running/resumable runs. |
| 3 | **GitHub Issues sourcing node** (`good-first-issue`/`help-wanted` search) → Built thin slice (M10) | LLM project synthesis only | Fragile external dependency (rate limits, label quality varies by repo). Thin slice in M10 alongside synthesis; quality filtering + search-and-reason refinement loop remain deferred. |
| 4 | **Chat refinement over the built graph** ("why is X a gap", "re-rank assuming I know Y") | None — static plan output | A second app (tool-calling loop over graph queries). v1.2, after the graph is trustworthy. |
| 5 | **Embedding-based skill clustering** for dedup | Exact + alias match, LLM merge for ambiguous cases | Load-bearing but simple matching suffices for seed data. Restore if dedup errors visibly corrupt judge input. |
| 6 | **Local model benchmark** (small open models vs. cloud) on the judge node | Cloud cheap models only | Great portfolio experiment, but only meaningful once the cloud baseline passes the rubric. The thin `judge()` interface makes this a config swap. |
| 7 | **Resume (messy text) ingestion parity** → Done (M8) | Skills JSON is the primary path; resume parsing best-effort | Structured seed data exists; messy-text parsing is its own problem. |
| 8 | **Web UI** → Done (M11 local UI + M13 extension shell) | CLI | CLI-first decision. M11 local `plan.html` is the first step; extension shell after M9. (The shell in fact landed at M13, ahead of M9 — user priority 2026-10-03.) |
| 9 | **`TRANSFERS_TO` symmetry question** (does LangGraph experience transfer back to ADK familiarity equally?) | Directional edges only | Decide empirically once real scores exist. |
| 10 | **Confidence-threshold auto-tuning** | Manual threshold, start 0.5 → tuned to 0.75 at M4 | Tune empirically against the rubric after the first full run (done — see M4). |
| 11 | **JD auto-discovery/scraping** | User-supplied JDs | Explicit non-goal of v1; extension prerequisite (browser JD is the input). M13's Capture button covers manual browser-JD input; *automatic* discovery/scraping remains deferred. |
| 12 | **In-page gap marking** (content script wraps the JD text's matched skills on the page) | Gaps render as a table in the extension side panel only | User decision 2026-10-03 at M13 design time. Restore when the panel flow is trusted and visual marking on the JD page adds value; the capture extraction and gap data it needs already exist. |

## Open — unresolved items that don't block the next milestone (folded from `7-open-items.md`, 2026-09-27)

- **Extraction latency (S1/S2).** The M8 resume-extraction LLM call (one
  call, full resume text, hierarchical JSON out) took ~19 minutes via
  DeepSeek V4 Flash on OpenRouter (2026-09-23), vs. ~3–10s for
  small/medium prompts. Likely long reasoning on structured extraction;
  artifact reuse makes it one-time per resume, but interactive use is
  painful. Options: faster extraction model (mechanical, not judgment —
  a config change) or request timeout + retry in `llm.py`. Revisit if M9
  intake needs faster turnaround.
- **Checkpoint msgpack type registration (S7).** LangGraph (1.2.11) warns
  that `GateDecision`/`Gap`/`SynthesizedProject` are unregistered msgpack
  types ("will be blocked in a future version"). Works today; register
  them as allowed msgpack modules before the warning becomes an error.
  (Text after the header in the old file was truncated — this entry
  reconstructs the obvious intent; confirm on next M7 touch.)
- **Mention-modality classification, LLM pass (S4/S5).** Honest limitation
  of alternative groups (`requirements.py`): v1 cannot classify each JD
  mention's modality ("such as LangChain, ..." = exemplar/any-of vs. "must
  have production experience with LangChain" = strict/all-of). Per-group
  policy is a hand-set approximation. Future LLM pass per mention per JD
  feeding per-JD satisfaction into ranking — deferred until hand-set
  policies visibly misfire.
- **Proficiency data upstream (S5).** The skills JSON's own
  `self_assessment_flags` note suggests a future
  `skills_dataset_v2_rated.json` layering proficiency/recency per skill.
  If it exists, the gate's depth question pre-fills from it (and the judge
  prompt uses it too).
- **Judge score calibration (S5).** Full-run top confidences cluster high
  (min 0.65, mean 0.84); the gate's depth factor compensates. If ranking
  can't separate bridges from gaps, re-prompt the judge with a stricter
  rubric. The automatic re-judge loop was deferred at M7 (decision in
  `02-decisions.md`); revisit trigger: bridge/gap verdicts visibly misfire
  on clustered-high scores.
- **Alias table contents (S4).** Seeded (~130 entries) from M2 merges +
  ~50 M8 variants. The bridge (`vocab_bridge.py`) handles unanticipated
  variants; extend the manual table only for recurring variants.
- **Canonical-term extraction strategy (S4).** `normalize.py` regex +
  alias table; LLM fallback not needed so far; revisit only on new-data
  extraction errors.
- **External skill taxonomy ESCO (S4).** Loader with graceful fallback
  (`taxonomy.py`); data file not yet downloaded. To enable: fetch the ESCO
  ICT subset (EU Commission open data) as `data/taxonomy/esco_ict.json`
  with shape `[{"preferred": "...", "alt": [...], "broader": "..."}]`.
- **Implied-skill detection precision (S4).** Pattern-based works
  (14 on seed data, y/n/a flow). An LLM pass could catch subtler
  implications (e.g. "NL-to-SQL agents" → SQL depth); consider if the gap
  list looks wrong.
- **Vocabulary-bridge wiring (S4).** `vocab_bridge.py`
  (`bridge_vocabulary()` + `apply_bridge()`, decisions in
  `output/vocab_bridge.json`) is code-complete but unwired — no caller in
  `ingest.py` / `cli.py` imports it (status in S4 `07-skill-cleaner.md`).
  Open work: call it on unmatched canonical terms during ingestion and
  verify end-to-end on resume + seed data. Does not block M11.
- **Sweep ground truth (M12).** The sweep measures *stability and
  responsiveness* of the plan to the JD set, not correctness against a
  sealed ground truth — the M6 hand analysis covered 13 JDs and is not
  subset-partitioned. A per-subset hand analysis is the honest way to score
  plan *quality*; until then the sweep's automatic metrics flag where to
  look, and the two-pass manual review supplies the judgment. Revisit if
  sweep results need to be reported as accuracy numbers.
- **Hosting choice for demo (S7).** Local only for v1; AuraDB free tier
  when Neo4j is restored (Deferred #1).
- **Model pick (S2).** ~~Resolved at M3: DeepSeek V4 Flash 0731 via
  OpenRouter (see M3).~~ **Closed** — no longer an open item; the decision
  lives in [02-decisions.md](02-decisions.md) (M3 provider row) and the
  record in M3 above. Kept here only as a pointer.