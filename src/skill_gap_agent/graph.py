"""Graph schema: node/edge models and the networkx graph builder.

Store-agnostic per specs/architecture.md — the same shape maps 1:1 onto Neo4j
later (deferred-enhancements #1).
"""

from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel, Field
import networkx as nx


class SkillSource(str, Enum):
    CURRENT = "current"
    TARGET = "target"


class Skill(BaseModel):
    name: str
    category: str = "uncategorized"
    source: SkillSource


class JD(BaseModel):
    title: str
    company: str = ""
    raw_text_ref: str = ""  # path or id of the source JD text


class Project(BaseModel):
    title: str
    description: str = ""
    type: str = "standalone"  # v1: standalone only (oss_issue deferred)


class SkillGraph:
    """networkx-backed graph with the schema from specs/architecture.md.

    Nodes: Skill, JD, Project. Edges: HAS_SKILL, REQUIRES{weight},
    TRANSFERS_TO{confidence, rationale}, CLOSES_GAP.
    """

    def __init__(self) -> None:
        self.g = nx.DiGraph()

    # -- nodes -------------------------------------------------------------

    def add_skill(self, skill: Skill) -> None:
        self.g.add_node(f"skill:{skill.name}", kind="Skill", **skill.model_dump())

    def add_jd(self, jd: JD) -> str:
        node_id = f"jd:{jd.title}"
        self.g.add_node(node_id, kind="JD", **jd.model_dump())
        return node_id

    def add_project(self, project: Project) -> str:
        node_id = f"project:{project.title}"
        self.g.add_node(node_id, kind="Project", **project.model_dump())
        return node_id

    # -- edges -------------------------------------------------------------

    def add_has_skill(self, skill_name: str) -> None:
        self.g.add_edge("user", f"skill:{skill_name}", type="HAS_SKILL")

    def add_requires(self, jd_node: str, skill_name: str, weight: int = 1) -> None:
        target = f"skill:{skill_name}"
        if self.g.has_edge(jd_node, target):
            self.g[jd_node][target]["weight"] += weight
        else:
            self.g.add_edge(jd_node, target, type="REQUIRES", weight=weight)

    def add_transfers_to(
        self, from_skill: str, to_skill: str, confidence: float, rationale: str
    ) -> None:
        self.g.add_edge(
            f"skill:{from_skill}",
            f"skill:{to_skill}",
            type="TRANSFERS_TO",
            confidence=confidence,
            rationale=rationale,
        )

    def add_closes_gap(self, project_node: str, skill_name: str) -> None:
        self.g.add_edge(project_node, f"skill:{skill_name}", type="CLOSES_GAP")

    # -- queries (smoke-test level; ranking comes in milestone 5) -----------

    def current_skills(self) -> list[str]:
        return [
            d["name"]
            for _, d in self.g.nodes(data=True)
            if d.get("kind") == "Skill" and d.get("source") == SkillSource.CURRENT
        ]

    def target_skills(self) -> list[str]:
        return [
            d["name"]
            for _, d in self.g.nodes(data=True)
            if d.get("kind") == "Skill" and d.get("source") == SkillSource.TARGET
        ]

    def unmatched_target_skills(self) -> list[str]:
        """Target skills with no exact HAS_SKILL match — judge-node input."""
        current = {s.lower() for s in self.current_skills()}
        return [s for s in self.target_skills() if s.lower() not in current]

    def requires_weights(self) -> dict[str, int]:
        """Skill name -> total REQUIRES weight across JDs."""
        weights: dict[str, int] = {}
        for _, tgt, d in self.g.edges(data=True):
            if d.get("type") == "REQUIRES":
                name = self.g.nodes[tgt]["name"]
                weights[name] = weights.get(name, 0) + d.get("weight", 1)
        return weights

    # -- persistence ---------------------------------------------------------

    def save(self, path: str) -> None:
        from networkx.readwrite import json_graph

        data = json_graph.node_link_data(self.g, edges="links")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load(cls, path: str) -> "SkillGraph":
        from networkx.readwrite import json_graph

        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        sg = cls()
        sg.g = json_graph.node_link_graph(data, edges="links")
        return sg