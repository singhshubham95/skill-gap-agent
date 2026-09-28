# Roadmap — Build Order, Trade-offs, Open Questions

Build order, deferred trade-offs, and open questions in one place
(merged 2026-09-27 from `03-milestones.md` + `6-deferred-enhancements.md`
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
   criteria met — see the README case study for the full comparison. The
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
   is the proper fix (deferred — see §Deferred #10 below).
   Plan output now includes per-verdict JD traceability.

**v1 COMPLETE** — all six milestones done. The LangGraph wiring has since
been designed and scheduled as milestone M7 (below).

Model pick resolved at milestone 3: DeepSeek V4 Flash 0731 via OpenRouter
(see §Open: model pick below).

## Planned Milestones (v2 target — Designed, no code yet)

Versions are labels on milestone ranges (v1 = M1–M6 shipped; v2 = M7–M9
target), not spec boundaries. Numbering stays linear and global.

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
   (full design in `01-system-overview.md` §M9 design). Chat agent collects
   evidence (resume / JSON / JDs) and pre-fills gate questions; triaged
   skills validated via concept checklist + applied question with hidden
   rubric; grades persist to `output/proficiency.json` on the gate's 1–5
   depth scale; gate shrinks to unvalidated skills.
10. **OSS issue sourcing (GFI thin slice).** 🎯 Designed
    (end goal + mechanics in S6 `09-practice-planner.md`). New `oss.py`
    consumed from `rank_gaps()` `Gap` objects: curated repos → GitHub
    Search Issues (`good-first-issue`) → S2 relevance filter → persist
    `output/oss_issues.json`. `Project` gains `type="oss_issue"`.
11. **Minimal local UI.** 🎯 Designed
    (mechanics in S7 `10-flow-runner.md`). `output.py::render_plan()` also
    emits `output/plan.html` (same data, clickable issue links) — later the
    extension side-panel body. Not a Chrome extension. Order: M10 → M11 →
    then M9 and the extension shell (GFI-first pivot 2026-09-27).

## Deferred — every v1 simplification + restore trigger (folded from `6-deferred-enhancements.md`, 2026-09-27)

This file churns; `02-decisions.md` is append-only. Entries marked
**→ Designed (Mn)** keep their v1 trade-off text for history.

| # | Deferred | v1 Simplification | Why deferred / trigger to restore |
|---|---|---|---|
| 1 | **Neo4j graph store** (Docker dev / AuraDB hosted) | networkx in-memory, persisted as JSON | Setup cost before any pipeline signal. Restore when persistence across sessions or Cypher demo value matters (v1.1). Schema in `01-system-overview.md` §Graph Schema is already Neo4j-shaped. |
| 2 | **True LangGraph `interrupt()` + checkpointer** → Done (M7) | stdin prompt loop in the confidence gate | Resumable runtime adds complexity for a CLI. Restored for long-running/resumable runs. |
| 3 | **GitHub Issues sourcing node** (`good-first-issue`/`help-wanted` search) → Designed (M10) | LLM project synthesis only | Fragile external dependency (rate limits, label quality varies by repo). Thin slice in M10 alongside synthesis; quality filtering remains deferred. |
| 4 | **Chat refinement over the built graph** ("why is X a gap", "re-rank assuming I know Y") | None — static plan output | A second app (tool-calling loop over graph queries). v1.2, after the graph is trustworthy. |
| 5 | **Embedding-based skill clustering** for dedup | Exact + alias match, LLM merge for ambiguous cases | Load-bearing but simple matching suffices for seed data. Restore if dedup errors visibly corrupt judge input. |
| 6 | **Local model benchmark** (small open models vs. cloud) on the judge node | Cloud cheap models only | Great portfolio experiment, but only meaningful once the cloud baseline passes the rubric. The thin `judge()` interface makes this a config swap. |
| 7 | **Resume (messy text) ingestion parity** → Done (M8) | Skills JSON is the primary path; resume parsing best-effort | Structured seed data exists; messy-text parsing is its own problem. |
| 8 | **Web UI** | CLI | CLI-first decision. M11 local `plan.html` is the first step; extension shell after M9. |
| 9 | **`TRANSFERS_TO` symmetry question** (does LangGraph experience transfer back to ADK familiarity equally?) | Directional edges only | Decide empirically once real scores exist. |
| 10 | **Confidence-threshold auto-tuning** | Manual threshold, start 0.5 → tuned to 0.75 at M4 | Tune empirically against the rubric after the first full run (done — see M4). |
| 11 | **JD auto-discovery/scraping** | User-supplied JDs | Explicit non-goal of v1; extension prerequisite (browser JD is the input). |

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
- **Hosting choice for demo (S7).** Local only for v1; AuraDB free tier
  when Neo4j is restored (Deferred #1).
- **Model pick (S2).** Resolved at M3: DeepSeek V4 Flash 0731 via
  OpenRouter (see M3).