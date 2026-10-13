"""Pytest wrapper for the M26 debug-mode checks.

The full flow (real graph run + server boot) runs via the verify list
(python -m skill_gap_agent.m26_check); these wrap the light, side-effect-
free checks so `pytest` guards them too.
"""

from skill_gap_agent.m26_check import (
    check_debuglog_imports,
    check_line_format,
    check_llm_summary,
    check_node_hooks_attached,
    check_off_by_default,
    check_payload_gating,
    check_stage_decorator,
)


def test_off_by_default() -> None:
    check_off_by_default()


def test_line_format() -> None:
    check_line_format()


def test_payload_gating() -> None:
    check_payload_gating()


def test_stage_decorator() -> None:
    check_stage_decorator()


def test_node_hooks_attached() -> None:
    check_node_hooks_attached()


def test_llm_summary() -> None:
    check_llm_summary()


def test_debuglog_imports() -> None:
    check_debuglog_imports()
