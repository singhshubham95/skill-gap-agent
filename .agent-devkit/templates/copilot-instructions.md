<!-- Project instruction file template. Copy into whichever file your
harness reads: .github/copilot-instructions.md (Copilot), CLAUDE.md
(Claude Code), or AGENTS.md (generic). Keep workflow rules only —
code-level conventions belong in the project's specs. -->

# Agent Instructions — <project>

Workflow rules for any AI agent working in this repository. Read before
changing code or specs. The methodology is canonical in the
`agent-devkit-simplified` repo (installed here under `.agent-devkit/` and
`scripts/`).

## Source of truth

`specs/` (flat, numbered, read in order) defines what the system is and
does. Design in the spec first, then implement; code changes that alter
behavior must touch the spec in the same change. Registers: a numbered
component file per component (mechanics + status), an append-only decisions
log (add rows, mark superseded, never rewrite), and a milestones log (build
order, verification records, learnings, deferred/open items). **One home per
register:** never restate design or rationale in a second file — link
instead.

Status markers everywhere: **Built** (code exists, validated — cite the
milestone), **Designed** (specified, no code yet), **Deferred** (restore
trigger recorded). Present tense must match the code.

## Multi-agent workflow

One agent = one functional requirement, end to end (plan → implement → test
→ review → close) in a single session. Multiple agents run **in parallel**,
one per requirement, isolated by git worktrees (`req/T-*` branches) and file
locks. There is no session chaining and no role split.

- Task work orders live in `specs/tasks/T-<id>.md` (template in
  `.agent-devkit/templates/task.md`) — slim: spec links, out-of-scope,
  files to touch, per-change acceptance criteria, tests, status. The spec
  owns the HOW; the task owns the WHERE/WHAT-NOW.
- **Lock board** (the anti-collision mechanism): claim before editing shared
  files (`python scripts/claim.py --task T-<id> <paths>`), always release
  (`python scripts/release.py --task T-<id>`) on every exit path. Stale
  locks (>30 min) auto-reclaim and log to `board/lock-events.log`.
- **Scope enforcement** (deterministic, not prompt-based): a `req/T-*`
  branch may only change files listed in its task's "Files to touch", plus
  `board/`. Enforced by `python scripts/path_guard.py` and the `agent-gates`
  CI workflow. To widen scope, update the task file first.
- Issues: blocked on shared state or find a shared defect you must not
  unilaterally change? `board/issues/` (template in
  `.agent-devkit/templates/issue.md`) — record it and what you did meanwhile.
- `docs/` is the derived human tier (short, non-authoritative): `overview.md`
  (intent) and `changelog.md` (one line per completed task).

## Verification before declaring done

- Run `python scripts/verify.py --task T-<id>` (lint + tests + project
  checks) and `python scripts/path_guard.py`; both must pass.
- Self-review the diff against the task's acceptance criteria — a checklist
  pass, deliberately skeptical of your own work. The test suite is the
  objective gate; do not rationalize a failing check.
- User-visible flows get validated interactively once, recorded in the
  milestones log.
