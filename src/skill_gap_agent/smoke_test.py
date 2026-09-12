"""Milestone 1 schema smoke test: load seed data, hand-build the graph,
exercise every node/edge type, save + reload.

Run: python -m skill_gap_agent.smoke_test
"""

from __future__ import annotations

import sys
from pathlib import Path

from .graph import JD, Project, Skill, SkillGraph, SkillSource
from .seed import load_jds, load_skills_json


def main() -> None:
    skills_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/skills.json")
    jds_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("data/jds")

    sg = SkillGraph()

    # 1. Seed data
    n_skills = load_skills_json(sg, skills_path) if skills_path.exists() else 0
    n_jds = load_jds(sg, jds_path) if jds_path.exists() else 0
    print(f"Loaded {n_skills} current skills, {n_jds} JDs")

    # 2. Hand-build the rest of the schema (smoke test only)
    sg.add_skill(Skill(name="LangGraph", source=SkillSource.TARGET))
    sg.add_requires("jd:example-jd", "LangGraph", weight=1)
    sg.add_transfers_to("Google ADK", "LangGraph", 0.7, "similar agent-orchestration model")
    proj = sg.add_project(Project(title="Multi-agent pipeline demo"))
    sg.add_closes_gap(proj, "LangGraph")

    # 3. Exercise queries
    print(f"current skills: {len(sg.current_skills())}")
    print(f"target skills:  {len(sg.target_skills())}")
    print(f"unmatched:      {sg.unmatched_target_skills()}")
    print(f"requires weights: {sg.requires_weights()}")

    # 4. Persistence round-trip
    out = Path("output"); out.mkdir(exist_ok=True)
    sg.save(str(out / "graph.json"))
    sg2 = SkillGraph.load(str(out / "graph.json"))
    assert sg2.g.number_of_nodes() == sg.g.number_of_nodes()
    assert sg2.g.number_of_edges() == sg.g.number_of_edges()
    print(f"round-trip OK: {sg2.g.number_of_nodes()} nodes, {sg2.g.number_of_edges()} edges")


if __name__ == "__main__":
    main()