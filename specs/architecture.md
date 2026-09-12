# v1 Architecture

## Pipeline

```
skills JSON ──▶ Ingestion ──┐
                            ├──▶ Normalize/Dedup ──▶ Transferability Judge ──▶ Confidence Gate (stdin)
JD texts ────▶ Target-      │                                                        │ (high conf)
              Ingestion ────┘                                                        ▼
                                                                        Gap Ranking ──▶ LLM Project Synthesis ──▶ Output (ranked markdown plan)
```

## Components

1. **Ingestion node** — parse skills JSON → `Skill` records (`name`, `category`,
   `source: current`). Also accepts a plain resume text dump (best-effort —
   deferred-enhancements #7).
2. **Target-ingestion node** — parse JD texts → `Skill` records
   (`source: target`) + `REQUIRES` edges with `weight` = number of JDs
   mentioning the skill.
3. **Normalize/dedup** — exact + alias match (case-insensitive, alias table);
   LLM-assisted merge only for ambiguous pairs. **Load-bearing:** judge quality
   depends entirely on this, so it is a first-class step, not an afterthought.
   Known input quirk (from milestone 1): the skills JSON contains long
   descriptive phrases, not clean names — canonical skill terms must be
   extracted here.
4. **Transferability judge** — for each unmatched target skill, score
   confidence (0–1) that an existing skill transfers, with a short rationale.
   **Pairwise pruning required:** embedding or keyword pre-filter to top-k
   (k≈5) candidate current skills per target skill before LLM calls — naive
   pairwise over ~40×60 skills is ~2,400 calls. All LLM calls go through the
   provider-agnostic `judge()` interface (structured prompt → structured JSON
   out).
5. **Confidence gate** — threshold ~0.5 (tunable). Below threshold: print the
   ambiguous skill + rationale, ask the user via stdin, record the answer as an
   edge-property override.
6. **Gap ranking** — networkx traversal: for each `REQUIRES` edge with no
   strong `TRANSFERS_TO` path, rank by `weight` descending.
7. **LLM project synthesis** — per top gap, generate standalone project ideas
   grounded in the user's *existing* skills, not generic ideas.
8. **Output node** — ranked markdown plan written to `output/plan.md`; graph
   state persisted to `output/graph.json`.

## Graph Schema (store-agnostic — same shape later in Neo4j)

**Nodes**

| Label | Key properties |
|---|---|
| `Skill` | `name`, `category`, `source` (`current`\|`target`) |
| `JD` | `title`, `company` |
| `Project` | `title`, `description`, `type` (`standalone` in v1) |

**Edges**

| Type | From → To | Properties | Written by |
|---|---|---|---|
| `HAS_SKILL` | User (implicit) → `Skill` | — | Ingestion node |
| `REQUIRES` | `JD` → `Skill` | `weight` (frequency across JDs) | Target-ingestion node |
| `TRANSFERS_TO` | `Skill` → `Skill` | `confidence` (0–1), `rationale` (short LLM text) | Transferability-judge node |
| `CLOSES_GAP` | `Project` → `Skill` | — | Output node |

`TRANSFERS_TO` is directional in v1 (see deferred-enhancements #9).