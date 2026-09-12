# Skill-Gap Agent — Specification Index

Minimal v1 build of the Skill-Gap Agent, derived from the full spec
(`../skill-gap-agent-spec.md`): the smallest system that runs the pipeline
end-to-end on the seed data (skills JSON + 13 JDs from the manual session) and
produces a ranked gap plan.

**Summary:** given a user's skills dump and target job descriptions, the agent
builds a weighted skill graph, scores skill transferability with an LLM judge,
gates low-confidence judgments through a human-in-the-loop prompt, ranks gaps
by JD frequency, and outputs a ranked plan of grounded learning projects. The
manual 13-JD gap analysis from an earlier session is the validation set and
README case study.

## Reading Order

| File | Contents |
|---|---|
| [decisions.md](decisions.md) | Locked technology and scope decisions, with rationale |
| [architecture.md](architecture.md) | v1 pipeline diagram, component details, graph schema |
| [validation.md](validation.md) | The rubric — what "done" means, measured against the manual run |
| [milestones.md](milestones.md) | Build order, milestone by milestone |
| [deferred-enhancements.md](deferred-enhancements.md) | Every trade-off made for v1, and the trigger to restore each |
| [open-items.md](open-items.md) | Unresolved items that don't block starting |