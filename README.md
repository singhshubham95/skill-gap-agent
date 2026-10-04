# Skill-Gap Agent

Transferability-aware skill-gap analysis: given your skills dump and a set of
target job descriptions, the agent builds a weighted skill graph, scores how
much your existing skills transfer to missing ones (LLM judge), checks the
uncertain verdicts with you (human-in-the-loop), and outputs a ranked plan of
learning projects grounded in what you already know — not generic advice.

Validated against a sealed hand-performed gap analysis of the same data — the
pipeline's first run was scored against it as acceptance criteria (rubric and
results: [specs/08-gap-measurer.md](specs/08-gap-measurer.md) §Validation
rubric). Ongoing quality monitoring runs the pipeline over seeded JD subsets
and records which subset produced which plan — the sweep harness
(`sweep.py`, design in
[specs/11-sweep.md](specs/11-sweep.md)).

## Quickstart (for users)

Requirements: Python 3.11+, an [OpenRouter](https://openrouter.ai/keys) API
key (default model: DeepSeek V4 Flash — a full run costs well under a cent).

```powershell
# 1. Install
python -m venv .venv
.\.venv\Scripts\pip install -e ".[dev]"

# 2. Add your key (stored in the OS keyring — Windows Credential Manager /
#    macOS Keychain — never in a file inside the repo)
.\.venv\Scripts\python -c "from skill_gap_agent.secrets import set_secret; set_secret('OPENROUTER_API_KEY', 'sk-or-YOUR-KEY')"

# 3. Add your data (see data/README.md for expected formats)
#    - data/skillsdataset.json (your skills dump)
#    - data/jds/*.txt         (job descriptions, one file each)

# 4. Run the full pipeline
.\.venv\Scripts\python -m skill_gap_agent.m5_plan --auto
```

During the run you'll be asked to approve **implied skills** the CV only hints
at, and to self-assess **depth + intent** for ambiguous gap verdicts. Decisions
persist in `output/`, so re-runs only ask about what changed.

**Outputs** (in `output/`): `plan.md` (the ranked plan — start here),
`plan.html` (clickable issue links, served by the local UI / extension),
`graph.json` (the full skill graph), `judge_report.json` +
`gate_overrides.json` (audit trail of every judgment and your decisions),
`oss_issues.json` (per-gap issue cache — re-runs make zero API calls),
`extracted_skills.json` + `extracted_approvals.json` (resume extraction,
when a resume is the input), `vocab_bridge.json` (vocabulary merge
decisions), `gaps.json` + `captured_jds/` (extension run artifacts), and
`sweeps/<sweep-id>/` (evaluation harness output).

## What v1 does — and deliberately doesn't

| Does | Doesn't (yet) |
|---|---|
| Skills JSON ingestion with implied-skill detection (you approve) | Conversational intake + evidence-backed skill validation (M9 — next) |
| Resume PDF/DOCX/TXT ingestion (M8) | Automatic JD discovery/scraping (capture is bookmarklet/extension) |
| JD parsing via a curated, auditable keyword lexicon | Chat follow-up Q&A over the graph |
| LLM transferability judge (calibrated 0–1 + rationale) | Per-JD mention-modality classification ("such as" vs "must have") — hand-set policies for now |
| Alternative-group semantics ("cloud: AWS/Azure/GCP" = any one) | Neo4j persistence (v1 is networkx + JSON) |
| Human gate on ambiguous verdicts (depth + intent, persisted) | Issue-quality ranking / curated-only results (search-and-reason loop is next) |
| Ranked plan with JD traceability + grounded projects | In-page gap marking on the JD text (extension renders a gap table) |
| OSS good-first-issue sourcing per top gap (M10 thin slice, unauthenticated) + `plan.html` | Chrome Web Store packaging / multi-user hosting |

Full trade-off list with restore triggers: [specs/03-milestones.md](specs/03-milestones.md) §Deferred.

**Roadmap (M7–M8 + M10–M13 built; M9 designed):** LangGraph orchestration with
resumable human-in-the-loop steps, resume PDF/DOCX ingestion, GFI issue
sourcing, minimal local UI (`python -m skill_gap_agent.server`), the
JD-subset sweep evaluation harness (`python -m skill_gap_agent.sweep`), and
the Chrome extension shell ([extension/](extension/) — capture JDs in the
browser, analyze gaps, generate the plan in a side panel) are built; next is
conversational intake + evidence-backed skill validation (M9). Design detail in
[specs/13-intake.md](specs/13-intake.md),
[specs/11-sweep.md](specs/11-sweep.md) and
[specs/12-extension.md](specs/12-extension.md); build order in
[specs/03-milestones.md](specs/03-milestones.md).

**Chrome extension:** start `python -m skill_gap_agent.server`, load
[extension/](extension/) unpacked in `chrome://extensions`, and follow
[extension/README.md](extension/README.md). Capture is LinkedIn-only for now.

## For contributors

The specs are the onboarding path — they document not just the design but the
*reasoning* behind every decision, including revisions made during building:

1. [specs/01-system-overview.md](specs/01-system-overview.md) — stage map, stage↔code table, data flow, repo map, component router (start here)
2. [specs/02-decisions.md](specs/02-decisions.md) — locked decisions, append-only, with rationale (including decisions that were *revised* and why)
3. [specs/03-milestones.md](specs/03-milestones.md) — roadmap: build order + learnings + deferred trade-offs + open questions
4. S1–S7 stage files ([specs/04-reader.md](specs/04-reader.md) … [specs/10-flow-runner.md](specs/10-flow-runner.md)) — per-stage mechanics + status
5. Non-stage component files ([specs/11-sweep.md](specs/11-sweep.md), [specs/12-extension.md](specs/12-extension.md), [specs/13-intake.md](specs/13-intake.md)) — sweep harness, extension shell, intake + validation

Conventions: specs are numbered by reading order and are **living
target-state documents** — they describe the full system being built, with
every component marked Built or Designed (never version-split into
`specs/v2/`; milestone numbers stay linear). `02-decisions.md` is append-only
(mark superseded, never rewrite); the graph schema in
[01-system-overview.md](specs/01-system-overview.md) is deliberately Neo4j-shaped so
the store can migrate without redesign. The full spec-evolution rules and
code conventions live in
[.github/copilot-instructions.md](.github/copilot-instructions.md) — read it
before changing code or specs.

## Specs

All specifications live in [`specs/`](specs/). Start with the system overview,
then dive as needed:

| File | Contents |
|---|---|
| [specs/01-system-overview.md](specs/01-system-overview.md) | **Start here** — stage map, stage↔code table, data flow, repo map, component router |
| [specs/02-decisions.md](specs/02-decisions.md) | Locked technology and scope decisions, with rationale |
| [specs/03-milestones.md](specs/03-milestones.md) | Roadmap: build order + learnings + deferred trade-offs + open questions |
| [specs/04-reader.md](specs/04-reader.md) … [specs/10-flow-runner.md](specs/10-flow-runner.md) | Per-stage mechanics (S1–S7); skill-graph schema in [06-skill-map.md](specs/06-skill-map.md) |
| [specs/11-sweep.md](specs/11-sweep.md) | JD-subset sweep evaluation harness (M12) |
| [specs/12-extension.md](specs/12-extension.md) | Chrome extension shell (M13) |
| [specs/13-intake.md](specs/13-intake.md) | Conversational intake + skill validation (M9, Designed) |