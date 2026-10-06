<!-- Project instruction file template. Copy into whichever file your
harness reads: .github/copilot-instructions.md (Copilot), CLAUDE.md
(Claude Code), or AGENTS.md (generic). Keep workflow rules only —
code-level conventions belong in the project's specs. -->

# Agent Instructions — <project>

Workflow rules for any AI agent working in this repository. Read before
changing code or specs. The methodology is canonical in the `agent-devkit`
repo (installed here under `.agent-devkit/` and `scripts/`).

## Source of truth

`specs/` (flat, numbered, read in order) defines what the system is and
does. Design in the spec first, then implement; code changes that alter
behavior must touch the spec in the same change. Registers: a numbered
component file per component (mechanics + status), an append-only
decisions log (`specs/02-decisions.md`-style — add rows, mark superseded,
never rewrite), and a milestones log (build order, verification records,
learnings, deferred/open items). **One home per register:** never restate
design or rationale in a second file — link instead.

Status markers everywhere: **Built** (code exists, validated — cite the
milestone), **Designed** (specified, no code yet), **Deferred** (restore
trigger recorded). Present tense must match the code.

## Multi-agent workflow

Pipelines: one per requirement, human-initiated. Within a pipeline:
planner → implementer → reviewer, sequential. Across pipelines: parallel,
isolated by git worktrees (`plan/T-*` / `impl/T-*`) and file locks.

- Task work orders live in `specs/tasks/T-<id>.md` (template in
  `.agent-devkit/templates/task.md`) — slim: spec links, out-of-scope,
  files to touch, per-change acceptance criteria, tests, status. The spec
  owns the HOW.
- Lock board: claim before editing shared files
  (`python scripts/claim.py --role <role> --task T-<id> <paths>`), always
  release (`python scripts/release.py --task T-<id>`) on every exit path.
  Stale locks (>30 min) auto-reclaim and log to `board/lock-events.log`.
- Write rules (enforced by `python scripts/path_guard.py` and the
  `agent-gates` CI workflow; branch prefixes are the role signal):
  planner writes `specs/`, `docs/`, `board/`; implementer writes
  everything except `specs/`/`docs/`; reviewer writes `board/` only.
- Session chaining: each stage ends by spawning the next with the handoff
  from `.agent-devkit/templates/handoff.md` and that role's model from
  `.agent-devkit/config/model-chains.yaml`.
- Issues: implementer/reviewer never fix spec defects — `board/issues/`
  (template in `.agent-devkit/templates/issue.md`) + message the
  originating planner session (URI in the task file); the planner fixes
  the spec and messages back.
- `docs/` is the derived human tier (short, non-authoritative): `overview.md`
  (intent) and `changelog.md` (planner adds one line per completed task).

## Verification before declaring done

- Run `python scripts/verify.py --task T-<id>` (lint + tests + project
  checks) and `python scripts/path_guard.py`; both must pass.
- User-visible flows get validated interactively once, recorded in the
  milestones log.
