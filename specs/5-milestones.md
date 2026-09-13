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
   manual run's shape (RAG 12/13, LLMs 12/13, Python 11/13, GenAI 11/13).
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
   reasoning matches the manual analysis). **Open concern:** full-run top
   confidences cluster high (min 0.65, mean 0.84) vs. the sample's 0.45–0.75 —
   the judge is generous when many candidates are shown. Milestone 4's
   confidence gate + possible threshold raise (0.5 → ~0.7) must handle this;
   revisit before gap ranking.
4. **Confidence gate (stdin loop).** Validate against the Databricks-style
   ambiguous case. **Design input from milestone 3:** full-run top confidences
   cluster high (mean 0.84), so a 0.5 threshold would flag nothing — decide
   threshold (~0.7?) and scope (top edge per skill vs. all edges) with the
   real edge data.
5. **Gap ranking + project synthesis + output.** Ranked plan in markdown.
6. **Validation pass.** Full run vs. manual analysis against the rubric (see
   [4-validation.md](4-validation.md)); write the README case study.

Model pick resolved at milestone 3: DeepSeek V4 Flash 0731 via OpenRouter
([7-open-items.md](7-open-items.md)).