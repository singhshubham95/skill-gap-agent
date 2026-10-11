"""Pytest wrappers for the M19 offline checks (harness: m19_check.py).

Same convention as test_m18.py: zero-arg wrappers so `pytest` runs the
checks `python -m skill_gap_agent.m19_check` runs. Everything is offline
(localhost only, output/plan.html preserved).
"""

from skill_gap_agent.m19_check import check_panel_theming, check_plan_theming


def test_plan_theming() -> None:
    check_plan_theming()


def test_panel_theming() -> None:
    check_panel_theming()
