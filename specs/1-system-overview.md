# System Overview

The top-down view of the Skill-Gap Agent: what the system is, its layers and
components, where each lives in code, and how data flows through. Deep detail
lives in [2-architecture.md](2-architecture.md); this page is the map.

**Status: v1 complete.** All pipeline stages are built and validated against
a sealed hand-performed gap analysis of the same data ([4-validation.md](4-validation.md));
results in the README case study. Known limitations and the v1.1 candidate
list are in [7-open-items.md](7-open-items.md) and [6-deferred-enhancements.md](6-deferred-enhancements.md).

## What the system does (one paragraph)

Given a user's skills dump and target job descriptions, the agent builds a
weighted skill graph (networkx), detects skills the CV *implies* but doesn't
state (user-approved), scores how much existing skills transfer to missing
ones (LLM judge), gates uncertain judgments through a human-in-the-loop
prompt, ranks gaps by JD frequency, and outputs a ranked plan of grounded
learning projects. Validated against a sealed hand-performed gap analysis of
the same data ([4-validation.md](4-validation.md)).

## Layered Component Map

```mermaid
flowchart TB
    subgraph L1["Interface layer"]
        CLI["CLI runners<br/>(m5_plan, m4_gate, m3_judge, m2_check)"]
    end
    subgraph L2["Pipeline nodes (LangGraph, M4+)"]
        ING["Ingestion<br/>(skills JSON → graph)"]
        TING["Target-Ingestion<br/>(JDs → REQUIRES edges)"]
        NORM["Normalize/Dedup"]
        JUD["Transferability Judge<br/>(LLM)"]
        GATE["Confidence Gate<br/>(stdin)"]
        RANK["Gap Ranking<br/>(+ alternative groups)"]
        SYNTH["Project Synthesis"]
        OUT["Output"]
    end
    subgraph L3["Core domain"]
        GRAPH["SkillGraph<br/>(networkx schema + queries)"]
        IMP["Implied-skill detection"]
        TAX["Skill taxonomy (ESCO)"]
    end
    subgraph L4["Services"]
        LLM["LLM interface<br/>(DeepSeek V4 Flash via OpenRouter)"]
    end
    CLI --> ING & TING & JUD
    ING --> NORM --> JUD
    TING --> JUD
    JUD --> GATE --> RANK --> SYNTH --> OUT
    ING --- IMP
    NORM --- TAX
    JUD --- LLM
    SYNTH --- LLM
    ING & TING & JUD & GATE & RANK & SYNTH & OUT --- GRAPH
```

## Component Table

| Component | Purpose | Code | Spec | Status |
|---|---|---|---|---|
| Graph schema | `SkillGraph`: nodes/edges, queries, JSON round-trip | `src/skill_gap_agent/graph.py` | [2-architecture.md §Graph Schema](2-architecture.md) | ✅ Built |
| Normalization | Canonical terms + alias resolution | `src/skill_gap_agent/normalize.py` | [2-architecture.md §3](2-architecture.md) | ✅ Built |
| Ingestion node | Skills JSON → `Skill` nodes + `HAS_SKILL` | `ingest.py::ingest_skills_json` | [2-architecture.md §1](2-architecture.md) | ✅ Built |
| Implied-skill flow | Detect CV-implied skills, propose with evidence, persist approvals | `implied.py` | [2-architecture.md §1](2-architecture.md) | ✅ Built |
| Target-ingestion node | JD texts → target skills + weighted `REQUIRES` | `ingest.py::ingest_jds` | [2-architecture.md §2](2-architecture.md) | ✅ Built |
| Skill taxonomy | ESCO loader, graceful fallback to built-in tables | `taxonomy.py` | [2-architecture.md §3](2-architecture.md) | ✅ Built (data file pending) |
| LLM interface | Provider-agnostic `judge()`/`chat()`, JSON-out with retries | `llm.py` | [3-decisions.md](3-decisions.md) | ✅ Built |
| Transferability judge | Score `TRANSFERS_TO {confidence, rationale}` per unmatched target skill | `judge.py` | [2-architecture.md §4](2-architecture.md) | ✅ Built |
| Confidence gate | Self-assessment review (depth + intent) of uncertain verdicts | `gate.py` | [2-architecture.md §5](2-architecture.md) | ✅ Built + validated |
| Alternative groups | Any-of capability categories (cloud platforms, DL frameworks, ...) demote satisfied brands | `requirements.py` | [2-architecture.md §6](2-architecture.md) | ✅ Built |
| Gap ranking | Rank gaps by JD weight, transferability-aware | `ranking.py` | [2-architecture.md §6](2-architecture.md) | ✅ Built |
| Project synthesis | Grounded standalone project ideas per gap | `synthesis.py` | [2-architecture.md §7](2-architecture.md) | ✅ Built |
| Output node | Ranked markdown plan + graph persistence | `output.py` | [2-architecture.md §8](2-architecture.md) | ✅ Built |
| LangGraph wiring | Orchestrate nodes with the conditional gate as a real branch | — | [3-decisions.md](3-decisions.md) | ⏳ Milestone 4–5 |

