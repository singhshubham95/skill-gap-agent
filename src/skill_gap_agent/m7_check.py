"""M7 verification: interrupt/resume flow through the LangGraph runner.

Simulates a user answering gate prompts by feeding scripted answers into the
interrupt/resume loop — the same loop cli.main() drives. Verifies:
1. The graph interrupts at the gate (instead of blocking stdin).
2. Resume with answers completes the run.
3. Decisions persist to output/gate_overrides.json.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from .cli import AgentState, build_app, pending_interrupt, prompt_text

CHECKPOINT_PATH = Path("output/checkpoints_test.sqlite")


def main() -> None:
    if CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()

    # Back up and clear saved gate decisions so the gate path actually fires
    # (persisted decisions are applied silently by design).
    overrides = Path("output/gate_overrides.json")
    backup = Path("output/gate_overrides.json.m7bak")
    if overrides.exists():
        backup.write_bytes(overrides.read_bytes())
        overrides.unlink()

    conn = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
    saver = SqliteSaver(conn)
    app = build_app(checkpointer=saver)
    config = {"configurable": {"thread_id": "m7-test"}}

    state: AgentState = {
        "skills_path": "data/skillsdataset.json",
        "jds_path": "data/jds",
        "auto": False,
        "skip_judge": True,
        "top_n": 2,
    }

    answers = iter(["3", "y", "3", "y", "3", "y", "3", "y", "3", "y", "3", "y"])
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
    print(f"gate_overrides.json exists: {overrides.exists()}")
    snap = app.get_state(config)
    print(f"Final state next: {snap.next}")
    ok = resumed > 0 and not snap.next and overrides.exists()
    print("PASS" if ok else "FAIL")

    conn.close()  # Windows: must close before unlinking the sqlite file
    CHECKPOINT_PATH.unlink(missing_ok=True)

    # Restore the user's real gate decisions
    if backup.exists():
        overrides.write_bytes(backup.read_bytes())
        backup.unlink()


if __name__ == "__main__":
    main()