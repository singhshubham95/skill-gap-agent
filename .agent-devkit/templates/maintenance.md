# Periodic maintenance charter

> Human-owned. This file configures maintenance mode for this project.
> Normal task agents do not read it. The procedure is in
> `.agent-devkit/roles/maintenance.md`.

- **Owner:** `<human>`
- **Cadence:** `<before each release | after each milestone | monthly | on demand>`
- **Last run:** `<YYYY-MM-DD — report link>`
- **Next due:** `<YYYY-MM-DD or trigger>`

## Why this exists

Feature sessions see one task and one diff. Maintenance sees the whole
repository and finds spec-code drift, spec-spec contradictions, stale specs,
code entropy, test rot, and context bloat that no single session can see.

## Active normative sources

The files that must be true right now:

- `specs/01-...` — system map/router
- `specs/NN-...` — component specs
- `.github/copilot-instructions.md` (or `AGENTS.md`/`CLAUDE.md`) — workflow rules
- `README.md` — user-facing entry point
- `docs/` — derived, non-authoritative; stale claims here are still defects

## Historical registers (do not delete)

- `specs/02-decisions.md` — append-only; mark superseded, never rewrite
- `specs/03-milestones.md` — build history, verification records, learnings
- `specs/tasks/T-MAINT-*.md` — maintenance work orders
- `board/maintenance/` — maintenance reports

## Commands

Fill in the project's actual commands:

- Lint: `<command>`
- Tests: `<command>`
- Project checks: `<command(s)>`
- Full verification: `python scripts/verify.py --task <id>`
- Link/reference check: `<command or manual>`

## Scope and branch

- Branch: `req/T-MAINT-<YYYYMMDD>`
- Work order: `specs/tasks/T-MAINT-<YYYYMMDD>.md` (from
  `.agent-devkit/templates/maintenance-task.md`)
- Files this pass may touch: `<list broad directories and files>`
- Run exclusively: no other agents/worktrees while this pass runs.
- Destructive repairs (spec/code/test/register removal, status downgrade)
  require your explicit approval during the pass; the work order does not
  pre-approve them.

## Project-specific focus

- `<known drift areas, generated code, vendored files, intentional exceptions>`
- `<tools to use for dead code / duplication / test strength>`
- `<anything the generic role must not touch>`

## First-run setup

- [ ] Fill in the commands above.
- [ ] Choose a cadence and record the next due date.
- [ ] List active and historical sources.
- [ ] Run one pilot pass and adjust this charter from what it finds.
