# T-M29-desktop-launcher: Tray companion lifecycle + runtime paths + versioned status

- **Status:** done (2026-10-26)
- **Agent session:** local Qoder Desktop (2026-10-26)
- **Blocked by:** none

## Why this task exists

The end-user install path needs a companion process that owns the local
agent without a console or system Python. This slice provides that process
and the runtime contract the installer and panel consume: tray lifecycle,
single instance, writable data/log roots, start-at-login toggle, and the
`app_version` field in `/api/status`. Milestone history and user decision:
[03-milestones.md](../03-milestones.md) M29.

## Spec sections this task applies (the HOW lives there)

- [15-desktop-companion.md](../15-desktop-companion.md) §Companion app —
  entry point, lifecycle, network/port, runtime paths, version contract
- [15-desktop-companion.md](../15-desktop-companion.md) §Failure modes
- [12-extension.md](../12-extension.md) §M29 — the panel consumes the
  version field; this task does not change panel code

## Out of scope for this task

- Packaging, PyInstaller spec, installer, signing, CI (T-M29-installer-ci)
- Panel copy/UI and version banner (T-M29-panel-onboarding)
- README/privacy/store registers (T-M29-install-docs)
- Auto-update, native messaging, dynamic ports, macOS/Linux
- Any change to pipeline stages, endpoints beyond the additive
  `app_version` field, judge/gate/ranking behavior, or keyring storage

## Files to touch (the lock board claims exactly these)

- `src/skill_gap_agent/desktop.py` (new — tray entry point + lifecycle)
- `src/skill_gap_agent/server.py` (reusable server factory/startup seam;
  additive `app_version` in `/api/status`; log-dir handling for the
  packaged app)
- `src/skill_gap_agent/m29_check.py` (new — offline launcher checks)
- `src/skill_gap_agent/test_m29.py` (new — pytest wrapper)
- `pyproject.toml` (desktop extra: `pystray`, `Pillow`; entry point if
  needed by the frozen build)
- `specs/15-desktop-companion.md` (only if implementation reveals a design
  change; status stays Designed until T-M29-install-docs closes M29)
- `specs/tasks/T-M29-desktop-launcher.md` (this file)
- `docs/changelog.md`

## Acceptance criteria (checkable, per-change)

1. **Tray lifecycle.** `python -m skill_gap_agent.desktop` (with the
   desktop extra) starts the existing loopback server and a tray icon;
   **Quit** stops the server and exits; **Restart agent** restarts it; a
   second launch does not create a second server. The frozen build is
   windowed; dev invocation keeps console output.
2. **Single instance + port.** A named single-instance guard prevents a
   duplicate process. With port 8000 already occupied, the app writes a
   log entry and shows an actionable notification, then exits — it never
   selects another port silently.
3. **Paths.** In a frozen context the data root is
   `%LOCALAPPDATA%\SkillGapAgent\data` and logs are
   `%LOCALAPPDATA%\SkillGapAgent\logs`; in dev the repo `output/` is used;
   `SKILL_GAP_DATA_DIR` overrides both. No runtime path is resolved
   relative to the executable's install directory. The M28 workspace
   layout inside the data root is unchanged.
4. **Version.** `/api/status` adds a non-empty `app_version` equal to
   `skill_gap_agent.__version__`, with all existing status fields and
   behavior unchanged. A small helper exposes the version for both dev
   and frozen runs (no reliance on an absent dist-info). The dev
   `server.main()` entry point keeps its existing flags, banner, and
   normal-mode output byte-stable (m26 assertions).
5. **Tray actions.** Open data folder, open logs, get the Chrome extension
   (release constant), check for updates (release page; no background
   network check), and a checkable **Start with Windows** registry toggle
   are wired; failures surface as notifications/log lines, not silent
   exceptions.
6. **No security/privacy change.** The server still binds loopback only;
   the M20 origin gate and keyring behavior are untouched; no telemetry or
   new network calls are introduced.
7. **Checks.** `m29_check.py` verifies path resolution (frozen/dev/env
   override), version/status, and the no-writes-next-to-exe rule without
   importing GUI libraries at module import time. A live tray pass (start,
   second launch, port-conflict, quit, autostart toggle) is recorded.

## Tests to add / run

- New `python -m skill_gap_agent.m29_check`
- New `src/skill_gap_agent/test_m29.py` wrappers for the side-effect-free
  checks
- `ruff check .`, `pytest`
- Existing m13 + m26 regressions (server contract/debug behavior)
- One interactive tray lifecycle pass on Windows; note the result in the
  task completion (T-M29-install-docs copies it into M29's record)

## Verification (2026-10-26)

- `python scripts/verify.py --task T-M29-desktop-launcher` ALL CHECKS PASS
  (`ruff`, pytest 67, `m29_check`, `m13_check`, `m26_check`); report:
  `board/verify-T-M29-desktop-launcher.md`.
- Live tray smoke: `python -m skill_gap_agent.desktop --smoke-seconds 6`
  served `/api/status` with `app_version=0.1.0`, logged `tray icon ready`,
  and exited 0 through the Quit path; a second launch exited 0 with the
  already-running notice; holding port 8000 made the app exit 2 with the
  port-conflict message.
- Autostart write/read/remove was exercised by `m29_check` under a
  throwaway HKCU key; the machine's real Run key was not touched.
- The frozen (windowed, LocalAppData) build itself is T-M29-installer-ci;
  this task verifies the frozen path/redirect logic headlessly.

## Completion protocol

1. Implement, run `python scripts/verify.py --task T-M29-desktop-launcher`
   until green.
2. Self-review the diff against the acceptance criteria (checklist, not
   taste); confirm no pipeline/API behavior changed beyond `app_version`.
3. Do **not** flip M29 / C5 status — T-M29-install-docs closes the
   milestone. Write the changelog line, mark this task done, release
   locks.
