"""Pytest wrappers for the M29 desktop-launcher checks.

The full live tray pass runs separately; these wrap the offline, side-effect-
free checks so `pytest` guards them too.
"""

from skill_gap_agent.m29_check import (
    check_backend_lifecycle,
    check_backend_port_error,
    check_no_gui_imports,
    check_output_redirect,
    check_runtime_paths,
    check_single_instance,
    check_startup_toggle,
    check_status_version,
    check_version_sync,
)


def test_version_sync() -> None:
    check_version_sync()


def test_runtime_paths() -> None:
    check_runtime_paths()


def test_no_gui_imports() -> None:
    check_no_gui_imports()


def test_status_version() -> None:
    check_status_version()


def test_backend_lifecycle() -> None:
    check_backend_lifecycle()


def test_backend_port_error() -> None:
    check_backend_port_error()


def test_single_instance() -> None:
    check_single_instance()


def test_startup_toggle() -> None:
    check_startup_toggle()


def test_output_redirect() -> None:
    check_output_redirect()
