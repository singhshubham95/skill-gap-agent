# Milestones

Build order. Each milestone ends with something runnable.

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
   per the rubric ([4-validation.md](4-validation.md)). All three pass
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
   is the proper fix, deferred ([7-open-items.md](7-open-items.md)).
   Plan output now includes per-verdict JD traceability.

**v1 COMPLETE** — all six milestones done. Remaining architecture item:
LangGraph wiring of the (currently sequentially-called) nodes, tracked in
[7-open-items.md](7-open-items.md). Next-version scoping comes after commit.

Model pick resolved at milestone 3: DeepSeek V4 Flash 0731 via OpenRouter
([7-open-items.md](7-open-items.md)).