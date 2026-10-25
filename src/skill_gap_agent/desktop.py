"""M29 desktop companion: tray lifecycle around the local agent server.

The extension remains a thin client; this module is the installed entry point
that starts the same loopback API server without a console, keeps it alive from
a tray icon, and owns the runtime data/log paths. Design:
specs/15-desktop-companion.md §Companion app.

Dev: run `python -m skill_gap_agent.desktop` (requires the `desktop` extra:
`pip install -e ".[desktop]"`). A hidden `--smoke-seconds N` starts the tray,
auto-quits through the same shutdown path, and is used for verification.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
import traceback
import webbrowser
from dataclasses import dataclass
from pathlib import Path

from . import __version__ as APP_VERSION

APP_TITLE = "Skill-Gap Agent"
APP_DIR_NAME = "SkillGapAgent"
DEFAULT_PORT = 8000
DATA_DIR_ENV = "SKILL_GAP_DATA_DIR"
REPO_ROOT = Path(__file__).resolve().parents[2]
# The companion's release page (the installer also opens this). The Chrome
# Web Store listing is a release gate; fill STORE_URL once it is public.
RELEASES_URL = "https://github.com/singhshubham95/skill-gap-agent/releases/latest"
STORE_URL = ""
SINGLE_INSTANCE_NAME = "Local\\SkillGapAgent.Desktop"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "SkillGapAgent"
ERROR_ALREADY_EXISTS = 183


@dataclass(frozen=True)
class RuntimePaths:
    data_root: Path
    log_dir: Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_version() -> str:
    return APP_VERSION


def _user_base() -> Path:
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local"
        )
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(
            Path.home() / ".local" / "share"
        )
    return Path(base) / APP_DIR_NAME


def resolve_runtime_paths(frozen: bool | None = None) -> RuntimePaths:
    """Installed: LocalAppData; dev: repo output/; env override wins."""
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        data = Path(override)
        return RuntimePaths(data, data / "logs")
    if frozen is None:
        frozen = is_frozen()
    if frozen:
        base = _user_base()
        return RuntimePaths(base / "data", base / "logs")
    data = REPO_ROOT / "output"
    return RuntimePaths(data, data / "logs")


def ensure_runtime_paths(paths: RuntimePaths) -> None:
    paths.data_root.mkdir(parents=True, exist_ok=True)
    paths.log_dir.mkdir(parents=True, exist_ok=True)


def redirect_output(log_dir: Path) -> Path:
    """Windowed builds have no stdout/stderr; send prints to one local file."""
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "desktop.log"
    # This handle *is* the process's stdout/stderr for its whole lifetime.
    handle = open(path, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = handle
    sys.stderr = handle
    return path


def _log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    stream = sys.stderr or sys.stdout
    if stream is None:
        return
    try:
        print(f"[desktop {stamp}] {message}", file=stream, flush=True)
    except Exception:  # noqa: BLE001, S110 — logging must never take the app down
        pass


def _windows_dialog(text: str, *, error: bool) -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        flags = 0x10 if error else 0x40  # MB_ICONERROR / MB_ICONINFORMATION
        ctypes.windll.user32.MessageBoxW(None, text, APP_TITLE, flags)
    except Exception:  # noqa: BLE001, S110 — a missing dialog must not mask the log
        pass


def show_message(text: str, *, error: bool = False, dialog: bool = True) -> None:
    _log(("ERROR: " if error else "") + text)
    if dialog:
        _windows_dialog(text, error=error)


def _open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.as_uri())


def _open_url(url: str) -> None:
    if not webbrowser.open(url):
        _log(f"could not open URL: {url}")


# --- start with Windows ------------------------------------------------------


def startup_command(frozen: bool | None = None) -> str:
    if frozen is None:
        frozen = is_frozen()
    exe = f'"{Path(sys.executable)}"'
    return exe if frozen else f"{exe} -m skill_gap_agent.desktop"


def startup_enabled(
    *, key_path: str = RUN_KEY, value_name: str = RUN_VALUE
) -> bool:
    if os.name != "nt":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except OSError:
        return False
    return bool(value)


def set_startup(
    enabled: bool, *, key_path: str = RUN_KEY, value_name: str = RUN_VALUE
) -> None:
    if os.name != "nt":
        raise OSError("Start with Windows is supported on Windows only")
    import winreg

    if enabled:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(
                key, value_name, 0, winreg.REG_SZ, startup_command()
            )
        return
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, value_name)
    except FileNotFoundError:
        pass


# --- single instance ---------------------------------------------------------


class SingleInstance:
    def __init__(self, name: str = SINGLE_INSTANCE_NAME) -> None:
        self.name = name
        self._handle: object | None = None

    def acquire(self) -> bool:
        if os.name != "nt":
            return True
        if self._handle is not None:
            return True
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [
            wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR
        ]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel32.CreateMutexW(None, False, self.name)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle(self._handle)
        self._handle = None


# --- embedded server ---------------------------------------------------------


class Backend:
    def __init__(self, port: int = DEFAULT_PORT) -> None:
        self._port = port
        self._srv = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        if self._srv is None:
            return self._port
        return int(self._srv.server_address[1])

    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self._srv is not None:
            if self.running():
                return
            try:
                self._srv.server_close()
            finally:
                self._srv = None
                self._thread = None
        from . import server

        srv = server.create_server(self._port)
        srv.daemon_threads = True
        thread = threading.Thread(
            target=self._serve,
            args=(srv,),
            name="skill-gap-backend",
            daemon=True,
        )
        try:
            thread.start()
        except Exception:
            srv.server_close()
            raise
        self._srv, self._thread = srv, thread
        _log(f"local agent listening on http://127.0.0.1:{self.port}/")

    def _serve(self, srv) -> None:
        try:
            srv.serve_forever()
        except Exception:  # noqa: BLE001 — log instead of dying silently
            _log("local agent stopped unexpectedly:\n" + traceback.format_exc())

    def stop(self) -> None:
        srv, thread = self._srv, self._thread
        if srv is None and thread is None:
            return
        self._srv = None
        self._thread = None
        if srv is not None:
            try:
                if thread is not None and thread.is_alive():
                    srv.shutdown()
            finally:
                srv.server_close()
        if thread is not None:
            thread.join(timeout=5)
            if thread.is_alive():
                _log("local agent thread did not exit within 5s")
        _log("local agent stopped")

    def restart(self) -> None:
        self.stop()
        self.start()


# --- tray --------------------------------------------------------------------


def _tray_image():
    from PIL import Image, ImageDraw

    candidates: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates += [
            Path(meipass) / "icons" / "icon128.png",
            Path(meipass) / "extension" / "icons" / "icon128.png",
        ]
    candidates.append(Path(sys.executable).parent / "icons" / "icon128.png")
    candidates.append(REPO_ROOT / "extension" / "icons" / "icon128.png")
    for candidate in candidates:
        try:
            if candidate.is_file():
                with Image.open(candidate) as image:
                    return image.convert("RGBA")
        except Exception:  # noqa: BLE001, S112 — try the next icon location
            continue
    image = Image.new("RGBA", (64, 64), (37, 99, 235, 255))
    draw = ImageDraw.Draw(image)
    draw.ellipse((6, 6, 58, 58), fill=(255, 255, 255, 255))
    draw.text((22, 18), "SG", fill=(37, 99, 235, 255))
    return image


def _build_tray(backend: Backend, paths: RuntimePaths):
    import pystray

    def open_data(icon, item):
        try:
            _open_path(paths.data_root)
        except OSError as exc:
            icon.notify(f"Could not open the data folder: {exc}", APP_TITLE)

    def open_logs(icon, item):
        try:
            _open_path(paths.log_dir)
        except OSError as exc:
            icon.notify(f"Could not open the log folder: {exc}", APP_TITLE)

    def open_store(icon, item):
        if not STORE_URL:
            icon.notify(
                "The Chrome Web Store listing isn't live yet.", APP_TITLE
            )
            return
        _open_url(STORE_URL)

    def open_updates(icon, item):
        _open_url(RELEASES_URL)

    def toggle_startup(icon, item):
        try:
            set_startup(not startup_enabled())
            icon.update_menu()
        except Exception as exc:  # noqa: BLE001 — registry failures are visible
            icon.notify(f"Could not update Start with Windows: {exc}", APP_TITLE)

    def restart(icon, item):
        try:
            backend.restart()
            icon.notify("Local agent restarted.", APP_TITLE)
        except Exception as exc:  # noqa: BLE001 — keep the tray alive
            icon.notify(f"Could not restart the local agent: {exc}", APP_TITLE)

    def quit_app(icon, item):
        backend.stop()
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            f"{APP_TITLE} {APP_VERSION} — running",
            lambda icon, item: None,
            enabled=False,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Get the Chrome extension", open_store),
        pystray.MenuItem("Open data folder", open_data),
        pystray.MenuItem("Open logs", open_logs),
        pystray.MenuItem("Check for updates", open_updates),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Start with Windows",
            toggle_startup,
            checked=lambda item: startup_enabled(),
            enabled=os.name == "nt",
        ),
        pystray.MenuItem("Restart agent", restart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit", quit_app),
    )
    icon = pystray.Icon("skill-gap-agent", _tray_image(), APP_TITLE, menu)
    return icon, quit_app


def _run_tray(icon, quit_app, smoke_seconds: float = 0.0) -> None:
    def setup(icon):
        icon.visible = True
        _log("tray icon ready")
        if smoke_seconds > 0:
            timer = threading.Timer(smoke_seconds, lambda: quit_app(icon, None))
            timer.daemon = True
            timer.start()

    icon.run(setup=setup)


# --- entry point -------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m skill_gap_agent.desktop",
        description="Skill-Gap Agent desktop companion (M29)",
    )
    parser.add_argument(
        "--smoke-seconds",
        type=float,
        default=0.0,
        help=argparse.SUPPRESS,
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    smoke = args.smoke_seconds > 0
    paths = resolve_runtime_paths()
    try:
        ensure_runtime_paths(paths)
    except OSError as exc:
        show_message(
            f"Could not create the data/log folders ({paths.data_root}, "
            f"{paths.log_dir}): {exc}",
            error=True,
            dialog=not smoke,
        )
        return 2

    if is_frozen() or sys.stdout is None or sys.stderr is None:
        try:
            log_path = redirect_output(paths.log_dir)
        except OSError as exc:
            show_message(
                f"Could not open the desktop log file in {paths.log_dir}: {exc}",
                error=True,
                dialog=not smoke,
            )
            return 2
        _log(f"log file: {log_path}")

    _log(
        f"starting {APP_TITLE} {APP_VERSION}; data={paths.data_root}; "
        f"port={DEFAULT_PORT}"
    )
    instance = SingleInstance()
    try:
        acquired = instance.acquire()
    except Exception as exc:  # noqa: BLE001 — show the real startup failure
        show_message(
            f"Could not create the single-instance guard: {exc}",
            error=True,
            dialog=not smoke,
        )
        return 2
    if not acquired:
        show_message(
            f"{APP_TITLE} is already running. Look for its icon in the "
            "notification area.",
            dialog=not smoke,
        )
        return 0

    backend = Backend(DEFAULT_PORT)
    try:
        os.environ[DATA_DIR_ENV] = str(paths.data_root)
        from . import server

        restored = server.prepare_workspace()
        if restored:
            _log(f"resume restored: {restored.get('filename')}")
        backend.start()
    except Exception as exc:  # noqa: BLE001 — startup errors are user-facing
        _log("startup failed:\n" + traceback.format_exc())
        show_message(
            f"Could not start the local agent on port {DEFAULT_PORT}: {exc}",
            error=True,
            dialog=not smoke,
        )
        backend.stop()
        instance.release()
        return 2

    try:
        icon, quit_app = _build_tray(backend, paths)
        _run_tray(icon, quit_app, args.smoke_seconds)
    except Exception as exc:  # noqa: BLE001 — tray dependency/runtime failure
        _log("tray failure:\n" + traceback.format_exc())
        show_message(
            f"Could not start the tray icon: {exc}. Install the desktop "
            'extra with: pip install -e ".[desktop]"',
            error=True,
            dialog=not smoke,
        )
        return 2
    finally:
        backend.stop()
        instance.release()
        _log("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
