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
from .sessions import load_profile, retire_legacy_files, save_profile, session_dir
from .taxonomy import load_taxonomy


def _save_key(src: Path, key: str, saved: dict) -> None:
    """Decisions persist in the session profile (M9: the retired global
    implied_skills.json / gate_overrides.json are never created or read)."""
    profile = load_profile(src) or {}
    profile[key] = saved
    save_profile(src, profile)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    skills_path = Path(args[0]) if args else Path("data/skillsdataset.json")
    jds_path = Path(args[1]) if len(args) > 1 else Path("data/jds")
    auto = "--auto" in sys.argv
    skip_judge = "--no-judge" in sys.argv  # reuse existing graph.json

    retire_legacy_files()
    session = session_dir(skills_path, create=True)
    profile = load_profile(skills_path) or {}

    taxonomy = load_taxonomy()
    sg, stats = build_seed_graph(
        skills_path,
        jds_path,
        taxonomy=taxonomy,
        auto_accept_implied=auto,
        implied_decisions=(profile.get("implied") or None),
        implied_on_save=lambda saved: _save_key(skills_path, "implied", saved),
    )
    print(
        f"Graph: {stats['canonical']} canonical + {stats['implied']} implied skills, "
        f"{stats['jds']} JDs"
    )

    if skip_judge:
        # Reuse persisted judge edges instead of re-calling the LLM
        from .graph import SkillGraph

        prev = SkillGraph.load(str(session / "graph.json"))
        for u, v, d in prev.g.edges(data=True):
            if d.get("type") == "TRANSFERS_TO":
                if not sg.g.has_node(v):
                    continue
                sg.g.add_edge(u, v, **d)
        print(f"Reused TRANSFERS_TO edges from {session / 'graph.json'} (--no-judge)")
    else:
        unmatched = sg.unmatched_target_skills()
        print(f"Judging {len(unmatched)} unmatched target skills...\n")
        depths = {k: str(v) for k, v in (profile.get("depth") or {}).items() if v}
        results = judge_all_unmatched(sg, cfg=LLMConfig(), depths=depths)
        save_judge_report(results, session / "judge_report.json")

    print(f"\n=== Confidence gate (threshold {DEFAULT_THRESHOLD}) ===")
    decisions = review_targets(
        sg,
        threshold=DEFAULT_THRESHOLD,
        auto=auto,
        overrides={},
        on_save=lambda saved: _save_key(skills_path, "gate", saved),
    )
    print(gate_summary(decisions))

    n_over = sum(1 for d in decisions if d.adjusted)
    print(f"\nReviewed {len(decisions)} targets, {n_over} overridden.")

    out = session
    sg.save(str(out / "graph.json"))
    print(f"Graph saved: {sg.g.number_of_nodes()} nodes, {sg.g.number_of_edges()} edges")


if __name__ == "__main__":
    main()