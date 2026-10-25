# Packaging — M29 Windows companion + installer

Design: [../specs/15-desktop-companion.md](../specs/15-desktop-companion.md)
§Installer and release pipeline.

## Prerequisites

- Windows 10/11 x64
- Python 3.11+ with the project installed:
  `pip install -e ".[dev,desktop]" pyinstaller`
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) (only for the installer;
  `winget install JRSoftware.InnoSetup`). Use `-SkipInstaller` for an
  exe-only test build.

The Inno Setup compiler prints "Non-commercial use only" for its bundled
preprocessor (ISPP); this project is distributed free. Review ISPP licensing
before any commercial distribution.

## Local build

```powershell
.\packaging\build.ps1
```

Artifacts:

- `dist\SkillGapAgent\SkillGapAgent.exe` — frozen, windowed companion
- `dist\SkillGapAgent-Setup.exe` — per-user installer
- `dist\SkillGapAgent-Setup.exe.sha256` — SHA-256 checksum

The script asserts `pyproject.toml` version == `skill_gap_agent.__version__`
and generates `packaging\app.ico` from the extension icon when missing.
`-SkipInstaller` builds only the frozen app; `-SkipSign` produces a clearly
labeled unsigned test build.

## Signing (release builds)

Set:

- `SKILL_GAP_SIGN_PFX` — path to a `.pfx` certificate
- `SKILL_GAP_SIGN_PASSWORD` — its password
- `SKILL_GAP_SIGNTOOL` — optional explicit `signtool.exe` path

The script signs the companion executable before freezing the installer and
passes Inno Setup a `/Sskillgap` command so the setup executable and
uninstaller are signed too. A certificate is an owner release gate; without
one, the artifact is test-only and Windows SmartScreen will warn.

## Store URL

`SKILL_GAP_STORE_URL` (or `-StoreUrl`) embeds the Chrome Web Store listing in
the installer's finish step. Leave it empty until the listing is approved;
the installer then simply omits that step. The extension itself is published
separately through the Chrome Web Store.

## CI

`.github/workflows/windows-release.yml` runs on a `v*` tag or manual
dispatch. It installs dependencies + Inno Setup, runs the tests/checks,
builds, signs when secrets are configured, uploads the artifact, and (on a
tag) attaches the installer + checksum to the GitHub Release. The tag must
match the package version. Signing secrets are read as
`SKILL_GAP_SIGN_PFX_BASE64` + `SKILL_GAP_SIGN_PASSWORD`; the store URL is the
repository variable `SKILL_GAP_STORE_URL`.

## Clean-machine check (before public release)

1. Install from `SkillGapAgent-Setup.exe` as a normal user (no admin) on a
   Windows 10/11 x64 VM with no Python installed.
2. Confirm no console window, tray icon appears, and
   `http://127.0.0.1:8000/api/status` returns `app_version`.
3. Sign out/in and confirm the companion starts.
4. (Live listing) Add the extension, create a free key, upload a resume,
   capture a JD, analyze, generate a plan.
5. Uninstall: the app stops, shortcuts/autostart are removed, and
   `%LOCALAPPDATA%\SkillGapAgent\data` is kept unless the uninstall prompt is
   accepted.

## Updates

No companion auto-updater in M29. A new installer runs over the old one and
preserves `%LOCALAPPDATA%\SkillGapAgent\data`; the panel warns on a version
mismatch. Chrome Web Store updates the extension automatically.
