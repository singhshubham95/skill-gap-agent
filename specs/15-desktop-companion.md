# C5 — Desktop Companion & Distribution (M29)

**Status: 🎯 Designed (M29, 2026-10-26).** Slice 29a (desktop launcher) is
built 2026-10-26; 29b (installer/CI) and 29c (panel onboarding) are
implemented and in review — clean-VM, signed-build, and live-panel passes
remain. 29d (docs/store close) is still designed. This file is the
design home for the installed companion program, the Windows installer,
the release pipeline, and the consumer setup journey. The panel-side
onboarding behavior lives in [12-extension.md](12-extension.md) §M29; this
file links to it rather than duplicating it.

## Why this component exists

M28 made the extension the only user surface, but launching it is still
developer-shaped: Python 3.11+, a virtualenv and `pip install`, a console
window from `tools/start-server.bat`, and `chrome://extensions` → **Load
unpacked** (`README.md` §Quickstart). A job seeker cannot be expected to
do any of that.

Chrome cannot remove the companion: an extension cannot execute Python or
native code, and cannot install a native application. Native messaging can
only *start an already installed* host, so it does not remove the install
either. The two-install floor is therefore:

1. the **companion app** (bundled runtime — no system Python), installed
   once;
2. the **extension**, installed once from the Chrome Web Store (which is
   also what removes developer mode).

The no-install alternatives are deliberately not in M29: porting the
pipeline to TypeScript inside the extension (a second implementation) and
hosting the backend (a different privacy/cost model). Native messaging,
automatic companion updates, and non-Windows packaging are deferred —
[03-milestones.md](03-milestones.md) §Deferred #14, #17, #18, #19.

## Consumer setup (target journey)

1. **Download** `SkillGapAgent-Setup.exe` from the project's release page.
2. **Install** — per-user, no administrator prompt; signed build. The
   installer creates the Start Menu shortcut, enables start-at-login, and
   launches the app.
3. **Add the extension** — the installer opens the Chrome Web Store
   listing in the default browser; one click on **Add to Chrome**. The
   tray menu can reopen this page later.
4. **Open the panel** — click the toolbar icon; it auto-connects to
   `http://127.0.0.1:8000` with no configuration. No Python, no console,
   no port setting, no unpacked-extension workflow.
5. **AI access** — click **Create free LLM key** (the existing OpenRouter
   OAuth flow) or paste an existing key; it is stored in the OS keyring as
   today. Rule-based mode remains available.
6. **Resume → capture → analyze → plan** — unchanged from the built
   extension flow.

Subsequent use: the companion starts with Windows and the panel is
connected whenever the app is running. Extension updates arrive through
the Chrome Web Store; companion updates are manual in M29 (a new
installer; see §Updates).

## Companion app

### Entry point and lifecycle

- **Entry point:** `python -m skill_gap_agent.desktop` (module
  `src/skill_gap_agent/desktop.py`). `server.main()` remains the developer
  entry point; both use the same server factory and the same pipeline.
- **Tray UI** (pystray + Pillow), with: status line, **Get the Chrome
  extension** (opens the store listing once the release constant is set;
  before the listing exists it shows a notice), **Open data folder**,
  **Open logs**, **Check for updates** (opens the release page; no
  background check), **Restart agent**, **Start with Windows**
  (checkable), **Quit**.
- **Single instance:** a named OS mutex; a second launch shows an
  informational "already running in the notification area" notice and
  exits instead of starting a second server.
- **Server lifecycle:** the app starts the loopback server and keeps it
  alive; **Quit** stops it cleanly. Dev invocation keeps the console
  output; the frozen build is windowed (no console).
- **Login autostart:** the installer enables it; the tray toggle can turn
  it off/on. Uninstall removes the autostart entry.
- **Failure logging:** unhandled errors and startup failures are written
  to the log folder; the tray shows an actionable notification instead of
  failing silently.

### Network and port

- The server binds **`127.0.0.1:8000`** only. The extension's default URL,
  origin gate, and host permissions are unchanged.
