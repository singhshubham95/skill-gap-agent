"""Pytest wrapper for the M7 gate-profiling tie regression.

The full m7 interrupt/resume flow (main()) runs via the verify list
(python -m skill_gap_agent.m7_check); this wraps the light regression
check so `pytest` guards it too.
"""

from skill_gap_agent.m7_check import check_profile_ties


def test_profile_ties() -> None:
    check_profile_ties()
