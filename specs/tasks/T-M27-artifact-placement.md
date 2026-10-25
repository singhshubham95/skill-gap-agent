# T-M27-artifact-placement: One session, one place — end artifact placement

- **Status:** superseded (2026-10-25 by M28 — the SHA-keyed session store and
  its placement rules were replaced by a single central workspace; see
  [13-intake.md](../13-intake.md) §Workspace store and the M28 rows in
  [02-decisions.md](../02-decisions.md))
- **Agent session:** ahp-session:/8ef0d59f-f8a0-4a58-8eb1-2d1b733803ca
- **Blocked by:** none

## Why this task exists

The user reported that `output/` holds loose files one level in that duplicate
the concepts of files inside each `output/sessions/<sha256>/` folder, and asked
for the cause to be found with the goal that session artifacts live in one
place. This work order records the diagnosis and the agreed target state; the
implementation slices follow in the acceptance criteria.

**Diagnosis (2026-10-19, read-only investigation + reproduction).** Three
distinct causes, not one:

1. **Pre-M9 leftovers.** The M9 session store (commit `8fc3efd`) moved run
   artifacts into `output/sessions/<sha>/`, but the six retired global files
   were only *deleted* by `sessions.py::retire_legacy_files()`, never
   removed from the writes that produced them. The twelve loose files at
   `output/` root are stale leftovers of the pre-M9 layout: SHA-256 hashing
   shows **none** of them matches any session copy, so they are standalone
   orphans, not duplicates.
2. **Live writers that still target the root.** Every stage's output path is
   a *default argument* on a module-level function
   (`implied.py::propose_implied(approvals_path=Path("output/implied_skills.json"))`,
   `gate.py::review_targets(overrides_path=Path("output/gate_overrides.json"))`,
   `resume.py::EXTRACTED_PATH`, `oss.py::OSS_CACHE_PATH`,
   `output.py::write_plan`, `output.py::write_plan_html`). A caller that
   omits the argument writes to `output/` root. `cli.py::_out(state)` still
   has the fallback `Path(state.get("session_dir") or "output")`.
3. **Deliberate sharing.** `output/captured_jds/` is a shared staging area:
   `server.py::_write_captured_jds` wipes and rewrites it,
   `_copy_captured_to_session` mirrors it into the session, and `_find_jd`
   resolves JD names against it.

**Two live defects found during the investigation** (both reproduced, see
"Tests to add / run"):

- **D1 — the retired-global guarantee is not airtight.**
  `implied.py::propose_implied` writes `approvals_path` whenever
  `on_save is None`; `ingest.py::ingest_skills_json` defaults
  `approvals_path=Path("output/implied_skills.json")` and
  `build_seed_graph` forwards no `approvals_path`. The **README's own
  documented quickstart** (`python -m skill_gap_agent.m5_plan --auto`)
  runs this path and recreates the retired global `output/implied_skills.json` in
  a clean directory. `m9_check.py`'s assertion (that the retired globals
  stay gone) covers the flows it exercises, not this one.
  *Reach:* the callers that pass no `implied_on_save` —
  `m5_plan.py:57`, `m3_judge.py:26`, `m26_check.py:316`.
