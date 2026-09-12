# Locked Decisions

Decisions made during scoping. This file is append-only: new decisions are
added, superseded ones are marked, never silently rewritten.

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | LangGraph ecosystem; user knows Python |
| Orchestration | LangGraph | Conditional confidence gate is a real branch, not a linear chain — the architectural point of the project |
| Graph store | **networkx** (in-memory, persisted to JSON on disk) | Zero setup cost; Neo4j migration is mechanical later because the schema (see [architecture.md](architecture.md)) is already Neo4j-shaped (deferred-enhancements #1) |
| Interface | CLI only | Fastest path to signal; web UI deferred |
| LLM provider | Cloud cheap tier behind a thin `judge()`-style interface (exact model: see [open-items.md](open-items.md)) | Judgment quality matters at the judge node — small local models are weakest exactly where this pipeline's core novel piece needs them most; a full run costs pennies. The interface makes later local-model benchmarking a config swap |
| Local models | Not for v1 default; later benchmark experiment (see deferred-enhancements #6) | If the judge produces garbage scores, we couldn't tell whether the architecture or the model was wrong. Benchmark only after the cloud baseline passes the rubric |
| Human-in-the-loop | Simple stdin prompt loop (print low-confidence items → ask → record override) | True LangGraph `interrupt()` + checkpointer adds resumable-runtime complexity a CLI doesn't need yet (deferred-enhancements #2) |
| Sourcing | LLM project-idea synthesis only | GitHub Issues API is a fragile external dependency (deferred-enhancements #3) |
| Seed data | Skills JSON + 13 JDs from the manual session (user-supplied files) | Doubles as the validation set — the project's own test data |
| Spec structure | Modular docs in flat `docs/`, no nested subdirectories | Each doc evolves independently (deferred-enhancements churns; decisions is append-only); ~6 files is the right granularity — finer splitting would hurt navigation |