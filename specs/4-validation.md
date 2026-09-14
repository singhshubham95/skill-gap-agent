# Validation Rubric (Definition of Done)

Before any pipeline code existed, the author performed the same gap analysis
**by hand** — reading the same skills dump against the same 13 JDs — and
sealed the conclusions as this rubric. The pipeline's first full run was then
scored against it. (The hand analysis itself is not in the repo; this file
records its conclusions as acceptance criteria.)

## Pass Criteria

- **≥70% overlap** between the pipeline's top-5 ranked gaps and the hand
  analysis's list.
- The transferability judge **independently arrives at** "Google ADK →
  LangGraph is a partial, not full, gap."
- The **ambiguous platform case** (e.g. AWS demanded by 9/13 JDs while the
  user has production GCP depth) is surfaced by the confidence gate (real
  skill gap vs. platform switch) rather than silently scored.

## Process

1. Run the full pipeline on the seed data (skills JSON + 13 JDs) with no
   hints from the hand analysis.
2. Compare the ranked gap output to the sealed conclusions below.
3. Write up the comparison — this becomes the README case study.

**Sealed hand-analysis conclusions (the ground truth):**
- Headline gap buckets: GenAI/LLM depth, agent-framework breadth, cloud
  platform breadth.
- Google ADK → LangGraph is a partial, not full, gap (adjacent orchestration
  concepts).
- Broad cloud demand (AWS/Azure/GCP) is a platform-switch question, not a
  from-scratch learning need.

The confidence threshold (~0.5) is tuned empirically against this rubric after
the first full run (deferred-enhancements #10).

## Result (milestone 6)

All three pass criteria met on the fresh full run — details in the README
case study. Note: the threshold was set at 0.75 (not 0.5) based on the
milestone-3 edge distribution; see [5-milestones.md](5-milestones.md) M4.