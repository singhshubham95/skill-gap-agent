# T-M15-fix-cache: Honest judge cache (skip semantics) + debug log file + Fresh analysis

- **Status:** done 2026-10-18 — `python scripts/verify.py --task
  T-M15-fix-cache` ALL CHECKS PASS (`board/verify-T-M15-fix-cache.md`;
  ruff clean, pytest 59 passed); `m15_check`/`m9_check`/`m26_check` PASS
  and the full mN sweep is green. One live extension re-test stays the
  human's step (03-milestones.md §Open).
- **Origin:** live extension debugging session 2026-10-18 — every gap row
  labeled `LLM (cached)` despite 15 fresh judge LLM calls in the same run;
  debug console scrollback truncated the run's start (the M26 restore
  trigger fired).

## Spec sections this task applies (the HOW lives there)

- [12-extension.md](../12-extension.md) §Judge cache reuse for
  re-analysis (`reuse_judged`) — skip semantics + edge lifecycle (design
  home)
- [12-extension.md](../12-extension.md) §Fresh analysis (clear LLM
  caches) — new: button + endpoint contract
- [14-observability.md](../14-observability.md) §Local debug mode —
  log-file mirror (restore-triggered amendment of the recorded non-goal)
- [13-intake.md](../13-intake.md) §Depth-aware judge — stamp rule, linked
  only (unchanged)
- [05-ai-caller.md](../05-ai-caller.md) §LLM presence policy —
  provenance vocabulary, linked only (unchanged)

## Out of scope for this task

- Any change to judge scoring, prompts, or the M12 purity assumption
- CLI default semantics (stays fresh-judging; `reuse_judged` remains the
  extension's flag)
- Log rotation, network log export, `--debug` on `cli.py`/`sweep.py`
- Re-generating validation questions beyond deleting the question cache
- Anything about LangSmith / M17 tracing (untouched)

## Files to touch (the lock board claims exactly these)

- `src/skill_gap_agent/graph.py` (fresh edges write `cached: False`)
- `src/skill_gap_agent/cli.py` (reuse skips judged targets; reuse result
  reports stale targets)
- `src/skill_gap_agent/sessions.py` (`clear_judgment_cache`)
- `src/skill_gap_agent/server.py` (`POST /api/session/clear-cache`;
  debug log-file wiring)
- `src/skill_gap_agent/debuglog.py` (file mirror, path at startup)
- `src/skill_gap_agent/m9_check.py` (adapt to the reuse-result return)
- `src/skill_gap_agent/m15_check.py` (cache-skip + label + clear-cache
  assertions)
- `src/skill_gap_agent/m26_check.py` (log-file mirror assertion)
- `extension/sidepanel.js`, `extension/sidepanel.html`,
  `extension/sidepanel.css` (Fresh analysis button + feedback)
- `specs/12-extension.md`, `specs/14-observability.md`,
  `specs/02-decisions.md`, `specs/03-milestones.md`,
  `specs/tasks/T-M15-fix-cache.md` (this file)
- `docs/changelog.md`
- `board/` (always allowed)

## Acceptance criteria (checkable, per-change)

1. Under `reuse_judged`, a target with ≥1 reusable stamped edge and no
   stale-stamped edge is **not sent to the LLM**; its row renders
   `LLM (cached)`. A target whose edges were refused (stale depth stamp)
   or that has none is judged fresh and its row renders `LLM`.
2. A freshly judged pair never carries `cached: True` — the flag is
   written explicitly at both edge write sites (copy → True, judge →
   False). No judgment is ever mislabeled as reused or vice versa.
3. `POST /api/session/clear-cache` (JSON) removes exactly
   `graph.json`, `judge_report.json`, `questions.json` from its target
   session (same skills-input precedence as a run: body `skills_path` →
   uploaded resume → server default); `profile.json`, `captured_jds/` and
   extraction artifacts survive; the response lists what was removed.
   Origin gate + JSON Content-Type enforcement apply.
4. The panel's **Fresh analysis** control confirms, calls the endpoint
   (single-flight), and reports the cleared files or the error inline.
5. `--debug` (and `--debug-payloads`) mirror every log line to
   `output/logs/server-<start timestamp>.log` and print the path at
   startup; the console output is unchanged; normal mode stays
   byte-stable; `debuglog.py` still imports no network/`langsmith`
   module.
6. `m15_check.py` / `m26_check.py` assert 1–5 offline (stubbed LLM, no
   network) and run from `main()`; `ruff check .` and `pytest` clean.

## Tests to add / run

- `m15_check.py`: cache-skip semantics, fresh-flag clearing, `clear_judgment_cache`
- `m26_check.py`: log-file mirror
- `m9_check.py`: reuse-result return adaptation
- `ruff check .`, `pytest`, the mN sweep (`m2_check --auto`)

## Completion protocol

1. Implement, run `python scripts/verify.py --task T-M15-fix-cache`
   (checks: `ruff check .,pytest`) until green.
2. Self-review the diff against the acceptance criteria (checklist).
3. Changelog line + milestone/decision register updates, mark done,
   release locks (`python scripts/release.py --task T-M15-fix-cache`).
