"""Pytest wrappers for the M9 offline checks (harness: m9_check.py).

Same convention as test_m24.py: zero-arg wrappers so `pytest` runs the
checks `python -m skill_gap_agent.m9_check` runs. Everything is offline
(LLM seams stubbed, localhost only, isolated session stores).
"""

from skill_gap_agent.m9_check import (
    check_depth_judge_and_gate,
    check_end_to_end,
    check_intake_chat,
    check_panel_surface,
    check_sessions,
    check_validation_protocol,
)


def test_sessions() -> None:
    check_sessions()


def test_intake_chat() -> None:
    check_intake_chat()


def test_validation_protocol() -> None:
    check_validation_protocol()


def test_depth_judge_and_gate() -> None:
    check_depth_judge_and_gate()


def test_end_to_end() -> None:
    check_end_to_end()


def test_panel_surface() -> None:
    check_panel_surface()
