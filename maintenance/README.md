# Periodic maintenance charter

> Human-owned. This file configures maintenance mode for this project.
> Normal task agents do not read it. The procedure is in
> `.agent-devkit/roles/maintenance.md`.

- **Owner:** Shubham Singh
- **Cadence:** before each release (version tag or Chrome Web Store submission); otherwise on demand
- **Last run:** none yet — pilot pass pending
- **Next due:** before the next release

## Why this exists

Feature sessions see one task and one diff. Maintenance sees the whole
repository and finds spec-code drift, spec-spec contradictions, stale specs,
code entropy, test rot, and context bloat that no single session can see.

## Active normative sources

The files that must be true right now:

- `specs/01-system-overview.md` — system map/router and code conventions guardrails
- `specs/04-reader.md` … `specs/15-desktop-companion.md` — component specs
- `.github/copilot-instructions.md` — workflow rules
- `README.md` — user-facing entry point (extension + companion quickstart)
- `CHROMEWEBSTORE.md` — store submission material: permission justifications, listing copy, declarations
- `docs/` — derived, non-authoritative; stale claims here are still defects
  (`docs/overview.md`, `docs/index.md`, `docs/privacy-policy.md`)

## Historical registers (do not delete)

- `specs/02-decisions.md` — append-only; mark superseded, never rewrite
- `specs/03-milestones.md` — build history, verification records, learnings
- `specs/tasks/T-MAINT-*.md` — maintenance work orders
- `board/maintenance/` — maintenance reports
- `board/verify-T-*.md`, `board/review-T-*.md` — per-task verification and review records
- `board/issues/` — durable issue records
- `docs/changelog.md` — one line per completed task, append-only

## Commands

- Lint: `python -m ruff check .`
- Tests: `python -m pytest -q`
- Project checks:
  - `python -m skill_gap_agent.m29_check`
  - `python -m skill_gap_agent.m13_check`
  - `python -m skill_gap_agent.m18_check`
  - `python -m skill_gap_agent.m20_check`
  - `node --check extension/sidepanel.js` and `node --check extension/content.js`
  - `python -m skill_gap_agent.m26_check` — only when `data/skillsdataset.json` is present
- Full verification: `python scripts/verify.py --task <id>`
- Link/reference check: manual — grep specs, README, and store docs for referenced paths/symbols; no automated link checker is configured
- Platform CI equivalent: `.github/workflows/windows-release.yml` (Lint, tests, checks step)

## Scope and branch

- Branch: `req/T-MAINT-<YYYYMMDD>`
- Work order: `specs/tasks/T-MAINT-<YYYYMMDD>.md` (from
  `.agent-devkit/templates/maintenance-task.md`)
- Files this pass may touch: `specs/`, `src/skill_gap_agent/`, `extension/`,
  `packaging/`, `docs/`, `.github/`, `README.md`, `CHROMEWEBSTORE.md`,
  `maintenance/`, `board/maintenance/`
- Run exclusively: no other agents/worktrees while this pass runs.

## Project-specific focus

- **Tests live in `src/skill_gap_agent/test_*.py`** (pytest discovers them
  there), not in a top-level `tests/` directory. Milestone check harnesses
  are the `m*_check.py` / `m3_judge.py` modules in the same package.
- **Privacy claims are load-bearing** (Chrome Web Store Limited Use):
  `README.md`, `docs/privacy-policy.md`, `CHROMEWEBSTORE.md`, and
  `specs/14-observability.md` must agree that data stays local except for
  the chosen AI provider and GitHub's public search API. No telemetry.
- **Version is duplicated** in `pyproject.toml` and
  `skill_gap_agent.__version__`; the release build asserts they match.
- **Extension is plain JS with no build step or linter** — use
  `node --check`, and verify manifest permissions against the store copy.
- **Generated/local, not sources:** `data/`, `output/`, `dist/`, `build/`,
  `board/locks/`, `board/lock-events.log`. Never audit or delete user data.
- **Vendored kit files:** `.agent-devkit/` and `scripts/` are refreshed by
  re-running `init.py` from the newer `agent-devkit-simplified` checkout.
  Do not fix kit defects in place; record them upstream.

## First-run setup

- [x] Fill in the commands above.
- [x] Choose a cadence and record the next due date.
- [x] List active and historical sources.
- [ ] Run one pilot pass and adjust this charter from what it finds.
