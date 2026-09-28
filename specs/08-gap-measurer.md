# S5 — Gap Measurer

What is missing and how big. Consumes the S3 map, writes verdicts back
onto it.

**Status: Built** (M3 judge, M4 gate, M5 ranking + M6 fixes).

## Judge (`judge.py`)

Per unmatched target: keyword-overlap top-5 + `PRUNER_HINTS`
(framework/platform analogs) → one S2 call → `TRANSFERS_TO` edges
(scores <0.3 dropped). Report: `output/judge_report.json`.
Calibration: full-run confidences cluster high (min 0.65, mean 0.84) —
gate compensates; auto re-judge loop explicitly deferred (see
`3-decisions.md` M7 row; trigger in `5-milestones.md` §Open: calibration).

## Gate (`gate.py`)

Scope: top edge per sub-threshold target (<0.75). Asks self-assessment
only (user cannot judge unknown targets): depth 1–5 → multiplier
(0.3/0.6/0.85/1.0/1.0) + intent (count vs declared-gap). Persists
`output/gate_overrides.json`, writes `gate_*` edge props, silent re-runs.
Validated interactively on 4 targets (M4).

## Ranking (`ranking.py`, `requirements.py`)

`gap_score = weight × (1 − top confidence)`. Verdicts: `held` (ladder
match, score 0), `bridge` (≥0.7), `partial` (≥0.4), `gap`, `declared-gap`,
`alt-bridged` (any-of group + user holds another member; groups never
erase specific gaps — LangChain stays full-urgency). Policies hand-set;
per-JD modality parsing deferred.

## Validation rubric — what "done" means (folded from `4-validation.md`, 2026-09-27)

This file answers your "what is validation for" question: it is **not a
component and not cross-cutting functionality**. It is the Definition of
Done for the v1 pipeline — acceptance criteria sealed *before* any pipeline
code existed, scored once at M6, now history. It lives here (not in its own
file) because S5 owns ranking correctness: the rubric judges whether the
ranked gaps are right.

- **Origin:** the author performed the same gap analysis **by hand** —
  reading the same skills dump against the same 13 JDs — and sealed the
  conclusions. The pipeline's first full run was then scored against them.
  (The hand analysis itself is not in the repo.)
- **Pass criteria (all met at M6, see roadmap M6):**
  1. ≥70% overlap between the pipeline's top-5 ranked gaps and the hand
     analysis's list (headline buckets: GenAI/LLM depth, agent-framework
     breadth, cloud platform breadth).
  2. The judge **independently arrives at** "Google ADK → LangGraph is a
     partial, not full, gap" (reproduced: `LangGraph ← Google ADK @ 0.90`).
  3. The **ambiguous platform case** (AWS 9/13 JDs vs production GCP depth)
     is surfaced by the gate, not silently scored (AWS gate-kept as bridge,
     ranked below true gaps).
- **Process (for any future re-validation):** run the full pipeline on the
  seed data with no hints → compare ranked gaps to the sealed buckets above
  → write up as the README case study.
- **Threshold note:** the gate threshold (~0.5 initial guess) was tuned to
  **0.75** against this rubric after the first full run (M3 edge
  distribution clustered high) — see roadmap M4.

## History (links, not copies)

- Decisions: `3-decisions.md` (M4 redesign, M7 recalibration-defer).
- Milestones: `5-milestones.md` M3, M4, M5, M6 (rubric scored here).
