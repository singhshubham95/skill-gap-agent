# S3 — Skill Map

How cleaned skills, jobs, projects and their links are stored. Reference
only — no logic lives here beyond queries.

**Status: Built** (M1; schema unchanged through M8).

## Schema (`graph.py`, store-agnostic, Neo4j-shaped)

Nodes: `Skill{name, category, source: current|target}`,
`JD{title, company}`, `Project{title, description, type}`.
Edges: `HAS_SKILL` (user → skill), `REQUIRES{weight}` (JD → skill),
`TRANSFERS_TO{confidence, rationale, gate_*}` (skill → skill),
`CLOSES_GAP` (project → skill). `TRANSFERS_TO` directional (see
`5-milestones.md` §Deferred #9).

## Queries

- `match_current()` ladder: exact → alias/canonical → substring (min 4
  chars). Bridges user/JD vocabularies at comparison time.
- `unmatched_target_skills()`, `requires_weights()`, JSON round-trip
  via `save()`/`load()` (`output/graph.json`).

## Consumers

Every stage reads/writes here; the object lives in the S7 runtime
registry (not in LangGraph state — checkpointer cannot serialize
networkx). Persistence stays `output/graph.json`.

## History (links, not copies)

- Milestones: `5-milestones.md` M1.
- Deferred: `5-milestones.md` §Deferred #1 (Neo4j), #9 (symmetry).
