"""Pytest wrappers for the M18 offline checks (harness: m18_check.py).

Same convention as test_m14.py: zero-arg wrappers so `pytest` runs the
checks `python -m skill_gap_agent.m18_check` runs. Everything is offline
(key validation stubbed, node probe against a stub DOM, localhost only).
"""

from skill_gap_agent.m18_check import (
    check_key_status_endpoint,
    check_mode_mapping,
    check_panel_surface,
)


def test_key_status_endpoint() -> None:
    check_key_status_endpoint()


def test_mode_mapping() -> None:
    check_mode_mapping()


def test_panel_surface() -> None:
    check_panel_surface()