- **Port 8000 occupied:** the app shows an error dialog (or a logged
  message in non-interactive/smoke mode) and writes a log entry, then
  exits. It does **not** silently switch ports — the panel expects 8000.
  Dynamic port selection plus extension discovery is deferred
  ([03-milestones.md](03-milestones.md) §Deferred #19).
- No new inbound surface: no LAN binding, no remote access, no telemetry.
  The M20 origin gate and M21 data-disclosure behavior are unchanged.

### Runtime paths

| Context | Data root | Logs |
|---|---|---|
| Installed (frozen) | `%LOCALAPPDATA%\SkillGapAgent\data` | `%LOCALAPPDATA%\SkillGapAgent\logs` |
| Dev (`python -m …`) | repo `output/` (unchanged) | console; `--debug` file under `output/logs/` |
| Override | `SKILL_GAP_DATA_DIR` wins in both contexts | — |

The data root keeps the exact M28 workspace layout (`current.json`,
`profile.json`, graph/judge/gaps/plan artifacts, `uploads/`,
`captured_jds/`, `saved_sessions/`). **No artifact path changes in M29.**
`SKILL_GAP_DATA_DIR` remains the isolation seam for offline checks. The
app never writes next to the executable or into `Program Files`.

A developer workspace under the repo's `output/` is **not migrated
automatically** into the installed data root; copying the files across is
a manual, supported action because the layout is identical. New users
start empty.

Uninstall keeps user data by default (an opt-in checkbox can delete it);
the panel's **Delete all data** control remains the in-app wipe.

### Version contract

- `/api/status` gains **`app_version`** (the package version, sourced from
  `skill_gap_agent.__version__`; the build checks it matches
  `pyproject.toml`).
- The panel compares `app_version` against a **minimum compatible**
  constant and shows a non-blocking banner if the companion is older or the
  field is missing. A run is never refused for a version mismatch.
- No separate API-version negotiation in M29; a breaking API change must
  bump the minimum-compatible constant as part of that change.

### Security posture

- Loopback-only binding and the existing origin/Content-Type gates remain
  the API boundary; OS-keyring storage of keys is unchanged.
- The installer and binaries are code-signed for release builds (the
  certificate is an owner-provided release gate). Unsigned builds are for
  local testing only and are labeled as such.
- No new data leaves the machine: the companion's LLM/GitHub calls and the
  local-first privacy claims are unchanged by packaging.
- Data lives in the user profile; uninstall removes binaries, shortcuts,
  and autostart, and leaves data unless explicitly deleted.

## Installer and release pipeline

### Frozen build

- **PyInstaller, one-directory build** (not one-file: faster start, fewer
  antivirus false positives), Windows x64, windowed executable with the app
  icon; the desktop extra (`pystray`, `Pillow`) is bundled, tests and dev
  tooling are excluded.
- Package metadata is bundled so `__version__` and runtime metadata agree;
  a build check asserts `pyproject.toml` version == `__version__`.
- The build must be reproducible from a clean checkout on a GitHub-hosted
  Windows runner; no system Python is required on the target machine.

### Installer

- **Inno Setup 6**, per-user: `PrivilegesRequired=lowest`, install into
  `%LOCALAPPDATA%\Programs\SkillGapAgent`, Start Menu shortcut, optional
  desktop shortcut, launch after install, start-at-login entry.
- Uninstaller stops the running companion, removes shortcuts and the
  autostart entry, and keeps user data unless the user opts to delete it.
  Because the tray app has no main window for Restart Manager to close,
  setup and uninstall explicitly stop `SkillGapAgent.exe` before touching
  files; an install over a running app is treated as an update and also
  stops it first.
- Finish step opens the Chrome Web Store listing (a build-time constant;
  see §CI and distribution). The tray menu can reopen it.
- Signing: `signtool` over the app executable, uninstaller, and setup
  executable in CI when signing secrets are configured. The certificate
  purchase is an owner action; unsigned artifacts still build for testing.

### CI and distribution

- New workflow `.github/workflows/windows-release.yml`, triggered by a
  `v*` tag or manual dispatch: run `ruff`, `pytest`, the M29 check and the
  existing regressions, build, sign when possible, write SHA-256
  checksums, and attach the installer + checksums to the GitHub Release.
- The tag must equal the package version; a mismatch fails the build.
- Companion distribution = **GitHub Releases**; extension distribution =
  **Chrome Web Store**. MSIX, winget, and Microsoft Store packaging are
  out of scope for M29.
- Chrome Web Store listing is the **consumer release gate**: until the
  listing is public, the journey still needs developer mode. Submission
  and approval are owner actions tracked in
  [CHROMEWEBSTORE.md](../CHROMEWEBSTORE.md); the code milestone can be
  verified with an unpacked extension, but the no-developer-mode claim is
  only true once the listing is live.

### Updates

- The extension updates automatically through the Chrome Web Store.
- The companion has **no auto-updater** in M29: **Check for updates**
  opens the release page and a new installer runs over the old one,
  preserving the data directory. Version mismatch is visible in the panel.
  Auto-update is deferred ([03-milestones.md](03-milestones.md) §Deferred
  #17).
- Update ordering is tolerant in both directions: an old companion with a
  newer extension produces a warning, never a broken panel.

## Panel onboarding (design home: 12-extension.md §M29)

At a glance: the default agent URL is fixed at `http://127.0.0.1:8000`
with no first-run configuration; the URL field moves under an
advanced/developer block; the offline state says the companion is not
running and offers **Retry** plus a download link instead of `.bat`
instructions; and `app_version` drives the non-blocking update banner.
Mechanics and done criteria live in
[12-extension.md](12-extension.md) §M29.

## Failure modes

| Condition | User-visible behavior |
|---|---|
| Companion not installed / not running | Panel shows the companion-offline state with **Retry** and a **Get the companion** link; no crash, no silent fallback |
| Port 8000 occupied | Error dialog (logged in non-interactive mode) + log entry; app exits; panel remains offline with the same guidance |
| Companion older than extension | Non-blocking panel banner with the release-page link; runs continue |
| Data directory not writable | Tray notification naming the log file; app does not start in a half-broken state |
| Chrome Web Store listing not yet live | Installer finish step cannot open a listing; developer-mode path remains the fallback and is documented as pre-release only |
| User quits the tray app | Panel goes offline with the same guidance; tray can be reopened from the Start Menu |

## Done criteria (M29)

1. **Clean Windows 10/11 x64 VM, two installs:** signed/per-user installer
   (no admin), no console, no system Python; extension from the store (or
   unpacked only while the listing is pending); panel connects without
   configuration; free-key OAuth, resume upload, capture, analyze, and plan
   complete end to end.
2. **Autostart and uninstall:** the companion starts after sign-out/in;
   uninstall stops it, removes shortcuts + autostart, and keeps data by
   default.
3. **Paths:** data and logs live under `%LOCALAPPDATA%\SkillGapAgent\`;
   nothing is written next to the executable; `SKILL_GAP_DATA_DIR` still
   isolates checks.
4. **Version contract:** `/api/status` carries `app_version`; a
   forced-older companion shows the non-blocking panel banner; runs are
   not blocked.
5. **Release artifact:** CI builds on a version tag, signs when secrets
   exist, and publishes the installer + SHA-256 on the GitHub Release.
6. **Docs and register:** README/extension README describe the two-install
   journey first; CHROMEWEBSTORE reviewer instructions match the installer;
   privacy policy names the installed data location and launch method; no
   end-user copy still says `start-server.bat`, `pip install`, or **Load
   unpacked**.
7. **Store gate recorded:** the CWS listing approval and signing
   certificate are listed as owner release gates; the milestone does not
   claim the no-developer-mode journey before the listing is live.

## Out of scope (M29)

- Porting the pipeline to TypeScript, a hosted backend, or a WASM runtime
- Native-messaging auto-launch (tray login autostart covers M29)
- Companion auto-update, MSIX/winget/Microsoft Store packaging
- macOS/Linux installers (Windows 10/11 x64 only in M29)
- Dynamic port selection and extension discovery
- Any change to pipeline stages, API routes, judge scoring, gates, or
  ranking; any redesign of the local dev UI
- Automating Chrome Web Store submission or review

## History

- M13 built the extension shell; M14 added the double-click `.bat` launcher
  and self-serve panel setup; M22 prepared the store register; M28 retired
  the CLI and made the extension the only interface. M29 completes the
  consumer install path.
- Decision rows: [02-decisions.md](02-decisions.md) M29 rows.
- Build order, slices, and verification records:
  [03-milestones.md](03-milestones.md) M29.
