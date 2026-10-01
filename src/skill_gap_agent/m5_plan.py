"""Milestone 5 runner: rank gaps, synthesize projects, write the plan.

Run: python -m skill_gap_agent.m5_plan --auto [--no-judge] [--top N]
"""

from __future__ import annotations

import sys
from pathlib import Path

from .gate import DEFAULT_THRESHOLD, review_targets
from .ingest import build_seed_graph
from .judge import judge_all_unmatched, save_judge_report
from .llm import LLMConfig
from .oss import source_oss_for_gaps
from .output import write_plan, write_plan_html
from .ranking import format_ranking, rank_gaps
from .synthesis import save_synthesis_report, synthesize_for_gaps
from .taxonomy import load_taxonomy


def main() -> None:
    argv = sys.argv[1:]
    pos: list[str] = []
    skip_next = False
    for a in argv:
        if skip_next:
            skip_next = False
            continue
        if a == "--top":
            skip_next = True
            continue
        if a.startswith("--"):
            continue
        pos.append(a)
    skills_path = Path(pos[0]) if pos else Path("data/skillsdataset.json")
    jds_path = Path(pos[1]) if len(pos) > 1 else Path("data/jds")
    auto = "--auto" in sys.argv
    skip_judge = "--no-judge" in sys.argv
    top_n = 5
    if "--top" in sys.argv:
        top_n = int(sys.argv[sys.argv.index("--top") + 1])

    taxonomy = load_taxonomy()
    sg, stats = build_seed_graph(
        skills_path, jds_path, taxonomy=taxonomy, auto_accept_implied=auto
    )
    print(
        f"Graph: {stats['canonical']} canonical + {stats['implied']} implied skills, "
        f"{stats['jds']} JDs"
    )

    if skip_judge:
        from .graph import SkillGraph

        prev = SkillGraph.load("output/graph.json")
        for u, v, d in prev.g.edges(data=True):
            if d.get("type") == "TRANSFERS_TO" and sg.g.has_node(v):
                sg.g.add_edge(u, v, **d)
        print("Reused TRANSFERS_TO edges from output/graph.json (--no-judge)")
    else:
        unmatched = sg.unmatched_target_skills()
        print(f"Judging {len(unmatched)} unmatched target skills...\n")
        results = judge_all_unmatched(sg, cfg=LLMConfig())
        save_judge_report(results, Path("output/judge_report.json"))

    print(f"\n=== Confidence gate (threshold {DEFAULT_THRESHOLD}) ===")
    review_targets(sg, threshold=DEFAULT_THRESHOLD, auto=auto)

    print("\n=== Gap ranking ===")
    gaps = rank_gaps(sg)
    print(format_ranking(gaps))

    print(f"\n=== Project synthesis (top {top_n} non-bridge gaps) ===")
    projects = synthesize_for_gaps(sg, gaps, top_n=top_n, cfg=LLMConfig())

    skip_oss = "--no-oss" in sys.argv
    no_llm_oss = "--no-llm-oss" in sys.argv
    if skip_oss:
        oss_by_gap = {}
    else:
        print(f"\n=== OSS issue sourcing (top {top_n} non-bridge gaps) ===")
        oss_by_gap = source_oss_for_gaps(
            sg, gaps, top_n=top_n, cfg=LLMConfig(), use_llm=not no_llm_oss
        )

    out = Path("output")
    plan_path = write_plan(gaps, projects, stats, out / "plan.md", oss_by_gap)
    write_plan_html(gaps, projects, stats, oss_by_gap, out / "plan.html")
    save_synthesis_report(projects, out / "synthesis_report.json")
    sg.save(str(out / "graph.json"))

    print(f"\nPlan written: {plan_path}")
    print(f"Graph saved: {sg.g.number_of_nodes()} nodes, {sg.g.number_of_edges()} edges")


if __name__ == "__main__":
    main()