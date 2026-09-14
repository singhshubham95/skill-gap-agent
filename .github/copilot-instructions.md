# Agent Instructions — Skill-Gap Agent

Guidance for any AI agent (or contributor) working in this repository. Read
before changing code or specs.

## Scope of this file

This file records **workflow rules only** — how to work in this repo. It
deliberately contains no code-level conventions or implementation facts:
those are spec content (see **Conventions & Guardrails** in
`specs/1-system-overview.md`) and change with the code, while this file must
stay implementation-agnostic so it cannot silently drift.

## Project snapshot

Python 3.11+ CLI agent. A spec-driven project: `specs/` (flat, numbered,
read in order) is the source of truth for everything the system is and does —
start at `specs/1-system-overview.md` for the component map and current
state, and follow its links rather than relying on details memorized here.

## Spec-first workflow

- `specs/` is the source of truth. Design or change design **in the spec
  first**, then implement. Code PRs that alter behavior must touch the spec
  in the same change.
- After implementing a milestone: flip its status markers to Built, record
  learnings in `specs/5-milestones.md`, append any new locked decision to
  `specs/3-decisions.md`.

## Spec evolution rules

The specs are **living target-state documents**, not per-version snapshots:

1. **Status markers everywhere.** Every component, milestone, and roadmap
   item is labeled one of: **Built** (code exists, validated — cite the
   milestone), **Designed** (specified for an upcoming milestone, no code
   yet), or **Deferred** (known trade-off, restore trigger recorded in
   `6-deferred-enhancements.md`). Never describe a not-yet-built thing in
   language that implies it exists; a contributor must be able to trust that
   present-tense descriptions match the code.
2. **Evolve in place; never version-split.** Do not create `specs/v2/` or
   duplicate files per release. Versions are labels on milestone ranges
   (e.g. "the shipped range" vs. "the current target range"), not document
   boundaries. When new design changes an existing component, revise that
   component's section and note the change; when it adds a component, add a
   new section.
3. **`3-decisions.md` is append-only.** Add rows, mark superseded ones,
   never delete or silently rewrite. Same for milestone entries: keep
   history, append learnings.
4. **Milestone numbers are linear and global** (M1, M2, … M7, M8, …). Never
   restart numbering per version ("v2-M1" is forbidden).
5. **No stale references.** Specs and README must only reference files,
   modules, and artifacts that exist in the repo. If you delete or rename an
   artifact, grep the docs for it in the same change.

## Code conventions

Code-level conventions and architectural guardrails (LLM access, override
files, normalization, output safety) are **spec content, not instruction
content** — they change with the code, and this file must not name modules
that may not exist tomorrow. Before writing or changing code, read the
**Conventions & Guardrails** section of `specs/1-system-overview.md` and
follow it. If your change alters how any of those concerns are handled,
update that section in the same change (spec-first rule above).

## Verification before declaring done

- The full pipeline runs end-to-end without errors — find the current entry
  point in the README quickstart (do not trust a memorized command).
- Lint and tests clean (`ruff check .` and `pytest` while those are the
  configured tools).
- If a milestone adds a user-visible flow, validate it interactively once
  and record the result in `specs/5-milestones.md` before marking it Built.
