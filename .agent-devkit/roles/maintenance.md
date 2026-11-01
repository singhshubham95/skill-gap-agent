# Role: Periodic maintenance (exclusive)

You are running one maintenance pass over the whole repository. This is not
a normal feature task. The human starts this mode explicitly; feature agents
must not run alongside you.

One maintenance pass = one maintenance task = your whole job: audit, fix
what is safely fixable, verify, report, close. The point is the global view
that no single feature session has.

## Shared rules

The normal rules still apply: `specs/` is canonical, design in the spec
first, behavior changes touch the spec in the same change, the issue channel
is `board/issues/`, and verification is `scripts/verify.py`. Read
`agent.md` in this directory for the normal task workflow; this file adds
the maintenance procedure on top of it.

## Preconditions

- The human has explicitly started a maintenance pass.
- No other agent or worktree is active. Maintenance is exclusive: it repairs
  shared files across the repository, and the lock board claims literal
  paths, not directories, so parallel feature work would collide.
- The working tree is clean, or all in-progress work is committed or stashed.
- You are on a dedicated branch: `req/T-MAINT-<YYYYMMDD>`.
- A work order exists at `specs/tasks/T-MAINT-<YYYYMMDD>.md`, created from
  `.agent-devkit/templates/maintenance-task.md`, with the broad files this
  pass may touch.
- You have read the project charter at `maintenance/README.md`. It names the
  project's active sources, historical registers, commands, and cadence.

If any precondition is missing, stop and ask the human. Do not run
maintenance on `main` or beside feature agents.

## Job

1. **Baseline.** Record the commit, branch, devkit version, and current
   state of the project's checks. Run the lint/tests/check commands named
   in the charter before changing anything. If the baseline is red, record
   the failures and ask whether to proceed; do not hide them in the report.

2. **Build the map.** List:
   - active normative sources (component specs, map/router, instruction
     files, README);
   - historical registers (decisions, milestone log, deferred/open items);
   - code modules and entry points;
   - tests and check harnesses;
   - progress/context files (changelog, board reports, any AGENTS/CLAUDE
     files).
   Use the charter's project-specific paths. This map is the global view.

3. **Run the six audits.** Record every finding with its category,
   severity, evidence (`file:line`), and proposed action. Do not fix while
   auditing; finish the inventory first so related findings are fixed
   together.

   ### A1. Spec-code drift
   - For every claim marked Built, verify the code exists and matches.
   - For every module, endpoint, flag, command, and config key, verify it
     has a spec home; flag orphans.
   - Grep for spec references to files, symbols, commands, and endpoints
     that no longer exist.
   - Compare task acceptance criteria and tests with implemented behavior.
   - Check that Built/Designed/Deferred statuses still match reality.

   ### A2. Spec-spec contradictions
   - Extract normative claims from the owning component specs, the
     map/router, decisions, milestones, README, and instruction files.
   - Look for conflicting values (thresholds, defaults, paths, endpoints,
     versions), status conflicts, ownership conflicts, and duplicated
     rationale.
   - Apply the one-home rule: the owning component file wins; replace
     copies with links.
   - If the conflict is a real design choice, record a decision row; if it
     is ambiguous, file an issue.

   ### A3. Stale specs
   - Audit Built/Designed/Deferred markers: Designed has no code, Built has
     evidence, Deferred has a restore trigger.
   - Review completed Open items and delete them once their results are
     recorded.
   - Check supersession markers and links.
   - Check derived docs (`README`, `docs/`) for stale concepts, not only
     broken links.
   - Do not delete history. Strike superseded decisions and keep the
     historical registers.

   ### A4. Code entropy
   - Find unused imports, symbols, functions, classes, constants, flags, and
     one-off scripts.
   - Find duplicate helpers and near-duplicate logic; consolidate only when
     the shared behavior is clear.
   - Find abandoned feature flags, dead branches, commented-out code, and
     obsolete compatibility shims.
   - Compare the repo map and README structure with the actual tree.
   - Verify the project's centralization guardrails still hold (for
     example, one LLM module, one normalization module).
   - Use the language's usual tools; the charter names them. The absence of
     a tool is a finding, not a reason to guess.

   ### A5. Test rot
   - Map each test/check to the spec claim or contract it protects.
   - Flag skipped/xfail tests without a recorded reason.
   - Flag assertions on labels, strings, or source text that do not check
     the behavior; distinguish deliberate structural locks (security, copy,
     no-click) from brittle implementation checks.
   - Flag stubs that accept any call shape, tests that cannot fail, and
     tests weakened to get green.
   - Run the suite and compare with the baseline.
   - For high-risk contracts, verify red→green: temporarily break the
     contract in a scratch copy, confirm a test fails, then restore.
   - Prefer behavior/contract assertions over implementation details.

   ### A6. Context bloat
   - Measure the instruction, spec, and progress files; flag growth that no
     longer fits one reading pass.
   - Look for contradictory or duplicated statements across sessions.
   - Verify the normal agent instruction file is workflow-only; code
     conventions belong in the specs.
   - Verify the system overview is a map/router, not a second design home.
   - Verify learnings are bounded (surprises, not design).
   - Check derived docs against current state; regenerate or fix them.
   - Propose archives and links; never delete append-only history.

4. **Classify and fix.** For each finding decide:
   - **Fix now** — clear drift, contradiction, stale text, dead code, weak
     test, or context bloat with an unambiguous correct answer.
   - **Follow-up task** — new behavior, a large refactor, or anything that
     needs its own design and review.
   - **Issue** — the correct side is genuinely unclear, or shared state
     belongs to another owner.
   - **Deferred** — real but out of scope for this pass; record the trigger.
   Keep fixes small and reviewable. Maintenance is not a mega-task.

5. **Fix rules.**
   - Spec first: if behavior changes, update the owning spec before code.
   - Do not rewrite history; mark supersessions in the fixed format.
   - Do not edit vendored kit files (`.agent-devkit/`, `scripts/`) to fix a
     kit defect; record it upstream.
   - Do not delete user data, generated artifacts, or code whose use you
     cannot rule out.
   - Do not weaken, skip, or delete a test to make the suite green.
   - Do not invent requirements; missing intent is a question or issue.
   - Do not declare code correct just because it runs; check the decisions
     and milestones before deciding which side of a drift is stale.

6. **Verify.** Run the full project checks from the charter:
   - lint, tests, and the project's check harnesses;
   - `python scripts/path_guard.py --task T-MAINT-<YYYYMMDD>`;
   - link/reference checks and any audit-specific checks;
   - for behavior changes: spec updated, tests added, `scripts/verify.py`
     green.
   Record the before/after results.

7. **Report and close.**
   - Write `board/maintenance/<YYYY-MM-DD>.md` from
     `.agent-devkit/templates/maintenance-report.md`.
   - Update `maintenance/README.md` with the last run and next due date.
   - Add one line to `docs/changelog.md`.
   - Mark the maintenance task done.
   - Release any locks: `python scripts/release.py --task T-MAINT-<date>`.
   - Leave the working tree clean except for the report and committed fixes.

## Output standard

Every finding cites `file:line` and one of the six categories. Every fix
traces to a spec section, decision row, or issue. Every unresolved item has
a follow-up task/issue and an owner. A pass that finds nothing must say what
was checked and why it is clean; "no issues" without evidence is not a
report.
