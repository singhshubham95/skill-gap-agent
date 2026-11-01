# T-MAINT-20261101-DEDUPE: consolidate duplicate check-harness helpers

- **Status:** planned
- **Owner:** human
- **Source:** `board/maintenance/2026-11-01.md` §F-21
- **Blocked by:** none

## Why

Two helper pairs are byte-identical across check harnesses:
`_wait_status` in `m13_check.py` and `m15_check.py`, and `_start` in
`m16_check.py` and `m20_check.py`. `checksupport.py` already owns shared
check isolation, so it is the natural home.

## Files to touch (the scope guard permits exactly these)

- `src/skill_gap_agent/`

## Acceptance criteria

1. `wait_status` and `start_server` live once in `checksupport.py` and are
   imported by the four harnesses.
2. No behavior change: m13/m15/m16/m20 checks and `pytest` stay green.
3. No test assertion is weakened or skipped.

## Tests to run

- `python -m skill_gap_agent.m13_check`
- `python -m skill_gap_agent.m15_check`
- `python -m skill_gap_agent.m16_check`
- `python -m skill_gap_agent.m20_check`
- `python -m pytest -q`
