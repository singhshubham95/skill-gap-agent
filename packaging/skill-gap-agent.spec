# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-directory build for the M29 companion.

Run through packaging/build.ps1 so the version/icon checks and installer
step happen in order. Design: specs/15-desktop-companion.md §Frozen build.
"""

from pathlib import Path

repo = Path(SPECPATH).resolve().parent  # noqa: F821 — PyInstaller defines SPECPATH
icon = repo / "packaging" / "app.ico"

datas = [
    (str(repo / "extension" / "icons" / "icon128.png"), "icons"),
    (str(repo / "LICENSE"), "."),
    (str(repo / "THIRD-PARTY-NOTICES.md"), "."),
]

# Keyring selects its backend through entry points, and pystray selects its
# platform backend at import time — PyInstaller cannot see either statically.
hiddenimports = [
    "keyring.backends.Windows",
    "win32ctypes.pywin32.win32cred",
    "pystray._win32",
]

a = Analysis(  # noqa: F821 — injected by PyInstaller
    [str(repo / "packaging" / "entrypoint.py")],
    pathex=[str(repo / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "_pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SkillGapAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon),
)
coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SkillGapAgent",
)
