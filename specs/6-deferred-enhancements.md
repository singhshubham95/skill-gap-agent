# Deferred Enhancements (Traded Off for v1)

Every simplification made in v1, recorded so each can be restored without
re-deriving the reasoning. This file churns; [3-decisions.md](3-decisions.md) is
append-only.

| # | Deferred | v1 Simplification | Why deferred / trigger to restore |
|---|---|---|---|
| 1 | **Neo4j graph store** (Docker dev / AuraDB hosted) | networkx in-memory, persisted as JSON | Setup cost before any pipeline signal. Restore when persistence across sessions or Cypher demo value matters (v1.1). Schema in [2-architecture.md](2-architecture.md) is already Neo4j-shaped. |
| 2 | **True LangGraph `interrupt()` + checkpointer** | stdin prompt loop in the confidence gate | Resumable runtime adds complexity for a CLI. Restore when moving to a web UI or long-running/resumable runs. |
| 3 | **GitHub Issues sourcing node** (`good-first-issue`/`help-wanted` search) | LLM project synthesis only | Fragile external dependency (rate limits, label quality varies by repo). Add in v1.1 alongside synthesis, run in parallel. |
| 4 | **Chat refinement over the built graph** ("why is X a gap", "re-rank assuming I know Y") | None — static plan output | A second app (tool-calling loop over graph queries). v1.2, after the graph is trustworthy. |
| 5 | **Embedding-based skill clustering** for dedup | Exact + alias match, LLM merge for ambiguous cases | Load-bearing but simple matching suffices for seed data. Restore if dedup errors visibly corrupt judge input. |
| 6 | **Local model benchmark** (small open models vs. cloud) on the judge node | Cloud cheap models only | Great portfolio experiment, but only meaningful once the cloud baseline passes the rubric. The thin `judge()` interface makes this a config swap. |
| 7 | **Resume (messy text) ingestion parity** | Skills JSON is the primary path; resume parsing best-effort | Structured seed data exists; messy-text parsing is its own problem. |
| 8 | **Web UI** | CLI | CLI-first decision. |
| 9 | **`TRANSFERS_TO` symmetry question** (does LangGraph experience transfer back to ADK familiarity equally?) | Directional edges only | Decide empirically once real scores exist. |
| 10 | **Confidence-threshold auto-tuning** | Manual threshold, start 0.5 | Tune empirically against the rubric after the first full run. |
| 11 | **JD auto-discovery/scraping** | User-supplied JDs | Explicit non-goal of the full spec's v1; unchanged. |