# C3 — Conversational Intake + Skill Validation

How the agent gathers evidence and how it verifies claimed depth before
ranking. Two coupled concerns: a tool-calling chat agent that assembles the
input, and a validation protocol that replaces self-report with elicited,
evidence-backed proficiency.

**Status: ⏸ Deferred / re-scoped** (2026-10-04 user decision: **no
conversational flow** — the extension panel stays the only interaction
model; decision row in [02-decisions.md](02-decisions.md)). M9's build
waits for the plan/gap-quality brainstorm
([03-milestones.md](03-milestones.md) §Deferred #13); whatever returns must
be **non-conversational** (e.g. a panel checklist of extracted skills with
confidence badges). The validation *goal* below stands; the conversational
*UX* is kept as history, not target state. No code: `intake.py`,
`validate.py` do not exist. End-to-end design originally folded from
`2-architecture.md` §§11–12.

## Conversational intake

A tool-calling chat agent fills a `UserProfile` state slot: collects the
resume (PDF/DOCX) or skills JSON, collects JD texts, asks clarifying
questions. Key synergy: the gate's depth/intent questions can be asked
conversationally during intake, collapsing two interaction points into one
conversation segment.

The existing capture paths are reused as tools, not rewritten: the
bookmarklet / extension capture JDs
([12-extension.md](12-extension.md)), and `resume_to_skills_json()` does
resume extraction ([04-reader.md](04-reader.md) S1).

## Skill validation

Evidence-backed proficiency instead of trusting resume claims. Resumes
inflate; self-ratings inflate more; the agent *elicits* depth through
calibration questions. **Framing: calibration, not a test** — the tool
exists to build the user's own learning plan, so no anti-cheat is needed,
only honest framing.

- **Triage (mandatory).** Quizzing every skill is an interrogation. Only
  ranking-relevant skills are validated: high JD `weight`, skills that are
  top-transfer *sources* (their depth drives the confidence
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

## How it changes the pipeline

The IN edge becomes conversational: resume PDF/DOCX or skills JSON → LLM
extraction → skill validation on triaged skills → proficiency evidence
feeds the gate (which shrinks to unvalidated skills) — and the whole flow
runs as a LangGraph graph with `interrupt()` at the human-in-the-loop
points. The stage table in
[01-system-overview.md](01-system-overview.md) is the router; nothing
downstream of ingestion changes shape.

## Done criteria (for the build)

To be sealed at M9 start; the shape follows the repo's verification
convention (offline check + lint/tests clean + one interactive validation
recorded in `03-milestones.md` before the status flips to Built).

## History (links, not copies)

- Decisions: [02-decisions.md](02-decisions.md) (post-M6 v2-direction row).
- Milestones: [03-milestones.md](03-milestones.md) M9 (Designed).
- Related: [05-ai-caller.md](05-ai-caller.md) S2 (LLM door), S5
  [08-gap-measurer.md](08-gap-measurer.md) (gate depth scale this feeds).