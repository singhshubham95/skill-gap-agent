"""Milestone 4 runner: build graph, judge, run the confidence gate.

Run: python -m skill_gap_agent.m4_gate --auto   (scripted: no stdin review)
"""

from __future__ import annotations

import sys
from pathlib import Path

from .gate import DEFAULT_THRESHOLD, gate_summary, review_targets
from .ingest import build_seed_graph
from .judge import judge_all_unmatched, save_judge_report
from .llm import LLMConfig
from .taxonomy import load_taxonomy


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    skills_path = Path(args[0]) if args else Path("data/skillsdataset.json")
    jds_path = Path(args[1]) if len(args) > 1 else Path("data/jds")
    auto = "--auto" in sys.argv
    skip_judge = "--no-judge" in sys.argv  # reuse existing graph.json

    taxonomy = load_taxonomy()
    sg, stats = build_seed_graph(
        skills_path, jds_path, taxonomy=taxonomy, auto_accept_implied=auto
    )
    print(
        f"Graph: {stats['canonical']} canonical + {stats['implied']} implied skills, "
        f"{stats['jds']} JDs"
    )

    if skip_judge:
        # Reuse persisted judge edges instead of re-calling the LLM
        from .graph import SkillGraph

        prev = SkillGraph.load("output/graph.json")
        for u, v, d in prev.g.edges(data=True):
            if d.get("type") == "TRANSFERS_TO":
                if not sg.g.has_node(v):
                    continue
                sg.g.add_edge(u, v, **d)
        print("Reused TRANSFERS_TO edges from output/graph.json (--no-judge)")
    else:
        unmatched = sg.unmatched_target_skills()
        print(f"Judging {len(unmatched)} unmatched target skills...\n")
        results = judge_all_unmatched(sg, cfg=LLMConfig())
        save_judge_report(results, Path("output/judge_report.json"))

    print(f"\n=== Confidence gate (threshold {DEFAULT_THRESHOLD}) ===")
    decisions = review_targets(sg, threshold=DEFAULT_THRESHOLD, auto=auto)
    print(gate_summary(decisions))

    n_over = sum(1 for d in decisions if d.adjusted)
    print(f"\nReviewed {len(decisions)} targets, {n_over} overridden.")

    out = Path("output")
    sg.save(str(out / "graph.json"))
    print(f"Graph saved: {sg.g.number_of_nodes()} nodes, {sg.g.number_of_edges()} edges")


if __name__ == "__main__":
    main()