- **D2 — cross-session decision contamination.**
  `propose_implied` *reads*
  `approvals_path` unconditionally, even when `on_save` routes persistence
  into the session profile. So a stale root `output/implied_skills.json`
  is silently applied to a **different** source's session: the user is never
  asked, and the inherited answer is written into the new session's
  `profile.json`. This is the exact failure M9's session store was built to
  make structurally impossible ("Cross-profile misapplication is structurally
  impossible", `13-intake.md` §Session store) — reproduced end to end.
  *Reach (verified):* the **sweep** (the widest vector — `seed_caches()`
  copies root `output/implied_skills.json` into
  `output/sweeps/<id>/_shared/`, which the sweep's ingest then reads),
  and `m3_judge.py` / `m26_check.py` (no `retire_legacy_files()` call).
  The primary CLI and extension paths are **not** affected — they call
  `retire_legacy_files()` first, so the file is gone before the read.
  **Why it stayed invisible:** `retire_legacy_files()` deletes the file at
  the start of every primary run, so the file is normally absent; it is
  created *during* a run and survives on disk until the next run's
  retire call.

## Spec sections this task applies (the HOW lives there)

- [13-intake.md](../13-intake.md) §Session store — artifact placement and the
  target state (design home; the three user decisions are recorded there)
- [02-decisions.md](../02-decisions.md) — the M27 decision rows
- [03-milestones.md](../03-milestones.md) — M27 entry, §Open items
- [01-system-overview.md](../01-system-overview.md) — the `output/` tree map
- [12-extension.md](../12-extension.md) §Run contract — captured JDs and
  `/api/gaps`
- [11-sweep.md](../11-sweep.md) §Output layout — the sweep's cache seeding

## User decisions (2026-10-19, recorded in `13-intake.md` §Session store)

1. **Scope:** diagnosis first; the implementation is this task's job.
2. **`captured_jds/`:** fold into the session (`<session>/captured_jds/`) —
   no shared root staging folder.
3. **Sweep:** seed the sweep's caches from a **session**, not from root
   `output/`.
4. **Existing sessions:** untouched — the 86 existing session folders are
   left exactly as they are.

## Out of scope for this task

- Deleting or rewriting the 86 existing session folders (decision 4)
- The vocabulary bridge wiring (`vocab_bridge.py` stays unwired and
  deferred; only its *default path* is re-pointed)
- Any change to judge scoring, prompts, gate thresholds, or ranking
- The M12 sweep's sampling, metrics, or shared-cache semantics — only where
  it reads a cache from the root changes
- `output/checkpoints.sqlite`, `output/uploads/`, `output/logs/`,
  `output/sweeps/` — these are genuinely root-owned, not session artifacts
- Retro-fitting the 12 stale leftover files in `output/` root (they are
  orphans; removing them is a separate, explicitly-approved cleanup)

## Files to touch (the lock board claims exactly these)

- `src/skill_gap_agent/implied.py` (D1/D2: no default root path; no root read)
- `src/skill_gap_agent/ingest.py` (forward the session approvals path)
- `src/skill_gap_agent/gate.py` (no default root path)
- `src/skill_gap_agent/sessions.py` (session-scoped path helpers; the retired-global list)
- `src/skill_gap_agent/server.py` (write captured JDs into the session; resolve JD names from the session)
- `src/skill_gap_agent/cli.py` (drop the `or "output"` fallback)
- `src/skill_gap_agent/m5_plan.py` (route the implied approvals to the session)
- `src/skill_gap_agent/sweep.py` (seed caches from a session)
- `src/skill_gap_agent/resume.py` (no default root path)
- `src/skill_gap_agent/oss.py` (no default root path)
- `src/skill_gap_agent/output.py` (no default root path)
- `src/skill_gap_agent/vocab_bridge.py` (no default root path)
- `src/skill_gap_agent/m2_check.py`, `src/skill_gap_agent/m3_judge.py`,
  `src/skill_gap_agent/smoke_test.py`, `src/skill_gap_agent/m11_check.py`,
  `src/skill_gap_agent/m13_check.py`, `src/skill_gap_agent/m14_check.py`,
  `src/skill_gap_agent/m15_check.py`, `src/skill_gap_agent/m19_check.py`
  (check harnesses stop writing to the root)
- `src/skill_gap_agent/m7_check.py`, `src/skill_gap_agent/m8_check.py`,
  `src/skill_gap_agent/m9_check.py`, `src/skill_gap_agent/m12_check.py`
  (assertions that pinned the retired/legacy root paths)
- `specs/13-intake.md`, `specs/02-decisions.md`, `specs/03-milestones.md`,
  `specs/01-system-overview.md`, `specs/04-reader.md`, `specs/06-skill-map.md`,
  `specs/07-skill-cleaner.md`, `specs/08-gap-measurer.md`,
  `specs/09-practice-planner.md`, `specs/10-flow-runner.md`,
  `specs/11-sweep.md`, `specs/12-extension.md`
- `specs/tasks/T-M27-artifact-placement.md` (this file)
- `README.md`
- `docs/changelog.md`

## Acceptance criteria (checkable, per-change)

1. **No flow writes a session artifact to `output/` root.** After a clean
   run of the README quickstart (`m5_plan --auto`) and of the `cli.py`
   graph, `output/` root contains **no** `implied_skills.json`,
   `gate_overrides.json`, `graph.json`, `judge_report.json`, `gaps.json`,
   `plan.md`, `plan.html`, `synthesis_report.json`, `oss_issues.json`,
   `extracted_skills.json`, or `extracted_approvals.json`.
2. **D1 closed.** `output/implied_skills.json` is never created by any
   flow. `propose_implied` and `ingest_skills_json` have **no** root default:
   a caller that supplies neither an approvals path nor `on_save` raises
   rather than silently writing to `output/`. Covers `m5_plan.py`,
   `m3_judge.py`, `m26_check.py`.
3. **D2 closed.** A stale root `output/implied_skills.json` is never *read*.
   Given a root global left over from a previous layout, ingesting a second,
   different source asks the user about its implied skills and writes the
   answer into **that** source's session `profile.json` — no answer is
   inherited across sources. In particular the sweep no longer seeds
   `_shared/implied_skills.json` from root `output/`, and `propose_implied`
   does not read a path it is not writing to.
4. **Same input still resumes.** Re-running with the same source reuses the
   session's implied and gate decisions silently (no re-prompting), and
   re-running with a different source starts fresh.
5. **`captured_jds/` folded.** The server writes captured JDs straight into
   `<session>/captured_jds/`; `output/captured_jds/` is no longer created or
   written; `GET /jds/<name>` still resolves extension-run JD links
   (resolution order: the session's folder, then `data/jds/`).
6. **`/api/gaps` and `/plan.html` still serve.** Both read from the session
   dir; the root fallback is removed only once the session copy is proven to
   exist.
7. **Sweep seeds from a session.** `sweep.py` takes the source session
   explicitly; `output/sweeps/<id>/_shared/` keeps its own copies, and the
   sweep no longer reads caches from root `output/`.
8. **Root-owned paths stay root-owned.** `output/checkpoints.sqlite`,
   `output/uploads/`, `output/logs/`, `output/sweeps/` are unchanged.
9. **Check harnesses are clean.** No `m*_check.py` or `smoke_test.py` writes
   to `output/` root; the harnesses that pinned the old root paths
   (`m7_check`, `m8_check`, `m9_check`) assert the new behaviour instead.
10. **Spec + docs match the code.** The `output/` tree in
    `01-system-overview.md`, the per-stage artifact paths, and the README
    "Outputs" list name the session-scoped location, and the M27 rows are
    in `02-decisions.md` / `03-milestones.md` (status flips to Built only
    after the code lands).

## Tests to add / run

- New: a regression check that a run in a clean directory leaves no session
  artifact at `output/` root (extend `m9_check.py` — it already asserts the
  retired globals stay gone, but only for the flows it exercises).
- New: a contamination regression — two different sources, the second must
  be asked about its implied skills even when a root global exists.
- Extend: `m7_check.py`, `m8_check.py`, `m12_check.py` (sweep seeding),
  `m13_check.py` (captured JDs in the session), `m19_check.py`.
- `ruff check .`, `pytest`, and the mN sweep
  (`python -m skill_gap_agent.m2_check --auto`).

## Completion protocol

1. Implement slice by slice, running `python scripts/verify.py --task
   T-M27-artifact-placement` until green.
2. Self-review the diff against the acceptance criteria above (checklist,
   not taste).
3. Flip M27's status to Built in `03-milestones.md`, append any new locked
   decision to `02-decisions.md`, write the changelog line
   (`docs/changelog.md`), mark this done, release locks
   (`python scripts/release.py --task T-M27-artifact-placement`).
