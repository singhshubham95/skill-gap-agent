"""Pytest wrappers for the M14 offline checks (harness: m14_check.py).

Same convention as test_m13.py: zero-arg wrappers so `pytest` runs the
checks `python -m skill_gap_agent.m14_check` runs. Everything is offline
(LLM extraction forced to the regex fallback, keyring seam stubbed,
localhost only).
"""

from skill_gap_agent.m14_check import (
    check_key_endpoint,
    check_panel_and_launcher,
    check_resume_endpoint,
    check_skills_provider_resolution,
)


def test_resume_endpoint() -> None:
    check_resume_endpoint()


def test_key_endpoint() -> None:
    check_key_endpoint()


def test_skills_provider_resolution() -> None:
    check_skills_provider_resolution()


def test_panel_and_launcher() -> None:
    check_panel_and_launcher()