## Data Flow at a Glance

```
IN:  data/skillsdataset.json (146 phrases)   data/jds/*.txt (13 JDs)
      │                                        │
      ▼                                        ▼
   canonical skills (119)                target skills (23)
   + implied skills (23, user-approved)  + REQUIRES weights
      │                                        │
      └──────────────┬─────────────────────────┘
                     ▼
            SkillGraph (networkx)
                     │
        unmatched targets (21) → LLM judge → TRANSFERS_TO edges (122)
                     │
                     ▼
        confidence gate (M4) → gap ranking (M5) → plan.md (M5)

PERSISTED: output/graph.json (whole graph), output/judge_report.json,
           output/implied_skills.json (approval record)
```

## Repo Map

```
skill-gap-agent/
├── README.md                  ← project entry point (user quickstart + case study)
├── specs/                     ← you are here (numbered by reading order)
├── data/                      ← seed data (gitignored)
│   ├── skillsdataset.json
│   └── jds/                   ← 13 JD texts
├── src/skill_gap_agent/
│   ├── graph.py               ← CORE: schema + queries (the system's backbone)
│   ├── normalize.py           ← CORE: canonical terms + aliases
│   ├── ingest.py              ← CORE: ingestion + target-ingestion nodes
│   ├── implied.py             ← CORE: implied-skill detection + proposal flow
│   ├── taxonomy.py            ← CORE: ESCO loader with fallback
│   ├── llm.py                 ← CORE: provider-agnostic LLM interface (DeepSeek via OpenRouter)
│   ├── judge.py               ← CORE: transferability judge node
│   ├── gate.py                ← CORE: confidence gate (self-assessment: depth + intent)
│   ├── ranking.py             ← CORE: transferability-aware gap ranking
│   ├── requirements.py        ← CORE: alternative-skill groups (any-of semantics)
│   ├── synthesis.py           ← CORE: grounded project synthesis
│   ├── output.py              ← CORE: plan.md renderer (with JD traceability)
│   ├── cli.py                 ← entry point (pipeline wiring into LangGraph pending)
│   ├── m5_plan.py             ← full-pipeline runner (current primary entry)
│   ├── m4_gate.py             ← milestone-4 runner (scaffolding)
│   ├── m3_judge.py            ← milestone-3 runner (scaffolding)
│   ├── m2_check.py            ← milestone-2 verification script (scaffolding)
│   └── smoke_test.py          ← milestone-1 schema test (scaffolding)
├── output/                    ← pipeline artifacts (gitignored): plan.md, graph.json,
│                                 judge_report.json, gate_overrides.json, implied_skills.json
└── .env                       ← API keys (gitignored; see .env.example)
```

**Scaffolding note:** the `m*_*.py` runners are milestone scripts; `m5_plan.py`
is the current full-pipeline entry. The LangGraph wiring (`cli.py`) that turns
the sequential node calls into a real conditional graph is the main remaining
architecture item — see [7-open-items.md](7-open-items.md).

## Where to Go Next

- **Deep design detail:** [2-architecture.md](2-architecture.md)
- **Why these choices:** [3-decisions.md](3-decisions.md)
- **Build order + progress:** [5-milestones.md](5-milestones.md)
- **What "done" means:** [4-validation.md](4-validation.md)
- **Trade-offs made:** [6-deferred-enhancements.md](6-deferred-enhancements.md)
- **Open questions:** [7-open-items.md](7-open-items.md)