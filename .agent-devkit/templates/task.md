# Task template — a work order, not a recipe

<!--
Rules (see agent-devkit-simplified README):
- The component spec owns the HOW. Never restate design here — link to it.
- This file owns the WHERE/WHAT-NOW: scope boundary, claimed files,
  per-change acceptance, tests, status.
- "Files to touch" is machine-read by scripts/path_guard.py — it is the
  deterministic scope boundary. List every path the diff may change.
- Keep it slim: 10-15 lines of substance. If it grows, the spec is too thin
  or the task is too big — fix the right one.
-->

# T-<id>: <short goal, one line>

- **Status:** planned | in-progress | in-review | done | blocked
- **Agent session:** <session URI — where other agents / the human reach you>
- **Blocked by:** <none | T-xxx | board/issues/...>

## Spec sections this task applies (the HOW lives there)

- [component-spec.md](../../specs/NN-component.md) §Section — what it covers
- [decisions](../../specs/02-decisions.md) — relevant decision rows

## Out of scope for this task

- <explicit exclusions so parallel work is not disturbed and you cannot
  gold-plate or guess>

## Files to touch (the lock board claims exactly these)

- `path/to/file.py`
- `path/to/other.file`

## Acceptance criteria (checkable, per-change)

1. <criterion you can verify against the diff and the tests>
2. <...>

## Tests to add / run

- <test files to add or extend>
- <commands: `ruff check .`, `pytest`, `node --check <files>`, `mNN_check.py`>

## Completion protocol

1. Implement, run `python scripts/verify.py --task T-<id>` until green.
2. Self-review the diff against the acceptance criteria above (checklist,
   not taste).
3. Write the changelog line (docs/changelog.md), mark this done, release
   locks (`python scripts/release.py --task T-<id>`).
