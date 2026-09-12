# Validation Rubric (Definition of Done)

The pipeline's output is compared against the manual 13-JD gap analysis
performed in an earlier session. That manual run is the project's own test set.

## Pass Criteria

- **≥70% overlap** between the pipeline's top-5 ranked gaps and the manual
  list.
- The transferability judge **independently arrives at** "Google ADK →
  LangGraph is a partial, not full, gap."
- The **Databricks-style ambiguous case** is surfaced by the confidence gate
  (real skill gap vs. platform switch) rather than silently scored.

## Process

1. Run the full pipeline on the seed data (skills JSON + 13 JDs) with no
   manual hints.
2. Compare the ranked gap output to the manual analysis.
3. Write up the comparison — this becomes the README case study and the
   portfolio's before/after story.

The confidence threshold (~0.5) is tuned empirically against this rubric after
the first full run (deferred-enhancements #10).