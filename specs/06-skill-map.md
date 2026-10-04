# S3 — Skill Map

How cleaned skills, jobs, projects and their links are stored. Reference
only — no logic lives here beyond queries.

**Status: Built** (M1; schema unchanged through M8).

## Schema (`graph.py`, store-agnostic, Neo4j-shaped)

The canonical schema reference — same shape later in Neo4j (folded from
`2-architecture.md`; kept here because this file owns `graph.py`).

**Nodes**

| Label | Key properties |
|---|---|
| `Skill` | `name`, `category`, `source` (`current`\|`target`) |
| `JD` | `title`, `company` |
| `Project` | `title`, `description`, `type` (`standalone` + `oss_issue` since M10) + `url, repo, labels, updated_at` for oss issues |

**Edges**

| Type | From → To | Properties | Written by |
|---|---|---|---|
| `HAS_SKILL` | User (implicit) → `Skill` | — | Ingestion node |
| `REQUIRES` | `JD` → `Skill` | `weight` (frequency across JDs) | Target-ingestion node |
| `TRANSFERS_TO` | `Skill` → `Skill` | `confidence` (0–1), `rationale` (short LLM text), `gate_*` (M4) | Transferability-judge node / gate |
| `CLOSES_GAP` | `Project` → `Skill` | — | Output node |

`TRANSFERS_TO` is directional in v1 (see `03-milestones.md` §Deferred #9).

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

- Milestones: `03-milestones.md` M1.
- Deferred: `03-milestones.md` §Deferred #1 (Neo4j), #9 (symmetry).
