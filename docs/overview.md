# Skill-Gap Agent — overview (human tier)

> **Non-authoritative.** `specs/` is the source of truth for everything the
> system is and does. This page summarizes intent for human eyes; if it ever
> disagrees with `specs/`, `specs/` wins and this page gets fixed.

## Intent

Given a person's skills evidence and target job descriptions, build a
weighted skill graph, detect skills the CV implies but doesn't state
(user-approved), score how much existing skills transfer to missing ones,
gate uncertain judgments through the human, rank gaps by JD frequency, and
output a ranked plan of grounded learning projects — surfaced through a
Chrome extension panel alongside the job description being viewed.

## Where to look

- [specs/01-system-overview.md](../specs/01-system-overview.md) — component
  map, data flow, current state (start here)
- [specs/02-decisions.md](../specs/02-decisions.md) — what was decided and why
- [specs/03-milestones.md](../specs/03-milestones.md) — build order,
  verification records, learnings
- [specs/tasks/](../specs/tasks/) — one work order per unit of work

## Status

v1 pipeline built and validated (M1–M16, incl. M9 conversational intake +
skill validation); M17 (observability + judge evaluation) designed — see
[specs/03-milestones.md](../specs/03-milestones.md) for the authoritative
status of each milestone.
