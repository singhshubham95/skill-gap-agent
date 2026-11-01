# T-MAINT-20261101-ARCHIVE: archive closed milestone eras

- **Status:** planned
- **Owner:** human
- **Source:** `board/maintenance/2026-11-01.md` §F-24
- **Blocked by:** none
- **Trigger:** before v2 spec work or the next spec restructure

## Why

`specs/03-milestones.md` is ~101 KB / 1,411 lines. It is append-only
history and must not be deleted, but one reading pass no longer fits in a
working context. Split closed eras into archive files and keep the live
file as a readable index + current era.

## Files to touch (the scope guard permits exactly these)

- `specs/`
- `docs/`
- `README.md`

## Acceptance criteria

1. Closed milestone history lives in archive files with stable links; no
   row is deleted or rewritten.
2. `03-milestones.md` keeps the current era, §Deferred, and §Open, and links
   to each archive.
3. Every inbound link still resolves; `README`/`docs/` references updated.
4. Spec-evolution rules in `01-system-overview.md` describe the new layout.

## Tests to run

- Link/reference check (manual grep)
- `python -m pytest -q`
- `python -m ruff check .`
