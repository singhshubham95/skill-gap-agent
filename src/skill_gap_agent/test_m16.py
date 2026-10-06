"""Pytest wrappers for the M16 offline checks (harness: m16_check.py).

Same convention as test_m13.py / test_m14.py / test_m15.py: zero-arg
wrappers so `pytest` runs the checks `python -m skill_gap_agent.m16_check`
runs. Everything is offline (LLM seams stubbed at the llm._client
boundary, OpenRouter exchange stubbed, keyring stubbed, localhost only).
"""

from skill_gap_agent.m16_check import (
    check_bounded_attempts,
    check_consent_gate,
    check_model_fallback,
    check_oauth_connect_flow,
    check_retry_classification,
)


def test_oauth_connect_flow() -> None:
    check_oauth_connect_flow()


def test_consent_gate() -> None:
    check_consent_gate()


def test_retry_classification() -> None:
    check_retry_classification()


def test_bounded_attempts() -> None:
    check_bounded_attempts()


def test_model_fallback() -> None:
    check_model_fallback()
