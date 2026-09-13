# Skill-Gap Agent

Minimal v1 build of the Skill-Gap Agent, derived from the full spec
(`skill-gap-agent-spec.md`): the smallest system that runs the pipeline
end-to-end on the seed data (skills JSON + 13 JDs from the manual session) and
produces a ranked gap plan.

**Summary:** given a user's skills dump and target job descriptions, the agent
builds a weighted skill graph, scores skill transferability with an LLM judge,
gates low-confidence judgments through a human-in-the-loop prompt, ranks gaps
by JD frequency, and outputs a ranked plan of grounded learning projects. The
manual 13-JD gap analysis from an earlier session is the validation set and
README case study.

## Specs

All specifications live in [`specs/`](specs/). Start with the system overview,
then dive as needed:

| File | Contents |
|---|---|
| [specs/1-system-overview.md](specs/1-system-overview.md) | **Start here** — layered component map, component↔code table, data flow, repo map |
| [specs/2-architecture.md](specs/2-architecture.md) | Deep design: pipeline components, graph schema |
| [specs/3-decisions.md](specs/3-decisions.md) | Locked technology and scope decisions, with rationale |
| [specs/4-validation.md](specs/4-validation.md) | The rubric — what "done" means, measured against the manual run |
| [specs/5-milestones.md](specs/5-milestones.md) | Build order, milestone by milestone, with progress |
| [specs/6-deferred-enhancements.md](specs/6-deferred-enhancements.md) | Every trade-off made for v1, and the trigger to restore each |
| [specs/7-open-items.md](specs/7-open-items.md) | Unresolved items that don't block starting |