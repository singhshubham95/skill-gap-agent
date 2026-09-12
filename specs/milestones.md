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
2. **Ingestion + target-ingestion + normalization.** Automate the manual parse;
   verify weights reproduce the manual frequency tally (e.g. "LangChain-family
   frameworks: 9/13 JDs").
3. **Transferability judge.** LLM-scored `TRANSFERS_TO` edges with pairwise
   pruning; sanity-check against the manual gap analysis.
4. **Confidence gate (stdin loop).** Validate against the Databricks-style
   ambiguous case.
5. **Gap ranking + project synthesis + output.** Ranked plan in markdown.
6. **Validation pass.** Full run vs. manual analysis against the rubric (see
   [validation.md](validation.md)); write the README case study.

Exact model pick happens at milestone 3 ([open-items.md](open-items.md)).