"""Pytest wrappers for the M13 offline checks (harness: m13_check.py).

The repo's milestone done criteria include `pytest` clean; these zero-arg
wrappers let pytest run the same checks `python -m skill_gap_agent.m13_check`
runs. All checks are offline (stubbed judge/synthesis/oss, localhost only).
"""

from skill_gap_agent.m13_check import (
    check_cli_wiring,
    check_extension_manifest,
    check_two_phase_flow,
)


def test_cli_wiring() -> None:
    check_cli_wiring()


def test_extension_manifest() -> None:
    check_extension_manifest()


def test_two_phase_flow() -> None:
    check_two_phase_flow()
