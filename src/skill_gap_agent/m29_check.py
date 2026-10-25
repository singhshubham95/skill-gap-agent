"""M29 verification: desktop launcher, paths, version, and embedded backend.

Offline (localhost + a temporary HKCU test key only; no LLM/network). Runs
without the `desktop` extra: the tray GUI is imported lazily inside the
launcher, and the checks cover the headless seams.

Run: python -m skill_gap_agent.m29_check
"""

from __future__ import annotations

import ast
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import tomllib
import urllib.request
from pathlib import Path

from . import __version__, checksupport, desktop, server

REPO_ROOT = Path(__file__).resolve().parents[2]


def _get(base: str, path: str) -> tuple[int, dict]:
    with urllib.request.urlopen(base + path, timeout=5) as resp:
        return resp.status, json.loads(resp.read().decode("utf-8"))


def check_version_sync() -> None:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text("utf-8"))
    declared = data["project"]["version"]
    assert declared == __version__ == desktop.app_version(), (
        declared, __version__, desktop.app_version()
    )
    assert desktop.RELEASES_URL.startswith("https://"), desktop.RELEASES_URL
    assert not desktop.STORE_URL or desktop.STORE_URL.startswith("https://"), (
        "STORE_URL must be empty (pre-listing) or an https listing URL"
    )
    print(f"version OK: {declared}; release URL set; store URL gated")


def check_runtime_paths() -> None:
    keys = ("LOCALAPPDATA", "XDG_DATA_HOME", desktop.DATA_DIR_ENV)
    previous = {key: os.environ.get(key) for key in keys}
    tmp = Path(tempfile.mkdtemp(prefix="m29-paths-"))
    try:
        for key in keys:
            os.environ.pop(key, None)
        if os.name == "nt":
            os.environ["LOCALAPPDATA"] = str(tmp)
        else:
            os.environ["XDG_DATA_HOME"] = str(tmp)
        installed = desktop.resolve_runtime_paths(frozen=True)
        assert installed.data_root == tmp / desktop.APP_DIR_NAME / "data", (
            installed
        )
        assert installed.log_dir == tmp / desktop.APP_DIR_NAME / "logs", installed

        dev = desktop.resolve_runtime_paths(frozen=False)
        assert dev.data_root == desktop.REPO_ROOT / "output", dev
        assert dev.log_dir == dev.data_root / "logs", dev

        os.environ[desktop.DATA_DIR_ENV] = str(tmp / "custom")
        override = desktop.resolve_runtime_paths(frozen=True)
        assert override.data_root == tmp / "custom", override
        assert override.log_dir == tmp / "custom" / "logs", override

        desktop.ensure_runtime_paths(installed)
        assert installed.data_root.is_dir() and installed.log_dir.is_dir()
        print("paths OK: frozen LocalAppData, dev output/, env override + mkdir")
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(tmp, ignore_errors=True)


def check_no_gui_imports() -> None:
    source = Path(desktop.__file__).read_text(encoding="utf-8")
    roots: set[str] = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    banned = {"pystray", "PIL"}
    assert not (roots & banned), (
        "tray GUI must be imported lazily so checks can run headless: "
        f"{sorted(roots & banned)}"
    )
    assert "pystray" not in sys.modules, "desktop import pulled in pystray"
    print("imports OK: no top-level tray/GUI imports")


def check_status_version() -> None:
    with checksupport.isolated_store():
        httpd = server.create_server(0)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            code, body = _get(base, "/api/status")
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
    assert code == 200, (code, body)
    assert body["app_version"] == __version__, body
    assert body["status"] == "idle", body
    print("status OK: /api/status carries app_version without changing state")


def check_backend_lifecycle() -> None:
    backend = desktop.Backend(port=0)
    try:
        backend.start()
        assert backend.running(), "backend thread did not start"
        base = f"http://127.0.0.1:{backend.port}"
        code, body = _get(base, "/api/status")
        assert code == 200 and body["app_version"] == __version__, (code, body)
        backend.restart()
        assert backend.running(), "backend did not restart"
        code, _ = _get(f"http://127.0.0.1:{backend.port}", "/api/status")
        assert code == 200, code
    finally:
        backend.stop()
    assert not backend.running(), "backend thread survived stop()"
    print("backend OK: start -> status -> restart -> stop")


def check_backend_port_error() -> None:
    real = server.create_server

    def busy(port: int = 8000):
        raise OSError("address already in use")

    server.create_server = busy  # type: ignore[assignment]
    backend = desktop.Backend(port=8000)
    try:
        try:
            backend.start()
        except OSError as exc:
            assert "already in use" in str(exc), exc
        else:
            raise AssertionError("busy port must fail loudly")
    finally:
        server.create_server = real  # type: ignore[assignment]
        backend.stop()
    assert not backend.running()
    print("port error OK: OSError propagates and no server is left running")


def check_single_instance() -> None:
    if os.name != "nt":
        print("single instance skipped: Windows-only mutex")
        return
    name = f"Local\\SkillGapAgent.M29Check.{os.getpid()}.{time.time_ns()}"
    first = desktop.SingleInstance(name)
    second = desktop.SingleInstance(name)
    assert first.acquire(), "first instance must acquire the mutex"
    second_acquired = False
    try:
        second_acquired = second.acquire()
        assert second_acquired is False, "second instance must be refused"
    finally:
        if second_acquired:
            second.release()
        first.release()
    third = desktop.SingleInstance(name)
    assert third.acquire(), "mutex must be released for the next launch"
    third.release()
    print("single instance OK: second acquire refused, release frees the name")


def check_startup_toggle() -> None:
    if os.name != "nt":
        print("startup toggle skipped: Windows-only registry")
        return
    import winreg

    key_path = (
        f"Software\\SkillGapAgentM29Check.{os.getpid()}.{time.time_ns()}"
    )
    value_name = "TestStartup"
    try:
        desktop.set_startup(
            True, key_path=key_path, value_name=value_name
        )
        assert desktop.startup_enabled(
            key_path=key_path, value_name=value_name
        ), "startup value was not written"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
        assert value == desktop.startup_command(), (value, desktop.startup_command())
        desktop.set_startup(
            False, key_path=key_path, value_name=value_name
        )
        assert not desktop.startup_enabled(
            key_path=key_path, value_name=value_name
        ), "startup value was not removed"
    except PermissionError:
        print("startup toggle skipped: registry write not permitted")
        return
    finally:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        except OSError:
            pass
    print("startup toggle OK: write/read/remove under a throwaway HKCU key")


def check_output_redirect() -> None:
    old_out, old_err = sys.stdout, sys.stderr
    handle = None
    with tempfile.TemporaryDirectory(prefix="m29-log-") as tmp:
        try:
            path = desktop.redirect_output(Path(tmp))
            handle = sys.stdout
            print("redirect-probe", flush=True)
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            if handle is not None:
                handle.close()
        assert "redirect-probe" in path.read_text(encoding="utf-8"), path
    print("output redirect OK: windowed-build prints land in desktop.log")


def main() -> None:
    check_version_sync()
    check_runtime_paths()
    check_no_gui_imports()
    check_status_version()
    check_backend_lifecycle()
    check_backend_port_error()
    check_single_instance()
    check_startup_toggle()
    check_output_redirect()
    print("M29 launcher checks OK")


if __name__ == "__main__":
    main()
