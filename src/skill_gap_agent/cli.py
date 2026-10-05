"""LangGraph orchestration (milestone 7, specs/10-flow-runner.md S7).

Wires the v1 pipeline nodes into a real LangGraph graph:

- Conditional edges replace sequential assumptions: the confidence gate runs
  only when the judge left sub-threshold targets; project synthesis runs only
  when actionable gaps exist.
- Human-in-the-loop (implied-skill proposals, confidence gate) uses true
  interrupt()/resume with a checkpointer, so a run can be resumed and moved to
  a web UI later (restores deferred-enhancements #2).
- State is a TypedDict of serializable fields only; the SkillGraph lives in
  the runtime registry keyed by thread_id (decision in specs/02-decisions.md).

Interactive prompts are routed through an ask_fn that raises an interrupt with
the prompt text and returns the user's answer on resume. Re-runs are cheap:
persisted decisions (implied_skills.json, gate_overrides.json) are applied
silently, so interrupts only fire for genuinely new questions.

M13 additions: a `pause` node after rank powers the extension's two-phase
flow (analyze gaps -> generate plan); the `oss` node sources good-first-issues
after synthesis; nodes report progress through set_stage_listener().

Run: python -m skill_gap_agent.cli [--auto] [--no-judge] [--top N] [--resume]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import operator
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .gate import DEFAULT_THRESHOLD, gate_summary, review_targets
from .graph import SkillGraph
from .ingest import build_seed_graph
from .judge import judge_all_unmatched, save_judge_report
from .llm import LLMConfig, LLMError, require_api_key
from .oss import source_oss_for_gaps
from .output import write_plan, write_plan_html
from .ranking import format_ranking, rank_gaps
from .resume import resume_to_skills_json
from .synthesis import save_synthesis_report, synthesize_for_gaps
from .taxonomy import load_taxonomy

CHECKPOINT_PATH = Path("output/checkpoints.sqlite")

# Runtime registry for non-serializable objects (the SkillGraph). The
# checkpointer serializes every state channel, so the graph object must NOT
# live in state — nodes access it via the thread id. Graph persistence stays
# with output/graph.json per the override-file convention.
_RUNTIME: dict[str, dict[str, Any]] = {}


def _runtime(config: dict) -> dict[str, Any]:
    return _RUNTIME.setdefault(config["configurable"]["thread_id"], {})


# Progress-reporting seam: server.py (M11) registers a listener to surface
# node progress on the local UI and the extension side panel (M13). Nodes
# call _stage() with their name; the listener is set for the run's duration.
_STAGE_LISTENER: Callable[[str], None] | None = None


def set_stage_listener(fn: Callable[[str], None] | None) -> None:
    """Register a progress callback fn(node_name), or None to clear."""
    global _STAGE_LISTENER
    _STAGE_LISTENER = fn


def _stage(name: str) -> None:
    if _STAGE_LISTENER is not None:
        _STAGE_LISTENER(name)


class AgentState(TypedDict, total=False):
    """Pipeline state — serializable data only (flags, paths, results).
    The SkillGraph lives in the runtime registry, not here."""

    skills_path: str
    jds_path: str
    auto: bool
    skip_judge: bool
    top_n: int
    stats: dict
    judged: bool
    gate_decisions: list
    gaps: list
    projects: list
    skip_oss: bool
    no_llm_oss: bool
    reuse_judged: bool  # M13: reuse TRANSFERS_TO edges, judge only new targets
    two_phase: bool  # M13: pause after rank for the extension's two-button flow
    phase_resumed: bool
    oss_by_gap: dict
    link_jds: bool
    jd_files: dict
    provider: str  # M14: llm provider id (openrouter/glm/openai), default openrouter
    use_llm: bool  # M15: run-level LLM mode (false = Rule-based mode)
    # M15 append-only channels (specs/05-ai-caller.md §LLM presence policy):
    # unjudged targets (target + reason) and per-touchpoint degradation
    # records ({touchpoint, error}) accumulate across nodes and phases.
    unjudged: Annotated[list[dict], operator.add]
    degraded_reasons: Annotated[list[dict], operator.add]


def _llm_cfg(state: AgentState) -> LLMConfig:
    """LLM config for a run: provider comes from run state (M14)."""
    return LLMConfig(provider=state.get("provider") or "openrouter")


def ask_via_interrupt(prompt: str) -> str:
    """Route one interactive prompt through LangGraph interrupt().

    Called from node code via the ask_fn seam in gate.py / implied.py; the
    runner surfaces the prompt to the user and resumes with the answer.
    """
    answer = interrupt({"prompt": prompt})
    return str(answer)


def pending_interrupt(app, config: dict) -> Any | None:
    """Return the pending Interrupt of the run, or None if none is pending.

    Detection MUST use the task list, not get_state().next: after a resume
    that immediately hits another interrupt() in the same node, `next` is
    empty even though a question is pending (the run never left the node,
    so the "waiting at" pointer doesn't move). Verified in M7 — see
    specs/10-flow-runner.md S7 ("Detecting pending interrupts").
    """
    snap = app.get_state(config)
    if not snap:
        return None
    for t in snap.tasks or []:
        if getattr(t, "interrupts", None):
            return t.interrupts[0]
    return None


def prompt_text(value: Any) -> str:
    """Extract the human-readable prompt from an Interrupt value."""
    return value.get("prompt", "") if isinstance(value, dict) else str(value)


def _ask_or_interrupt(prompt: str, checkpointer, config: dict) -> str:
    """Ask one question outside the graph: interrupt() if resumable, else stdin.

    The M8 resume-approval flow runs BEFORE the graph starts, so it cannot
    rely on a node context. With a checkpointer, interrupt()/Command(resume)
    still works (the pause is recorded in the checkpoint); without one, fall
    back to plain input() — same seam semantics as inside nodes.
    """
    if checkpointer is None:
        return input(prompt)

    value = interrupt({"prompt": prompt})
    return str(value)


# --- nodes -----------------------------------------------------------------


def node_ingest(state: AgentState, config: RunnableConfig) -> dict:
    _stage("ingest")
    taxonomy = load_taxonomy()
    sg, stats = build_seed_graph(
        state["skills_path"],
        state["jds_path"],
        taxonomy=taxonomy,
        auto_accept_implied=state["auto"],
        ask_fn=None if state["auto"] else ask_via_interrupt,
    )
    print(
        f"Graph: {stats['canonical']} canonical + {stats['implied']} implied skills, "
        f"{stats['jds']} JDs"
    )
    _runtime(config)["sg"] = sg
    return {"stats": stats}


def _copy_previous_transfers(sg: SkillGraph) -> int:
    """Copy TRANSFERS_TO edges from the last saved graph into this run.

    Copied edges are marked cached=True so ranking can label their rows
    "LLM (cached)" instead of freshly-judged (M15 provenance).
    """
    prev_path = Path("output/graph.json")
    if not prev_path.exists():
        return 0
    prev = SkillGraph.load(str(prev_path))
    reused = 0
    for u, v, d in prev.g.edges(data=True):
        if d.get("type") == "TRANSFERS_TO" and sg.g.has_node(v):
            sg.g.add_edge(u, v, **{**d, "cached": True})
            reused += 1
    return reused


def _save_merged_judge_report(results: list) -> None:
    """Append new judge results to output/judge_report.json, keyed by target.

    Used with reuse_judged: cached targets keep their old report rows, newly
    judged targets replace/add theirs (judge score is a pure function of the
    target — the M12 insight — so rows are interchangeable across runs).
    """
    path = Path("output/judge_report.json")
    merged: dict[str, dict] = {}
    if path.exists():
        try:
            for row in json.loads(path.read_text(encoding="utf-8")):
                merged[row["target"]] = row
        except (ValueError, KeyError, TypeError):
            pass
    for r in results:
        merged[r.target] = {"target": r.target, "error": r.error, "scores": r.scores}
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(list(merged.values()), indent=2), encoding="utf-8")


def node_judge(state: AgentState, config: RunnableConfig) -> dict:
    _stage("judge")
    sg: SkillGraph = _runtime(config)["sg"]
    if not state.get("use_llm", True):
        # M15 Rule-based mode: nothing is measured, so rows render "unjudged"
        # instead of a fake confidence-0 transfer score.
        targets = sorted(sg.unmatched_target_skills())
        print(
            f"Rule-based mode: LLM judging skipped "
            f"({len(targets)} target(s) marked unjudged)"
        )
        return {
            "judged": False,
            "unjudged": [{"target": t, "reason": None} for t in targets],
        }
    if state.get("skip_judge") or state.get("reuse_judged"):
        reused = _copy_previous_transfers(sg)
        print(f"Reused {reused} TRANSFERS_TO edges from output/graph.json")
        if state.get("skip_judge"):
            # --no-judge measures nothing new: remaining unmatched targets
            # are unjudged, not measured gaps (M15).
            targets = sorted(sg.unmatched_target_skills())
            return {
                "judged": False,
                "unjudged": [{"target": t, "reason": None} for t in targets],
            }

    unmatched = sg.unmatched_target_skills()
    if not unmatched:
        return {"judged": False}
    print(f"Judging {len(unmatched)} unmatched target skills...\n")
    results = judge_all_unmatched(sg, cfg=_llm_cfg(state))
    if state.get("reuse_judged"):
        _save_merged_judge_report(results)
    else:
        save_judge_report(results, Path("output/judge_report.json"))
    out: dict = {"judged": True}
    # M15: a failed judge call must never read as a measured 0-confidence
    # gap — the target is labeled unjudged and the run is marked degraded.
    # "no candidates" is structural (nothing plausible to judge against),
    # not an outage: it rides the unjudged channel for classification but
    # does not raise the degraded banner.
    failed = [{"target": r.target, "reason": r.error} for r in results if r.error]
    if failed:
        out["unjudged"] = failed
        out["degraded_reasons"] = [
            {"touchpoint": f"judge({r.target})", "error": r.error}
            for r in results
            if r.error and r.error != "no candidates"
        ]
    return out


def gate_needed(state: AgentState, config: RunnableConfig) -> str:
    """Conditional edge: run the interactive gate only if sub-threshold,
    not-yet-decided targets exist (auto mode never prompts)."""
    if state["auto"]:
        return "rank"
    sg: SkillGraph = _runtime(config)["sg"]
    saved = _gate_override_names()
    for target in sorted(sg.target_skills()):
        if target in saved:
            continue
        top = _top_confidence(sg, target)
        if top is not None and top < DEFAULT_THRESHOLD:
            return "gate"
    return "rank"


def _gate_override_names() -> set[str]:
    p = Path("output/gate_overrides.json")
    if not p.exists():
        return set()
    return set(json.loads(p.read_text(encoding="utf-8")).keys())


def _top_confidence(sg: SkillGraph, target: str) -> float | None:
    confs = [
        float(d.get("confidence", 0.0))
        for u, _, d in sg.g.in_edges(f"skill:{target}", data=True)
        if d.get("type") == "TRANSFERS_TO"
    ]
    return max(confs) if confs else None


def node_gate(state: AgentState, config: RunnableConfig) -> dict:
    _stage("gate")
    sg: SkillGraph = _runtime(config)["sg"]
    decisions = review_targets(
        sg, threshold=DEFAULT_THRESHOLD, ask_fn=ask_via_interrupt
    )
    print(gate_summary(decisions))
    return {"gate_decisions": decisions}


def _write_gaps_json(gaps: list) -> Path:
    """Persist the ranked gaps (M13: served to the extension via GET /api/gaps)."""
    out = Path("output")
    out.mkdir(exist_ok=True)
    p = out / "gaps.json"
    payload = {"gaps": [dataclasses.asdict(g) for g in gaps]}
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return p


def node_rank(state: AgentState, config: RunnableConfig) -> dict:
    _stage("rank")
    unjudged = {
        u["target"]: u.get("reason")
        for u in state.get("unjudged", [])
        if isinstance(u, dict) and u.get("target")
    }
    gaps = rank_gaps(_runtime(config)["sg"], unjudged=unjudged or None)
    print("\n=== Gap ranking ===")
    print(format_ranking(gaps))
    gaps_path = _write_gaps_json(gaps)
    print(f"Gaps written: {gaps_path}")
    return {"gaps": gaps}


def node_pause(state: AgentState, config: RunnableConfig) -> dict:
    """M13 two-phase pause: hold the run after ranking until phase 2.

    Same interrupt() machinery as the gate questions: with a checkpointer the
    server resumes via Command(resume=...), and the node re-executes (replay
    semantics — the interrupt() call returns the resume value the second
    time). Only reached when state['two_phase'] is set.
    """
    _stage("pause")
    interrupt(
        {"phase": "gaps", "prompt": "Gaps ready. Resume to generate the plan."}
    )
    return {"phase_resumed": True}


def _actionable_gaps(state: AgentState) -> list:
    return [
        g for g in state.get("gaps", [])
        if g.verdict not in ("bridge", "alt-bridged", "held")
    ]


def after_rank(state: AgentState) -> str:
    """Conditional edge after rank and after the two-phase pause.

    Order: pause (two-phase, first visit) -> synthesize (actionable gaps and
    top_n > 0) -> output. The oss node hangs off synthesis (M10: same top-n
    actionable gaps).
    """
    if state.get("two_phase") and not state.get("phase_resumed"):
        return "pause"
    if not _actionable_gaps(state) or state.get("top_n", 0) <= 0:
        return "output"
    return "synthesize"


def after_synthesize(state: AgentState) -> str:
    """Conditional edge: source GFI issues unless --no-oss."""
    return "output" if state.get("skip_oss") else "oss"


def node_synthesize(state: AgentState, config: RunnableConfig) -> dict:
    _stage("synthesize")
    if not state.get("use_llm", True):
        # M15 Rule-based mode: project synthesis is LLM-only — the plan
        # renders a labeled note instead of template filler.
        print("Rule-based mode: project synthesis skipped (needs the LLM)")
        return {"projects": []}
    projects = synthesize_for_gaps(
        _runtime(config)["sg"], state["gaps"], top_n=state["top_n"], cfg=_llm_cfg(state)
    )
    out: dict = {"projects": projects}
    failed = [r for r in projects if r.error]
    if failed:
        out["degraded_reasons"] = [
            {"touchpoint": f"synthesis({r.gap.target})", "error": r.error}
            for r in failed
        ]
    return out


def node_oss(state: AgentState, config: RunnableConfig) -> dict:
    """M10 node: good-first-issue sourcing for the top actionable gaps."""
    _stage("oss")
    if state.get("skip_oss"):
        return {"oss_by_gap": {}}
    # M15: Rule-based mode implies keyword-only sourcing (no LLM filter).
    use_llm_oss = state.get("use_llm", True) and not state.get("no_llm_oss", False)
    degraded: list[dict] = []
    oss_by_gap = source_oss_for_gaps(
        _runtime(config)["sg"],
        state["gaps"],
        top_n=state["top_n"],
        cfg=_llm_cfg(state),
        use_llm=use_llm_oss,
        degraded_out=degraded,
    )
    return {"oss_by_gap": oss_by_gap, "degraded_reasons": degraded}


def node_output(state: AgentState, config: RunnableConfig) -> dict:
    _stage("output")
    sg: SkillGraph = _runtime(config)["sg"]
    out = Path("output")
    projects = state.get("projects", [])
    oss_by_gap = state.get("oss_by_gap") or {}
    jd_files = state.get("jd_files") if state.get("link_jds") else None
    # M15: the plan states its mode and any loud degradations (provenance
    # vocabulary lives in llm.py / specs/05-ai-caller.md §Provenance).
    run_info = {
        "llm_mode": "llm" if state.get("use_llm", True) else "rule-based",
        "degraded_reasons": state.get("degraded_reasons", []),
    }
    plan_path = write_plan(
        state["gaps"], projects, state["stats"], out / "plan.md", oss_by_gap,
        run_info=run_info,
    )
    write_plan_html(
        state["gaps"], projects, state["stats"], oss_by_gap, out / "plan.html", jd_files,
        run_info=run_info,
    )
    save_synthesis_report(projects, out / "synthesis_report.json")
    sg.save(str(out / "graph.json"))
    print(f"\nPlan written: {plan_path}")
    print(
        f"Graph saved: {sg.g.number_of_nodes()} nodes, "
        f"{sg.g.number_of_edges()} edges"
    )
    return {}


# --- graph assembly ---------------------------------------------------------


def build_app(checkpointer=None):
    """Compile the pipeline graph. Pass a checkpointer to make interrupt()
    pauses resumable (gate questions and the M13 two-phase pause); the graph
    shape is unchanged by it."""
    g = StateGraph(AgentState)
    g.add_node("ingest", node_ingest)
    g.add_node("judge", node_judge)
    g.add_node("gate", node_gate)
    g.add_node("rank", node_rank)
    g.add_node("pause", node_pause)
    g.add_node("synthesize", node_synthesize)
    g.add_node("oss", node_oss)
    g.add_node("output", node_output)

    g.add_edge(START, "ingest")
    g.add_edge("ingest", "judge")
    g.add_conditional_edges("judge", gate_needed, {"gate": "gate", "rank": "rank"})
    g.add_edge("gate", "rank")
    routes = {"pause": "pause", "synthesize": "synthesize", "output": "output"}
    g.add_conditional_edges("rank", after_rank, routes)
    g.add_conditional_edges("pause", after_rank, routes)
    g.add_conditional_edges(
        "synthesize", after_synthesize, {"oss": "oss", "output": "output"}
    )
    g.add_edge("oss", "output")
    g.add_edge("output", END)
    return g.compile(checkpointer=checkpointer)


def main() -> None:
    parser = argparse.ArgumentParser(description="Skill-gap agent (LangGraph runner)")
    parser.add_argument(
        "skills",
        nargs="?",
        default="data/skillsdataset.json",
        help="skills JSON, or a resume file (.pdf/.docx/.txt) to extract from",
    )
    parser.add_argument("jds", nargs="?", default="data/jds")
    parser.add_argument("--auto", action="store_true", help="no interactive prompts")
    parser.add_argument("--no-judge", action="store_true", help="reuse TRANSFERS_TO edges")
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="Rule-based mode (M15): no LLM calls anywhere — regex extraction, "
        "unjudged transfers, keyword GFI, no project synthesis",
    )
    parser.add_argument(
        "--provider",
        default="openrouter",
        help="LLM provider id: openrouter / glm / openai (default openrouter)",
    )
    parser.add_argument("--top", type=int, default=5, dest="top_n")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="persist checkpoints to output/checkpoints.sqlite so an interrupted "
        "run can be resumed by re-running with --resume",
    )
    args = parser.parse_args()

    # M15 pre-flight (specs/05-ai-caller.md §Availability): LLM mode with no
    # key refuses before any work instead of silently degrading mid-run.
    if not args.no_llm:
        try:
            require_api_key(args.provider)
        except LLMError as e:
            print(f"error: {e}", file=sys.stderr)
            raise SystemExit(2) from e

    checkpointer = None
    if args.resume:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver

        conn = sqlite3.connect(str(CHECKPOINT_PATH), check_same_thread=False)
        checkpointer = SqliteSaver(conn)

    config = {"configurable": {"thread_id": "cli"}}

    # M8 front-end: a resume file is converted to skills JSON BEFORE the
    # graph starts (extraction needs no interrupt; M9 intake will reuse the
    # same function as a tool). A .json input takes today's path unchanged.
    skills_path = args.skills
    if Path(skills_path).suffix.lower() != ".json":
        json_path, _stats = resume_to_skills_json(
            skills_path,
            use_llm=not args.no_llm,
            auto=args.auto,
            ask_fn=None if args.auto else (lambda p: _ask_or_interrupt(p, checkpointer, config)),
            cfg=LLMConfig(provider=args.provider),
        )
        skills_path = str(json_path)

    app = build_app(checkpointer=checkpointer)
    state: AgentState = {
        "skills_path": skills_path,
        "jds_path": args.jds,
        "auto": args.auto,
        "skip_judge": args.no_judge,
        "top_n": args.top_n,
        "provider": args.provider,
        "use_llm": not args.no_llm,
    }
    config = {"configurable": {"thread_id": "cli"}}

    # Drive the run, surfacing interrupts on the console and resuming.
    # get_state() requires a checkpointer; without one, interrupts cannot
    # occur in auto mode anyway (ask_fn is None).
    app.invoke(state, config=config)
    while checkpointer is not None:
        pending = pending_interrupt(app, config)
        if pending is None:
            break
        prompt = prompt_text(pending.value)
        if prompt:
            print(prompt, end="", flush=True)
        answer = input()
        app.invoke(Command(resume=answer), config=config)


if __name__ == "__main__":
    main()
