# T-M29-installer-ci: Per-user Windows installer + signed release build

- **Status:** in-review (2026-10-26) — code + local install/update/uninstall
  verified; clean-VM and signed-build gates pending
- **Agent session:** local Qoder Desktop (2026-10-26)
- **Blocked by:** T-M29-desktop-launcher (needs `skill_gap_agent.desktop`)

## Why this task exists

A tray companion that still needs a Python toolchain does not simplify
end-user setup. This slice turns the launcher into a downloadable
`SkillGapAgent-Setup.exe`: bundled runtime, per-user install, shortcuts,
autostart, uninstall, signing hook, and a CI pipeline that produces the
artifact and checksums. Milestone history: [03-milestones.md](../03-milestones.md)
M29; store gate: [CHROMEWEBSTORE.md](../../CHROMEWEBSTORE.md).

## Spec sections this task applies (the HOW lives there)

- [15-desktop-companion.md](../15-desktop-companion.md) §Installer and
  release pipeline — frozen build, installer behavior, signing, CI,
  distribution, updates
- [15-desktop-companion.md](../15-desktop-companion.md) §Failure modes
- [15-desktop-companion.md](../15-desktop-companion.md) §Done criteria
  (M29) items 1–2, 5

## Out of scope for this task

- Launcher code/tray/paths (T-M29-desktop-launcher; consume, do not modify)
- Panel onboarding and version banner (T-M29-panel-onboarding)
- README/landing/privacy/store reviewer copy (T-M29-install-docs)
- Companion auto-update, MSIX/winget/Microsoft Store, macOS/Linux
- Chrome Web Store submission automation; obtaining a signing certificate
  (owner actions — the CI hook must support secrets, not acquire them)
- Any pipeline/API change

## Files to touch (the lock board claims exactly these)

- `packaging/skill-gap-agent.spec` (new — PyInstaller one-dir build)
- `packaging/entrypoint.py` (new — frozen entry point if needed)
- `packaging/installer.iss` (new — Inno Setup per-user installer)
- `packaging/build.ps1` (new — local/CI build, version check, checksums)
- `packaging/make_icon.py` + `packaging/app.ico` (icon asset for exe/setup)
- `packaging/README.md` (new — build/sign/release steps)
- `.github/workflows/windows-release.yml` (new — tag/dispatch build)
- `.gitignore` (build/dist intermediates)
- `THIRD-PARTY-NOTICES.md` (bundled runtime + packaging dependencies)
- `specs/15-desktop-companion.md` (only if implementation reveals a design
  change; status stays Designed until T-M29-install-docs closes M29)
- `specs/tasks/T-M29-installer-ci.md` (this file)
- `docs/changelog.md`

## Acceptance criteria (checkable, per-change)

1. **Build from clean checkout.** On a Windows runner,
   `packaging/build.ps1` (or the CI workflow) produces a windowed
   one-directory app and `SkillGapAgent-Setup.exe`; the app runs with no
   system Python installed, and the frozen build can read/write the OS
   keyring (PyInstaller hidden imports for the Windows keyring backend
   included). The build asserts `pyproject.toml` version ==
   `skill_gap_agent.__version__` == installer version and writes SHA-256
   checksums.
2. **Per-user install.** Inno Setup uses `PrivilegesRequired=lowest`,
   installs under `%LOCALAPPDATA%\Programs\SkillGapAgent`, creates Start
   Menu + optional desktop shortcuts, launches after install, and enables
   start-at-login. No administrator prompt or `Program Files` write.
3. **Uninstall.** The uninstaller stops a running companion, removes
   shortcuts and the autostart entry, and keeps
   `%LOCALAPPDATA%\SkillGapAgent\data` unless the user opts to delete it.
4. **Extension step.** The installer finish step and tray link use the
   Chrome Web Store listing constant; when the constant is unset
   (pre-listing test build), the step is skipped safely and the build
   labels itself pre-release.
5. **Signing + CI.** The workflow triggers on a `v*` tag or manual
   dispatch, runs `ruff`/`pytest`/`m29_check` plus the existing
   regressions, signs the app/uninstaller/setup with `signtool` when
   signing secrets are configured, and otherwise produces a clearly
   labeled unsigned test artifact. Installer + checksums are attached to a
   GitHub Release; a tag/version mismatch fails the run.
6. **Licenses + notices.** The bundled runtime, `pystray`, `Pillow`, and
   PyInstaller bootloader licenses are reflected in
   `THIRD-PARTY-NOTICES.md`; the notices file ships with the app/installer.
7. **Clean VM pass.** Install → launch (no console) → panel connects →
   sign-out/in autostart → uninstall → data preserved. Record the exact
   Windows version and observed behavior for T-M29-install-docs.

## Verification (2026-10-26)

- `python scripts/verify.py --task T-M29-installer-ci` ALL CHECKS PASS
  (`ruff`, pytest 67, m29/m13/m18/m20/m22/m26); report:
  `board/verify-T-M29-installer-ci.md`.
- Frozen build: PyInstaller 6.22.3 one-directory, windowed (PE GUI
  subsystem); `dist\SkillGapAgent\SkillGapAgent.exe` served
  `/api/status` with `app_version=0.1.0`, logged to
  `%LOCALAPPDATA%\SkillGapAgent\logs\desktop.log`, started a tray icon, and
  exited 0 through the smoke/Quit path with no system Python.
- Installer: Inno Setup 6.7.3 per-user silent install under
  `%LOCALAPPDATA%\Programs\SkillGapAgent` (no admin), Start Menu shortcut +
  HKCU Run autostart, installed-app smoke passed, checksum matches. The
  `OpenStore=1` compile branch was exercised with a placeholder URL.
- Update/uninstall while running: `InitializeSetup` / `InitializeUninstall`
  stop the tray app (no main window for Restart Manager); reinstalling over
  a running app and silent uninstall while running both returned 0, killed
  the app, removed files/shortcut/autostart, and preserved the data marker
  (silent uninstall keeps data).
- **Pending:** a clean Windows 10/11 x64 VM pass and a signed-build check
  (this host has no signing certificate/signtool; the artifact here is
  explicitly unsigned). These are tracked in `03-milestones.md` §Open and
  must be recorded before 29d closes M29.

## Tests to add / run

- CI build on a Windows runner; checksum verification
- `ruff check .`, `pytest`, `python -m skill_gap_agent.m29_check`
- `node --check extension/sidepanel.js` (regression only; no JS edits)
- Clean Windows 10/11 x64 VM interactive pass (install/autostart/
  uninstall); note results in the task completion

## Completion protocol

1. Implement, run `python scripts/verify.py --task T-M29-installer-ci`
   until green; attach the CI run/artifact link to the task.
2. Self-review the installer/CI diff against the acceptance criteria;
   confirm no launcher/panel/API edits crept into scope.
3. Do **not** flip M29 / C5 status — T-M29-install-docs closes the
   milestone. Write the changelog line, mark this task done, release
   locks.
