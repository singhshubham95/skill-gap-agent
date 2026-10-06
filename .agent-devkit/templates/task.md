# Task template — a work order, not a recipe

<!--
Rules (from the workflow design, see agent-devkit README):
- The component spec owns the HOW. Never restate design here — link to it.
- This file owns the WHERE/WHAT-NOW: scope boundary, claimed files,
  per-change acceptance, tests, status.
- Keep it slim: 10-15 lines of substance. If it grows, the spec is too thin
  or the task is too big — fix the right one.
-->

# T-<id>: <short goal, one line>

- **Status:** planned | in-progress | in-review | done | blocked
- **Pipeline:** plan/T-<id> → impl/T-<id> → reviewer
- **Planner session:** <session URI — where downstream stages route issues>
- **Blocked by:** <none | T-xxx | board/issues/...>

## Spec sections this task applies (the HOW lives there)

- [component-spec.md](../../specs/NN-component.md) §Section — what it covers
- [decisions](../../specs/02-decisions.md) — relevant decision rows

## Out of scope for this task

- <explicit exclusions so the implementer cannot gold-plate or guess>

## Files to touch (the lock board claims exactly these)

- `path/to/file.py`
- `path/to/other.file`

## Acceptance criteria (checkable, per-change)

1. <criterion the reviewer can verify against the diff and the tests>
2. <...>

## Tests to add / run

- <test files to add or extend>
- <commands: `ruff check .`, `pytest`, `node --check <files>`, `mNN_check.py`>

## Completion protocol

1. Implementer: run tests, fill results below, release locks.
2. Reviewer: check the diff against the acceptance criteria above only.
3. On approval, planner writes the changelog line (docs/changelog.md).
