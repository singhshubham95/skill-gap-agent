# T-MAINT-<YYYYMMDD>: periodic maintenance pass

- **Status:** planned | in-progress | in-review | done | blocked
- **Agent session:** `<exclusive maintenance session URI>`
- **Blocked by:** none — do not run in parallel with feature agents
- **Charter:** `maintenance/README.md`
- **Role:** `.agent-devkit/roles/maintenance.md`

## Scope

One pass over the whole repository, or the subset named here. This is not a
feature task; it audits and repairs drift, contradictions, stale specs, code
entropy, test rot, and context bloat.

- **Scope:** `<whole repo | specs only | named area>`
- **Out of scope:** new features, large refactors, behavior changes without
  an owning spec or decision.

## Files to touch (the scope guard permits exactly these)

List the broad directories this pass may repair. Keep the list honest; widen
it before editing something new.

- `specs/`
- `src/`
- `tests/` or the project's test directory
- `docs/`
- `README.md`
- `.github/`
- `maintenance/`
- `board/maintenance/`

## Acceptance criteria

1. All six audits were run and their findings recorded in the report.
2. Every finding has evidence (`file:line`), a category, and a decision.
3. Clear drift/entropy/rot was fixed; larger items became follow-up tasks.
4. No history was rewritten and no append-only row was deleted.
5. No test was weakened, skipped, or deleted to get green.
6. Full verification is green; behavior changes have spec + tests.
7. `board/maintenance/<date>.md` is complete and the charter is updated.
8. The normal agent instruction file was not expanded with the audit.

## Tests to run

- `<lint/test/check commands from the charter>`
- `python scripts/verify.py --task T-MAINT-<YYYYMMDD>`
- `python scripts/path_guard.py --task T-MAINT-<YYYYMMDD>`

## Completion protocol

1. Work exclusively; do not run alongside feature agents.
2. Audit first, fix second, verify last.
3. Write the report, update the charter, add the changelog line.
4. Mark this task done and release any locks.
