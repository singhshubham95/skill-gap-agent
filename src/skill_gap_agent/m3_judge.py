"""Milestone 3 runner: build graph, judge unmatched skills, save report + graph.

Run: python -m skill_gap_agent.m3_judge            # full run
     python -m skill_gap_agent.m3_judge --sample   # 5-skill calibration check
"""

from __future__ import annotations

import sys
from pathlib import Path

from .ingest import build_seed_graph
from .judge import judge_all_unmatched, save_judge_report
from .llm import LLMConfig
from .taxonomy import load_taxonomy


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    skills_path = Path(args[0]) if args else Path("data/skillsdataset.json")
    jds_path = Path(args[1]) if len(args) > 1 else Path("data/jds")
    auto = "--auto" in sys.argv
    sample = "--sample" in sys.argv

    taxonomy = load_taxonomy()
    sg, stats = build_seed_graph(
        skills_path, jds_path, taxonomy=taxonomy, auto_accept_implied=auto
    )
    print(
        f"Graph: {stats['canonical']} canonical + {stats['implied']} implied skills, "
        f"{stats['jds']} JDs"
    )

    unmatched = sg.unmatched_target_skills()
    print(f"Unmatched target skills: {len(unmatched)}")

    if sample:
        # Calibration sample: high/medium/low-weight + framework cases
        only = ["LangGraph", "MLOps", "AWS", "Fine-tuning", "Data governance"]
        only = [t for t in only if t in unmatched]
        print(f"Calibration sample: {only}\n")
    else:
        only = None
        print(f"Judging all {len(unmatched)} unmatched skills...\n")

    cfg = LLMConfig()  # GLM 5.3 Flash per specs/open-items.md
    results = judge_all_unmatched(sg, cfg=cfg, only=only)

    out = Path("output")
    save_judge_report(results, out / "judge_report.json")
    sg.save(str(out / "graph.json"))

    n_edges = sum(len(r.scores) for r in results)
    n_err = sum(1 for r in results if r.error)
    print(
        f"\nDone: {n_edges} TRANSFERS_TO edges, {n_err} errors. "
        f"Report: output/judge_report.json"
    )

    # Calibration snapshot: distribution of top confidences
    tops = [
        max(r.scores, key=lambda s: s["confidence"])["confidence"]
        for r in results
        if r.scores
    ]
    if tops:
        import statistics

        print(
            f"Calibration: top-confidence min={min(tops):.2f} "
            f"max={max(tops):.2f} mean={statistics.mean(tops):.2f} "
            f"(want spread across 0-1, not clustered)"
        )


if __name__ == "__main__":
    main()