# Milestones

Build order. Each milestone ends with something runnable.

1. **Repo scaffold + seed data.** Project layout, deps, load skills JSON + 13
   JDs; hand-build the graph in networkx as a schema smoke test.
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