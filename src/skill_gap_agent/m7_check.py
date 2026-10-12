"""M7 verification: interrupt/resume flow through the LangGraph runner.

Simulates a user answering gate prompts by feeding scripted answers into the
interrupt/resume loop — the same loop cli.main() drives. Verifies:
1. The graph interrupts at the gate (instead of blocking stdin).
2. Resume with answers completes the run.
3. Decisions persist to the SESSION PROFILE (M9 rule: the retired global
   gate_overrides.json is never created or read).

Deterministic (M9): the check seeds its own session (a temp copy of the
skills JSON) with a fixture graph carrying two sub-threshold TRANSFERS_TO
edges, so the gate fires regardless of what other checks left behind. Fully
offline: top_n=0 skips synthesis, skip_oss skips sourcing.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .cli import (
    AgentState,
    _profile_gate_overrides,
    build_app,
    pending_interrupt,
    prompt_text,
)
from .graph import Skill, SkillGraph, SkillSource
from .sessions import retire_legacy_files, session_dir

CHECKPOINT_PATH = Path("output/checkpoints_test.sqlite")

# Fixture edges: two real target skills (from data/jds) at sub-threshold
# confidence -> the gate must prompt for each (depth + intent = 2 prompts).
FIXTURE_EDGES = {"Fine-tuning": 0.5, "Spark": 0.5}


def check_profile_ties() -> None:
    """Regression (live-pass bug, 2026-10-12): gate profiling must survive
    EQUAL-confidence TRANSFERS_TO edges into one target. The old
    max((confidence, edge_dict)) compared the dicts on ties —
    TypeError: '>' not supported between instances of 'dict' and 'dict' —
    crashing gate_needed right after judging (real judge scores tie
    often; the offline harnesses stubbed distinct ones, so it hid)."""
    sg = SkillGraph()
    sg.add_skill(Skill(name="Python", source=SkillSource.CURRENT))
    sg.add_skill(Skill(name="PyTorch", source=SkillSource.CURRENT))
    sg.add_skill(Skill(name="TensorFlow", source=SkillSource.TARGET))
    # Distinct rationale per edge: equal-confidence ties only crash when
    # the edge dicts DIFFER (tuple comparison skips elements that are ==,
    # so identical stub data masked the bug in every earlier harness).
    sg.add_transfers_to("Python", "TensorFlow", 0.85, "from python")
    sg.add_transfers_to("PyTorch", "TensorFlow", 0.85, "from pytorch")
    out = _profile_gate_overrides(sg, {"intent": {"TensorFlow": "count"}})
    assert "TensorFlow" in out, out
    assert out["TensorFlow"]["final_confidence"] == 0.85, out
    print("profile ties OK: equal-confidence edges do not crash gate profiling")


def _seed_fixture_graph(session: Path) -> None:
    """Pre-seed the session's graph.json so skip_judge copies these edges."""
    sg = SkillGraph()
    sg.add_skill(Skill(name="Python", source=SkillSource.CURRENT))
    for target, conf in FIXTURE_EDGES.items():
        sg.add_skill(Skill(name=target, source=SkillSource.TARGET))
        sg.add_transfers_to("Python", target, conf, "fixture")
    sg.save(str(session / "graph.json"))


def main() -> None:
    check_profile_ties()
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()

    retire_legacy_files()  # M9 migration: retired globals must not linger

    with tempfile.TemporaryDirectory() as td:
        skills = Path(td) / "skills.json"
        skills.write_text(
            json.dumps({"skills": ["Python programming experience"]}),
            encoding="utf-8",
        )
        import shutil

        shutil.rmtree(session_dir(skills), ignore_errors=True)  # hermetic
        session = session_dir(skills, create=True)
        _seed_fixture_graph(session)

        conn = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
        saver = SqliteSaver(conn)
        app = build_app(checkpointer=saver)
        config = {"configurable": {"thread_id": "m7-test"}}

        state: AgentState = {
            "skills_path": str(skills),
            "jds_path": "data/jds",
            "auto": False,
            "skip_judge": True,
            "skip_oss": True,
            "top_n": 0,
            "source_input": str(skills),
            "session_dir": str(session),
        }

        answers = iter(["3", "y", "3", "y", "3", "y", "3", "y"])
        resumed = 0

        app.invoke(state, config=config)
        while True:
            pending = pending_interrupt(app, config)
            if pending is None:
                break
            prompt = prompt_text(pending.value)
            print(f"INTERRUPT: {prompt.strip()[:90]}")
            answer = next(answers)
            print(f"  -> scripted answer: {answer}")
            resumed += 1
            app.invoke(Command(resume=answer), config=config)

        print(f"\nInterrupts handled: {resumed}")
        profile_path = session / "profile.json"
        profile = (
            json.loads(profile_path.read_text(encoding="utf-8"))
            if profile_path.exists()
            else {}
        )
        gate = profile.get("gate") or {}
        print(f"profile.json gate decisions: {sorted(gate)}")
        legacy = Path("output/gate_overrides.json")
        print(f"gate_overrides.json exists (must be False): {legacy.exists()}")
        snap = app.get_state(config)
        print(f"Final state next: {snap.next}")
        ok = (
            resumed >= 2 * len(FIXTURE_EDGES)  # depth + intent per fixture target
            and not snap.next
            and set(gate) >= set(FIXTURE_EDGES)
            and not legacy.exists()
        )
        print("PASS" if ok else "FAIL")

        conn.close()  # Windows: must close before unlinking the sqlite file
        CHECKPOINT_PATH.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
