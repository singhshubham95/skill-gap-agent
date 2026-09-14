# Locked Decisions

Decisions made during scoping. This file is append-only: new decisions are
added, superseded ones are marked, never silently rewritten.

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | LangGraph ecosystem; user knows Python |
| Orchestration | LangGraph | Conditional confidence gate is a real branch, not a linear chain — the architectural point of the project |
| Graph store | **networkx** (in-memory, persisted to JSON on disk) | Zero setup cost; Neo4j migration is mechanical later because the schema (see [2-architecture.md](2-architecture.md)) is already Neo4j-shaped (deferred-enhancements #1) |
| Interface | CLI only | Fastest path to signal; web UI deferred |
| LLM provider | Cloud cheap tier behind a thin `judge()`-style interface (exact model: see [7-open-items.md](7-open-items.md)) | Judgment quality matters at the judge node — small local models are weakest exactly where this pipeline's core novel piece needs them most; a full run costs pennies. The interface makes later local-model benchmarking a config swap |
| Local models | Not for v1 default; later benchmark experiment (see deferred-enhancements #6) | If the judge produces garbage scores, we couldn't tell whether the architecture or the model was wrong. Benchmark only after the cloud baseline passes the rubric |
| Human-in-the-loop | Simple stdin prompt loop (print low-confidence items → ask → record override) | True LangGraph `interrupt()` + checkpointer adds resumable-runtime complexity a CLI doesn't need yet (deferred-enhancements #2) |
| Sourcing | LLM project-idea synthesis only | GitHub Issues API is a fragile external dependency (deferred-enhancements #3) |
| Seed data | Skills JSON + 13 JDs (user-supplied files, in `data/`) | Doubles as the validation set — the project's own test data |
| Spec structure | Modular specs in flat `specs/`, no nested subdirectories | Each spec evolves independently (deferred-enhancements churns; decisions is append-only); ~6 files is the right granularity — finer splitting would hurt navigation |
| **(Added M3)** LLM provider | **DeepSeek V4 Flash 0731** via OpenRouter (`deepseek/deepseek-v4-flash-0731`) | 284B MoE / 13B active — strong reasoning/agent capability at flash-tier pricing (~$0.035/M in, ~$0.106/M out); user has an OpenRouter key. GLM + OpenAI remain configured as calibration fallbacks. Supersedes the earlier "GLM 5.3 Flash" interim pick |
| **(Added M2)** Implied-skill handling | Agentic proposal flow, not a static set: detect implications from CV phrases, propose each with evidence, user approves (y/n/a), approvals persist | User identified the static set as a design gap — a CV never states 100% of skills, and only the user can judge "too generous vs. too strict." Evidence-backed proposals keep the human in control |
| **(Added M2)** External taxonomy | ESCO ICT subset as optional enrichment, graceful fallback to built-in tables | Public skill taxonomies exist (ESCO); use where applicable rather than hand-maintaining everything, but never hard-depend on an external file |