"""Pytest wrappers for the M24 offline checks (harness: m24_check.py).

Same convention as test_m21.py: zero-arg wrappers so `pytest` runs the
checks `python -m skill_gap_agent.m24_check` runs. Everything is offline
(LLM extractor stubbed, localhost only, temp artifact dirs).
"""

from skill_gap_agent.m24_check import (
    check_mode_scoped_cache,
    check_panel_surface,
    check_upload_contract,
)


def test_upload_contract() -> None:
    check_upload_contract()


def test_mode_scoped_cache() -> None:
    check_mode_scoped_cache()


def test_panel_surface() -> None:
    check_panel_surface()
