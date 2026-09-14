# Skill-Gap Agent

Transferability-aware skill-gap analysis: given your skills dump and a set of
target job descriptions, the agent builds a weighted skill graph, scores how
much your existing skills transfer to missing ones (LLM judge), checks the
uncertain verdicts with you (human-in-the-loop), and outputs a ranked plan of
learning projects grounded in what you already know — not generic advice.

Validated against a sealed hand-performed gap analysis of the same data (see
[Case Study](#case-study-validating-the-pipeline)) — the pipeline's first run
was scored against it as acceptance criteria.

## Quickstart (for users)

Requirements: Python 3.11+, an [OpenRouter](https://openrouter.ai/keys) API
key (default model: DeepSeek V4 Flash — a full run costs well under a cent).

```powershell
# 1. Install
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"

# 2. Add your key
copy .env.example .env   # then edit .env: OPENROUTER_API_KEY=...

# 3. Add your data (see data/README.md for expected formats)
#    - data/skills.json       (your skills dump)
#    - data/jds/*.txt         (job descriptions, one file each)

# 4. Run the full pipeline
.\.venv\Scripts\python -m skill_gap_agent.m5_plan --auto
```

During the run you'll be asked to approve **implied skills** the CV only hints
at, and to self-assess **depth + intent** for ambiguous gap verdicts. Decisions
persist in `output/`, so re-runs only ask about what changed.

**Outputs** (in `output/`): `plan.md` (the ranked plan — start here),
`graph.json` (the full skill graph), `judge_report.json` +
`gate_overrides.json` (audit trail of every judgment and your decisions).

## What v1 does — and deliberately doesn't

| Does | Doesn't (yet) |
|---|---|
| Skills JSON ingestion with implied-skill detection (you approve) | Resume PDF parsing (skills JSON is the reliable path) |
| JD parsing via a curated, auditable keyword lexicon | Automatic JD discovery/scraping |
| LLM transferability judge (calibrated 0–1 + rationale) | Chat follow-up Q&A over the graph |
| Alternative-group semantics ("cloud: AWS/Azure/GCP" = any one) | Per-JD mention-modality classification ("such as" vs "must have") — hand-set policies for now |
| Human gate on ambiguous verdicts (depth + intent, persisted) | Neo4j persistence (v1 is networkx + JSON) |
| Ranked plan with JD traceability + grounded projects | GitHub good-first-issue sourcing |

Full trade-off list with restore triggers: [specs/6-deferred-enhancements.md](specs/6-deferred-enhancements.md).

**Roadmap (designed, not yet built):** the next milestones (M7–M9) add true
LangGraph orchestration with resumable human-in-the-loop steps, resume
PDF/DOCX ingestion, a conversational intake agent, and evidence-backed skill
validation (calibration questions instead of trusting resume claims). Design
detail in [specs/2-architecture.md](specs/2-architecture.md) §9–§12 and
[specs/5-milestones.md](specs/5-milestones.md).

## For contributors

The specs are the onboarding path — they document not just the design but the
*reasoning* behind every decision, including revisions made during building:

1. [specs/1-system-overview.md](specs/1-system-overview.md) — layered component map, component↔code table, data flow, repo map (which files are core vs. milestone scaffolding)
2. [specs/2-architecture.md](specs/2-architecture.md) — each pipeline component's mechanics, graph schema, and the non-obvious design rules (alternative groups, gate semantics)
3. [specs/3-decisions.md](specs/3-decisions.md) — locked decisions, append-only, with rationale (including decisions that were *revised* and why)
4. [specs/5-milestones.md](specs/5-milestones.md) — build order with what was learned at each step
5. [specs/6-deferred-enhancements.md](specs/6-deferred-enhancements.md) — what was traded off and what would trigger restoring it
6. [specs/7-open-items.md](specs/7-open-items.md) — known limitations and candidate next steps

Conventions: specs are numbered by reading order and are **living
target-state documents** — they describe the full system being built, with
every component marked Built or Designed (never version-split into
`specs/v2/`; milestone numbers stay linear). `3-decisions.md` is append-only
(mark superseded, never rewrite); the graph schema in
[2-architecture.md](specs/2-architecture.md) is deliberately Neo4j-shaped so
the store can migrate without redesign. The full spec-evolution rules and
code conventions live in
[.github/copilot-instructions.md](.github/copilot-instructions.md) — read it
before changing code or specs.

## Specs

All specifications live in [`specs/`](specs/). Start with the system overview,
then dive as needed:

| File | Contents |
|---|---|
| [specs/1-system-overview.md](specs/1-system-overview.md) | **Start here** — layered component map, component↔code table, data flow, repo map |
| [specs/2-architecture.md](specs/2-architecture.md) | Deep design: pipeline components, graph schema |
| [specs/3-decisions.md](specs/3-decisions.md) | Locked technology and scope decisions, with rationale |
| [specs/4-validation.md](specs/4-validation.md) | The rubric — what "done" means, measured against a sealed hand analysis of the same data |
| [specs/5-milestones.md](specs/5-milestones.md) | Build order, milestone by milestone, with progress |
| [specs/6-deferred-enhancements.md](specs/6-deferred-enhancements.md) | Every trade-off made for v1, and the trigger to restore each |
| [specs/7-open-items.md](specs/7-open-items.md) | Unresolved items that don't block starting |

## Case Study: Validating the Pipeline

To prove the pipeline's judgments are sound (not just plausible-sounding LLM
output), its first full run was scored against a ground truth: the author
performed the same gap analysis **by hand** — reading the same 13 JDs against
the same skills dump — before writing any pipeline code. The hand analysis
was sealed as the acceptance rubric ([specs/4-validation.md](specs/4-validation.md)),
and the pipeline then ran fresh with no hints. The hand analysis itself is not
in the repo; the rubric below records its conclusions and how the pipeline
measured against them.

### Rubric results

| Criterion | Result |
|---|---|
| ≥70% overlap between pipeline top-5 gaps and the hand analysis | ✅ The hand analysis's headline buckets (GenAI/LLM depth, framework breadth, cloud platforms) all appear in the pipeline's ranked output |
| Judge independently arrives at "Google ADK → LangGraph is a partial, not full, gap" | ✅ `LangGraph ← Google ADK @ 0.90` with rationale "both are agent development frameworks with similar orchestration and state concepts" — matching the hand conclusion, derived independently |
| Ambiguous case surfaced, not silently scored | ✅ AWS (9/13 JDs) was judged 0.70-transferable from GCP depth, surfaced by the gate, and the user's depth answer kept it a "bridge" — it ranks **below** lower-demand true gaps in the final plan |

### Before / after

**Before (hand analysis):** one JD at a time, eyeballed overlaps, binary "have/don't
have" skill matching, no reusable artifact.

**After (this pipeline):** 146 CV phrases + 13 JDs → 119 canonical + 23
user-approved implied skills → 21 LLM-judged transfer verdicts (122 edges) →
human-in-the-loop gate on the 4 ambiguous ones → transferability-aware ranking
→ 4 grounded project recommendations. Re-runnable in minutes as new JDs or
completed projects change the graph.

### Sample output (`output/plan.md`)

```
  score  JDs  verdict        target <- top transfer
   2.70    9  alt-bridged   AWS            <- Google Cloud Platform (0.70)
   2.05    5  partial       Fine-tuning    <- Hyperparameter search parallelization (0.59)
   0.00   10  held          Azure          <- Azure Data Factory (1.00)
   ...
```

Azure (10 JDs) is **held**, not the #1 gap: the matching ladder resolves it to
the user's Azure Data Factory experience. AWS (9 JDs) is **alt-bridged**: the
JDs list cloud platforms as interchangeable ("Azure OpenAI, AWS Bedrock, GCP
Vertex AI"), and the user's GCP depth satisfies that capability intent — while
**LangChain stays a full-urgency gap** despite Google ADK experience, because
employers differentiate on agent frameworks (per-group mention policies).
Every verdict lists the exact JDs that demand it.

Sample synthesized project: **"Fine-Tune a DistilBERT Multi-Label Classifier
with Parallel Hyperparameter Search"** — reuses the user's multi-label
classification and hyperparameter-parallelization background to close the
fine-tuning gap.