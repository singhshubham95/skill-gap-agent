"""Pytest wrappers for the M15 offline checks (harness: m15_check.py).

Same convention as test_m13.py / test_m14.py: zero-arg wrappers so `pytest`
runs the checks `python -m skill_gap_agent.m15_check` runs. Everything is
offline (LLM seams stubbed at the llm module boundary, GitHub search
stubbed, localhost only) and real artifacts are preserved/restored.
"""

from skill_gap_agent.m15_check import (
    check_extraction_provenance,
    check_llm_mode_labels,
    check_loud_degradation,
    check_pre_flight_refusal,
    check_vocabulary_and_panel,
)


def test_vocabulary_and_panel() -> None:
    check_vocabulary_and_panel()


def test_pre_flight_refusal() -> None:
    check_pre_flight_refusal()


def test_loud_degradation() -> None:
    check_loud_degradation()


def test_llm_mode_labels() -> None:
    check_llm_mode_labels()


def test_extraction_provenance() -> None:
    check_extraction_provenance()
