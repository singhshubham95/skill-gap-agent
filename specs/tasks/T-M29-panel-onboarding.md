# T-M29-panel-onboarding: Companion-aware panel — auto-connect, offline guidance, version banner

- **Status:** in-review (2026-10-26) — automated checks green; live panel
  pass pending
- **Agent session:** local Qoder Desktop (2026-10-26)
- **Blocked by:** T-M29-desktop-launcher (the `app_version` status field
  must exist for live verification)

## Why this task exists

With the companion installed, the panel must stop looking like a developer
tool: no port setup, no `.bat` instructions, and a visible but
non-blocking warning when the manually-updated companion is older than the
Web-Store-updated extension. Milestone history:
[03-milestones.md](../03-milestones.md) M29.

## Spec sections this task applies (the HOW lives there)

- [12-extension.md](../12-extension.md) §M29 — connection assumptions,
  offline state, version handshake, done criteria
- [15-desktop-companion.md](../15-desktop-companion.md) §Version contract,
  §Distribution (URLs/update ordering)
- [12-extension.md](../12-extension.md) §M18 (healthy connection stays
  silent), §M20 (server URL validation) — preserved behavior

## Out of scope for this task

- Launcher/tray/data paths/status implementation
  (T-M29-desktop-launcher; consume the additive field)
- Installer/CI (T-M29-installer-ci)
- README/landing/privacy/store register copy (T-M29-install-docs)
- New permissions, new endpoints, host-permission changes, or any
  pipeline/key/consent behavior
- Redesigning the panel outside the connection/offline/version surfaces

## Files to touch (the lock board claims exactly these)

- `extension/sidepanel.js` (connection, offline copy, version banner,
  advanced URL block behavior, release-page constant)
- `extension/sidepanel.html` (settings grouping/labels, banner/offline
  controls)
- `extension/sidepanel.css` (banner/offline presentation consistent with
  M18/M19)
- `src/skill_gap_agent/m13_check.py` (static assertions for the new
  panel contract)
- `src/skill_gap_agent/m18_check.py` (DOM probe: version handshake
  comparison + banner states)
- `specs/12-extension.md` (only if implementation reveals a design change;
  status stays Designed until T-M29-install-docs closes M29)
- `specs/tasks/T-M29-panel-onboarding.md` (this file)
- `docs/changelog.md`

## Acceptance criteria (checkable, per-change)

1. **Auto-connect.** With no stored URL, the panel uses
   `http://127.0.0.1:8000` and connects on first open; Settings is not
   needed. A stored developer override is still honored and normalized
   (M20 assertions unchanged).
2. **Advanced grouping.** **Local agent URL** is inside a closed
   advanced/developer block; the hint no longer instructs users to edit
   manifest host permissions. Top-gap and existing settings controls stay
   available.
3. **Offline guidance.** Every offline path (initial check, failed run,
   polling) shows: "Skill-Gap Agent isn't running. Open it from the Start
   menu, then choose Retry." with **Retry** and a **Get the companion**
   release link. No `start-server.bat` or `python -m` copy remains in
   end-user panel strings.
4. **Version handshake.** `app_version` is read from `/api/status`; a
   missing/older value than `MIN_COMPANION_VERSION` shows the
   non-blocking "companion is older" banner with the release link; equal
   or newer shows no banner. The banner never disables a control and never
   blocks a run.
5. **Unchanged flows.** Setup order (AI access → resume), consent/key
   handling, capture/list, analyze, plan iframe/reopen, theming, and the
   healthy-connection silence are unchanged.
6. **Checks.** `m13_check.py` asserts the auto-connect/default, the
   advanced grouping, the offline copy/Retry/link, and the version
   handshake wiring. `node --check` is clean; m18/m20 stay green.
7. **Live pass.** Against the installed companion: first-run connect + a
   run; then a forced older `app_version` stub shows the banner while a
   run still starts. Record the result for T-M29-install-docs.

## Verification (2026-10-26)

- `python scripts/verify.py --task T-M29-panel-onboarding` ALL CHECKS PASS
  (`ruff`, pytest 67, m13/m18/m20/m29, `node --check` both JS files);
  report: `board/verify-T-M29-panel-onboarding.md`.
- Static contract (`m13_check`): auto-connect default, advanced-only URL
  block, offline copy + Retry + release link, version banner wiring, both
  links using the release constant, and no `.bat`/`python -m` end-user
  copy.
- DOM probe (`m18_check`): old → banner shown, current/newer → hidden,
  missing → shown; the existing key/mode probes stay green.
- **Pending:** one live side-panel pass against the installed companion,
  including a forced older `app_version` (banner visible, run still
  starts). Tracked in `03-milestones.md` §Open; 29d closes only after it is
  recorded.

## Tests to add / run

- Extend `python -m skill_gap_agent.m13_check` (static panel assertions)
- Extend `python -m skill_gap_agent.m18_check` (version-banner probe)
- `node --check extension/sidepanel.js`
- `python -m skill_gap_agent.m20_check` regression
- `ruff check .`, `pytest`
- One live panel pass with the installed companion + forced version
  mismatch

## Completion protocol

1. Implement, run `python scripts/verify.py --task T-M29-panel-onboarding`
   until green.
2. Self-review the diff against the acceptance criteria; confirm no new
   permissions or API changes.
3. Do **not** flip M29 / C2 status — T-M29-install-docs closes the
   milestone. Write the changelog line, mark this task done, release
   locks.
