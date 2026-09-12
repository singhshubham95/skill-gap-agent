"""Milestone 2 verification: run ingestion + target-ingestion on seed data,
print the frequency tally, and sanity-check against the manual run.

Run: python -m skill_gap_agent.m2_check
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

from .ingest import build_seed_graph
from .normalize import canonical_term


def main() -> None:
    skills_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/skillsdataset.json")
    jds_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/jds")

    sg, stats = build_seed_graph(skills_path, jds_path)
    print(f"ingestion: {stats['raw']} raw phrases -> {stats['canonical']} canonical skills")
    print(f"target-ingestion: {stats['jds']} JDs -> {stats['target_skills']} target skills")

    # Frequency tally (the manual run's "X/13 JDs" numbers)
    weights = sg.requires_weights()
    n_jds = stats["jds"]
    print(f"\nFrequency tally (skill: n/{n_jds} JDs), top 25:")
    for name, w in sorted(weights.items(), key=lambda kv: -kv[1])[:25]:
        print(f"  {name}: {w}/{n_jds}")

    # Unmatched target skills = judge-node input (milestone 3)
    unmatched = sg.unmatched_target_skills()
    print(f"\nUnmatched target skills ({len(unmatched)}):")
    for name in sorted(unmatched):
        print(f"  {name} ({weights.get(name, 0)}/{n_jds})")

    # Normalization spot-check
    print("\nCanonical-term spot checks:")
    samples = [
        "Docker (Dockerfile authoring, image build/tag/push/pull, registries)",
        "Core libraries: NumPy, pandas, Requests, Jupyter",
        "Advanced SQL: joins, grouping, window/partition functions, WITH/CTEs, array/struct unnesting",
        "Binary classification (large-scale, one-model-per-class reformulation of multi-label problems)",
        "Weights & Biases (experiment tracking, Sweeps, Artifacts)",
    ]
    for s in samples:
        print(f"  {s[:60]!r} -> {canonical_term(s)!r}")

    out = Path("output"); out.mkdir(exist_ok=True)
    sg.save(str(out / "graph.json"))
    print(f"\nGraph saved: {sg.g.number_of_nodes()} nodes, {sg.g.number_of_edges()} edges")


if __name__ == "__main__":
    main()