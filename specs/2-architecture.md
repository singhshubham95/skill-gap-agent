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

## v2 Components (Designed — M7–M9, no code yet)

The sections below are the designed-but-unbuilt parts of the system. They
describe the target state; present-tense v1 components above are unchanged
until a milestone actually revises their behavior.

9. **LangGraph orchestration (M7)** — the v1 nodes (§1–§8) are currently
   invoked sequentially from `m5_plan.py`; M7 wires them into a real
   LangGraph graph (`cli.py`). Three concrete wins, in order of certainty:
   - **Human-in-the-loop as `interrupt()` + checkpointer.** The implied-skill
     proposal (§1) and confidence gate (§5) stdin loops become true
     interrupts — runs become resumable across process restarts and portable
     to a future web UI (restores deferred-enhancements #2).
   - **Conditional edges replace sequential assumptions.** No
     sub-threshold targets after the judge → skip the gate; judge
     calibration looks clustered-high → re-judge with a stricter rubric as a
     loop (turns the calibration concern in [7-open-items.md](7-open-items.md)
     into an automatic branch); no gaps above threshold → skip synthesis.
   - **State design.** A pydantic state object wraps the `SkillGraph` plus
     conversation/intake fields; the graph object stays the single source of
     truth and `output/graph.json` persistence is unchanged.
10. **Resume ingestion (M8)** — real users have a CV, not a skills JSON.
    Pipeline: PDF/DOCX → text (pypdf / python-docx) → **one LLM extraction
    call** → structured skills list in the same shape as the skills JSON →
    everything downstream (normalize, dedup, implied-skill proposal, judge)
    works unchanged. Design points:
    - **LLM extraction, not regex growth.** The skills JSON worked with
      regex/alias normalization because it was semi-curated; a real resume
      is prose. One extraction call reuses the `llm.py` JSON-extraction
      infra; the regex path stays as a no-LLM fallback.
    - **The skills JSON remains a first-class input** (power users,
      reproducible test runs); intake branches on what the user provides.
    - Promotes deferred-enhancements #7 from "best-effort" to designed.
11. **Conversational intake (M9)** — a tool-calling chat agent that fills a
    `UserProfile` state slot: collects the resume (PDF/DOCX) or skills JSON,
    collects JD texts, asks clarifying questions. Key synergy: the gate's
    depth/intent questions (§5) can be asked conversationally during intake,
    collapsing two interaction points into one conversation segment.
12. **Skill validation (M9)** — evidence-backed proficiency instead of
    trusting resume claims. Resumes inflate; self-ratings inflate more; the
    agent *elicits* depth through calibration questions. **Framing:
    calibration, not a test** — the tool exists to build the user's own
    learning plan, so no anti-cheat is needed, only honest framing.
    - **Triage (mandatory).** Quizzing every skill is an interrogation.
      Only ranking-relevant skills are validated: high JD `weight`, skills
      that are top-transfer *sources* (their depth drives the confidence
      multiplication), gate-flagged skills. Cap ~10–15 questions total;
      explicitly skippable ("just use my resume as-is" → resume-claim
      fallback).
    - **Tiered protocol per triaged skill** (adaptive stop, LangGraph
      subgraph: `generate_question → interrupt → grade → route`):
      1. **Concept checklist** — yes/no on ~4–6 sub-concepts. Cheapest to
         generate reliably and fastest to answer; per-concept granularity
         makes the *pattern* of yesses informative even if individual
         answers inflate.
      2. **One applied question** on a concept the user claimed — "walk me
         through how you'd deduplicate near-identical customer records in
         SQL" — graded by one LLM call against a hidden rubric. Applied
         over trivia: tests capability, and the user's own answer is stored
         as evidence.
      3. **Optional follow-up probe** — only if tier 2 is strong.
      Route: strong → stop or escalate once; vague → downshift and stop.
      Max 2–3 turns per skill.
    - **Question authoring & leakage control.** Questions + hidden rubric
      are co-generated in one LLM call (rubric never shown). A mechanical
      string-overlap check between question text and rubric technique names
      catches answer leakage (same spirit as the judge's keyword pruner).
      Authoring is offline and cached, so the full question set is
      reviewable before any user sees it; obscure skills degrade gracefully
      to the self-report tier.
    - **Persistence & consumers.** Grades map to the gate's 1–5 depth scale
      and persist to `output/proficiency.json` (same override pattern as
      `gate_overrides.json`); question cache keyed by skill. Consumers:
      (a) the gate's depth question is pre-filled for validated skills —
      the gate shrinks to unvalidated skills only (an explicit, intended
      outcome, not gate redundancy); (b) the judge prompt gains proficiency
      context ("user has SQL at working depth, not expert") for better
      transfer scores.
    - **Semantics of a "no".** A failed concept lowers the *skill's* depth
      factor (nudge, never hard-reject — a soft signal modulates
      confidence, it does not remove a skill from the profile). Concept-level
      micro-gaps ("learn window functions" as a plan item) are a recorded
      future idea, not v2 scope.

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