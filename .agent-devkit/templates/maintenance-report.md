# Maintenance report — <YYYY-MM-DD>

- **Task:** T-MAINT-<YYYYMMDD>
- **Branch:** req/T-MAINT-<YYYYMMDD>
- **Commit:** `<hash>`
- **Devkit:** `<version from devkit.version>`
- **Scope:** `<whole repo | subset>`
- **Exclusive session:** yes — no other agents active

## Baseline

| Check | Command | Result |
|---|---|---|
| Lint | `<command>` | PASS/FAIL |
| Tests | `<command>` | PASS/FAIL |
| Project checks | `<command>` | PASS/FAIL |

## Summary

| Category | Findings | Fixed | Needs approval | Follow-up | Deferred |
|---|---:|---:|---:|---:|---:|
| A1 Spec-code drift | | | | | |
| A2 Spec-spec contradictions | | | | | |
| A3 Stale specs | | | | | |
| A4 Code entropy | | | | | |
| A5 Test rot | | | | | |
| A6 Context bloat | | | | | |

## Findings

### F-01 — `<title>`

- **Category:** `A1 | A2 | A3 | A4 | A5 | A6`
- **Severity:** `high | medium | low`
- **Evidence:** `path:line` (quote or describe)
- **Decision:** `fix now | needs approval | follow-up task | issue | deferred`
- **Action:** `<what changed or which task/issue was created>`
- **Verification:** `<command/result or link>`

## Changes made

- Spec: `<links>`
- Code: `<links>`
- Tests: `<links>`
- Docs/context: `<links>`

## Approvals

Destructive fixes require explicit human approval before they are applied.
Write `none` when no destructive finding was proposed.

| Finding | Approved by | Scope (files/paths) | Date |
|---|---|---|---|
| | | | |

## Verification

- Full suite: `<command/result>`
- Path guard: `<command/result>`
- Link/reference check: `<result>`
- No weakened/skipped tests: `<evidence>`

## Follow-ups

| Item | Type | Owner | Link |
|---|---|---|---|
| | task/issue | | |

## Carry-over to next pass

- `<unresolved item and trigger>`

## Sign-off

- [ ] Report complete, every finding classified
- [ ] Non-destructive fixes verified
- [ ] Destructive fixes explicitly approved and recorded (or none)
- [ ] Follow-ups filed
- [ ] Charter last-run/next-due updated
