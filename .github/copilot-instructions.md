# Agent Instructions — Skill-Gap Agent

Guidance for any AI agent (or contributor) working in this repository. Read
before changing code or specs.

## Scope of this file

This file records **workflow rules only** — how to work in this repo. It
deliberately contains no code-level conventions or implementation facts:
those are spec content (see **Conventions & Guardrails** in
`specs/01-system-overview.md`) and change with the code, while this file must
stay implementation-agnostic so it cannot silently drift.

## Project snapshot

A spec-driven project: `specs/` (flat, numbered, read in order) is the
source of truth for everything the system is and does — start at
`specs/01-system-overview.md` for the component map and current state, and
follow its links rather than relying on details memorized here.

## Communication with the user

- The user is a **beginner in the frameworks and engineering domains this
  project is built on**. Never assume framework internals are known — when a
  point depends on how any library behaves, briefly explain that behavior in
  plain language first, then apply it to the project.
- **Keep the details, add the context.** Do not simplify away technical
  specifics; instead, precede each non-obvious point with enough background
  (what the thing is, why it matters here) that a newcomer can follow.
  This rule governs **conversation with the user**, not spec files: specs
  follow the one-home-per-register rule and link rather than re-explain.
- Prefer concrete examples from this repo's own code/data over abstract
  phrasing. Avoid dense jargon-only paragraphs; if a paragraph needs
  unpacking, break it into a short explanation followed by the implication.

## Spec-first workflow

- `specs/` is the source of truth. Design or change design **in the spec
  first**, then implement. Code PRs that alter behavior must touch the spec
  in the same change.
- After implementing a milestone: flip its status markers to Built, record
  learnings in `specs/03-milestones.md`, append any new locked decision to
  `specs/02-decisions.md`.
- **One home per register.** Design prose lives in exactly one place — the
  owning component's spec file. `02-decisions.md` holds the decision + a
  one-line rationale and links to the design; `03-milestones.md` holds the
  verification record, genuinely new learnings, and links. Never restate
  the design in a second file — link to it instead. If you find yourself
  writing the same rationale in two files, that is the signal to delete one
  copy and link. **Cross-cutting scope does not create an exception:** a
  design that touches many stages still has exactly one home (the component
  file that owns it), and every other file links to it.

## Spec evolution rules

The specs are **living target-state documents**, not per-version snapshots:

1. **Status markers everywhere.** Every component, milestone, and roadmap
   item is labeled one of: **Built** (code exists, validated — cite the
   milestone), **Designed** (specified for an upcoming milestone, no code
   yet), or **Deferred** (known trade-off, restore trigger recorded in
   `03-milestones.md` §Deferred). Never describe a not-yet-built thing in
   language that implies it exists; a contributor must be able to trust that
   present-tense descriptions match the code.
2. **Evolve in place; never version-split.** Do not create `specs/v2/` or
   duplicate files per release. Versions are labels on milestone ranges
   (e.g. "the shipped range" vs. "the current target range"), not document
   boundaries. When new design changes an existing component, revise that
   component's section and note the change; when it adds a component, add a
   new section in the owning file — or a new file if the component is
   substantial (see rule 6).
3. **`02-decisions.md` is append-only.** Add rows, mark superseded ones,
   never delete or silently rewrite. Mark supersessions in a fixed format —
   `~~struck text~~ (superseded by <Mn> row, <date>)` — so a reader can see
   at a glance which rows are historical. Same for milestone entries: keep
   history, append learnings. **Learnings are bounded:** record what
   surprised you or changed during the build (bugs, discoveries,
   corrections, measured results) — not the design itself, which lives in
   the owning component spec.
4. **Milestone numbers are linear and global** (M1, M2, M3, …). Never
   restart numbering per version ("v2-M1" is forbidden).
5. **No stale references.** Specs and README must only reference files,
   modules, and artifacts that exist in the repo. If you delete or rename an
   artifact, grep the docs for it in the same change.
6. **Component specs are per-component, eager.** Each substantial component
   owns one spec file — pipeline stages and non-stage components alike; the
   current inventory is indexed in `specs/01-system-overview.md`. A component
   earns its own file when it has its own code directory or module cluster,
   its own status lifecycle, and enough design to bloat a shared file;
   otherwise it stays a section of the nearest component's file. Component
   files own mechanics + status only. History stays single-source: decisions
   in `02-decisions.md`, build order + learnings + trade-offs + open
   questions in `03-milestones.md` (§§Deferred/Open hold the rest) —
   component files link by ID (milestone number, decision row, item bullet)
   and never copy that text. Status markers in component files are derived
   from the milestone entry, never set independently. Ownership follows
   code: a design lives in the spec file of the component whose code
   implements it, whatever stages it touches, and a shared data structure is
   documented in the file of the component that defines it.
   `01-system-overview.md` is a **map and router**, never a design host: it
   holds orientation material and — at most — a 2–4 line summary plus a
   link per component. If a section of `01` reads as design rather than as a
   map entry, move it to the owning component file.

## Code conventions

Code-level conventions and architectural guardrails are **spec content, not
instruction content** — they change with the code, and this file must not
name modules or concerns that may not exist tomorrow. Before writing or
changing code, read the **Conventions & Guardrails** section of
`specs/01-system-overview.md` and follow it. If your change alters how any of those concerns are handled,
update that section in the same change (spec-first rule above).

## Verification before declaring done

- The full pipeline runs end-to-end without errors — find the current entry
  point in the README quickstart (do not trust a memorized command).
- Lint and tests clean (`ruff check .` and `pytest` while those are the
  configured tools).
- If a milestone adds a user-visible flow, validate it interactively once
  and record the result in `specs/03-milestones.md` before marking it Built.
