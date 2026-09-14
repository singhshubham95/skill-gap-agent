# v1 Architecture

Deep design detail. For the top-down map (layers, component↔code table, data
flow, repo layout), start at [1-system-overview.md](1-system-overview.md).

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
   deferred-enhancements #7). **Implied-skill detection:** a CV rarely states
   every skill explicitly (e.g. "Custom Airflow operator authoring (Python)"
   implies Python without listing it). After explicit skills, the node scans
   raw phrases for implied skills and **proposes each to the user with its
   evidence** ("'…(Python)' implies Python — add? [y/n/a]"); approvals persist
   to `output/implied_skills.json` so re-runs don't re-ask. Accepted implied
   skills enter the graph as `HAS_SKILL` with `category: implied`.
2. **Target-ingestion node** — parse JD texts → `Skill` records
   (`source: target`) + `REQUIRES` edges with `weight` = number of JDs
   mentioning the skill. **Normalization scope note:** JD-side skills are born
   canonical because extraction uses a curated keyword lexicon
   (`JD_SKILL_LEXICON` in `ingest.py`) whose keys are already aligned to the
   user-side canonical vocabulary — so `normalize.py` currently runs on the
   user side only. **If JD extraction ever switches to LLM-based** (to catch
   skills the lexicon misses), extracted surface forms will no longer be
   pre-aligned and normalization must run on the JD side too. The
   `match_current()` ladder in `graph.py` (exact → alias → substring) bridges
   the two vocabularies at comparison time.
3. **Normalize/dedup** — exact + alias match (case-insensitive, alias table);
   LLM-assisted merge only for ambiguous pairs. **Load-bearing:** judge quality
   depends entirely on this, so it is a first-class step, not an afterthought.
   Known input quirk (from milestone 1): the skills JSON contains long
   descriptive phrases, not clean names — canonical skill terms must be
   extracted here. **External taxonomy:** where available, an external skill
   taxonomy (ESCO ICT subset) supplies preferred labels + alt-labels, feeding
   the alias table and implied-skill patterns; the loader falls back gracefully
   to the built-in tables when the taxonomy file is absent
   (see [7-open-items.md](7-open-items.md)).
4. **Transferability judge** — for each unmatched target skill, score
   confidence (0–1) that an existing skill transfers, with a short rationale.
   **Implemented (milestone 3):** keyword-overlap pruning to top-k (k=5)
   candidates **plus lexicon-hint candidates** (`PRUNER_HINTS` in `judge.py` —
   framework-adjacent and platform-analog skills always included, since pure
   keyword overlap misses e.g. "LangGraph" vs "Agentic application development
   (Google ADK)"); one LLM call per target skill; scores <0.3 dropped; edges
   written as `TRANSFERS_TO {confidence, rationale}`; report persisted to
   `output/judge_report.json`. Default model: DeepSeek V4 Flash 0731 via
   OpenRouter (see [7-open-items.md](7-open-items.md)). Full run on seed data:
   21/21 targets, 122 edges, 0 errors. **Calibration note:** top confidences
   cluster high (mean 0.84) when many candidates are shown — the gate
   threshold likely needs raising; decide with milestone-4 data.
5. **Confidence gate** — reviews targets whose top-edge confidence is below
   the threshold (0.75, data-driven from milestone-3 edge distribution; scope:
   top edge per target skill — it determines the verdict, lower edges are
   supporting evidence). **Design principle (revised after M4 user feedback):**
   the user lacks the target skill by definition, so they cannot judge the
   LLM's semantic-transfer score — asking them to "correct the number" asks
   them to redo the LLM's job. Instead the gate asks **self-assessment
   questions only the user can answer**:
   - **Depth** of their real experience with the *source* (top-transfer)
     skill — the judge scored similarity but implicitly assumed a proficiency
     level the CV doesn't state ("GCP Composer administration" could be
     exposure or expert depth). Final confidence = judge score × depth factor.
   - **Intent** — does the user even want to count this skill area toward
     their profile (they may not want AWS roles despite JD demand)? "No"
     marks the target an explicit, user-declared gap regardless of score.
   Decisions persist to `output/gate_overrides.json` and are applied as
   edge-property overrides on re-runs. The platform-switch validation still
   holds and works better: "given your BigQuery depth" becomes a literal
   depth question rather than an appeal to intuition about an unknown skill.
6. **Gap ranking** — networkx traversal over target skills, ranked by
   `gap_score = weight × (1 − top transfer confidence)`. **Held-skill fix:**
   targets the matching ladder resolves to a current skill are marked `held`
   (score 0) — previously they read as confidence-0 gaps because the judge
   never scored them. **Alternative groups** (`requirements.py`, added after
   user review): JDs often list capability categories as interchangeable
   brands — "cloud AI platforms (Azure OpenAI, AWS Bedrock, GCP Vertex AI)"
   is an *any-of* requirement, not three strict ones. Groups NEVER erase a
   specific skill gap; they only demote a target to `alt-bridged` (low
   urgency) when it belongs to an **any-of** group AND the user holds another
   member. **Per-group mention policies** are hand-set and auditable:
   `any-of` for cloud_platform / managed_llm_platform / dl_framework / bi_tool
   (JDs list these as interchangeable); `specific` for agent_framework —
   "such as LangChain, LlamaIndex, ..." reads as exemplars, but employers
   differentiate on these brands, so LangChain stays a full-urgency gap
   despite ADK experience. This respects the user's challenge: group
   membership must never falsely mark LangChain as satisfied.
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