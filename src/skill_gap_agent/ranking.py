"""Gap ranking (milestone 5, specs/2-architecture.md #6).

Transferability-aware ranking: for each target skill (gap candidate), combine
JD demand (REQUIRES weight) with the gate-adjusted transfer confidence from
its top TRANSFERS_TO edge.

Verdict model (specs/1-system-overview.md "How Judge Output Becomes
Recommendations"):
- held            -> matched to a current skill by the matching ladder (not a gap)
- high transfer   -> platform switch / bridge (low urgency)
- alternative-bridged -> belongs to an any-of alternative group (e.g. cloud
  platform: AWS/Azure/GCP) and the user holds another member — the JD's
  capability intent is satisfied even though this brand is missing
- partial         -> adjacent skill (medium urgency, leverage what transfers)
- no/low          -> true gap (high urgency)

Score: gap_score = weight * (1 - top_transfer_confidence), so a skill needed
by many JDs with no transfer path ranks highest. Declared-gap targets (user
said "not counted") keep full urgency regardless of transfer score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import SkillGraph
from .requirements import alternative_satisfied

# Verdict bands on top-transfer confidence (post-gate).
BRIDGE_THRESHOLD = 0.7  # >= this: platform switch, mostly transferable
PARTIAL_THRESHOLD = 0.4  # >= this: adjacent skill; below: true gap


@dataclass
class Gap:
    target: str
    weight: int  # JD demand
    top_transfer_skill: str
    top_transfer_confidence: float
    verdict: str  # "held" | "alt-bridged" | "bridge" | "partial" | "gap" | "declared-gap"
    gap_score: float  # weight * (1 - confidence)
    rationale: str = ""
    note: str = ""  # gate note (depth/intent) if any
    alt_group: str = ""  # alternative group name if alt-bridged
    source_jds: list[str] = field(default_factory=list)  # JD titles requiring this skill


def _source_jds(sg: SkillGraph, target: str) -> list[str]:
    """Titles of JD nodes with a REQUIRES edge into this target skill."""
    return sorted(
        u.removeprefix("jd:")
        for u, _, d in sg.g.in_edges(f"skill:{target}", data=True)
        if d.get("type") == "REQUIRES"
    )


def rank_gaps(sg: SkillGraph) -> list[Gap]:
    """Rank all target skills by gap_score = weight * (1 - top transfer)."""
    weights = sg.requires_weights()
    gaps: list[Gap] = []

    for target in sorted(sg.target_skills()):
        weight = weights.get(target, 0)

        # Bug fix: targets the matching ladder already resolved to a current
        # skill are HELD, not gaps — the judge never scored them (no
        # TRANSFERS_TO edges), which previously read as confidence 0.0.
        held = sg.match_current(target)
        if held is not None:
            gaps.append(
                Gap(target=target, weight=weight,
                    top_transfer_skill=held, top_transfer_confidence=1.0,
                    verdict="held", gap_score=0.0, rationale="matched to current skill",
                    source_jds=_source_jds(sg, target))
            )
            continue

        edges = [
            (d, u)
            for u, _, d in sg.g.in_edges(f"skill:{target}", data=True)
            if d.get("type") == "TRANSFERS_TO"
        ]
        if edges:
            d, src = max(edges, key=lambda e: e[0]["confidence"])
            conf = float(d["confidence"])
            top_skill = src.removeprefix("skill:")
            rationale = d.get("rationale", "")
            note = d.get("gate_note", "")
            intent = d.get("gate_intent", "")
        else:
            conf, top_skill, rationale, note, intent = 0.0, "", "", "", ""

        if intent == "declared-gap":
            verdict = "declared-gap"
        else:
            alt_ok, alt_group = alternative_satisfied(sg, target)
            if alt_ok:
                verdict = "alt-bridged"
                note = (note + "; " if note else "") + \
                    f"alternative-satisfied via '{alt_group}' group"
            elif conf >= BRIDGE_THRESHOLD:
                verdict = "bridge"
            elif conf >= PARTIAL_THRESHOLD:
                verdict = "partial"
            else:
                verdict = "gap"

        gap_score = round(weight * (1 - conf), 2)
        gaps.append(
            Gap(target=target, weight=weight, top_transfer_skill=top_skill,
                top_transfer_confidence=conf, verdict=verdict,
                gap_score=gap_score, rationale=rationale, note=note,
                alt_group=alt_group if intent != "declared-gap" and verdict == "alt-bridged" else "",
                source_jds=_source_jds(sg, target))
        )

    gaps.sort(key=lambda g: (-g.gap_score, g.target))
    return gaps


def format_ranking(gaps: list[Gap]) -> str:
    """Human-readable ranking table for the run log."""
    lines = ["  score  JDs  verdict        target <- top transfer"]
    for g in gaps:
        lines.append(
            f"  {g.gap_score:5.2f}  {g.weight:3d}  {g.verdict:13} "
            f"{g.target:25} <- {g.top_transfer_skill or '—'} ({g.top_transfer_confidence:.2f})"
        )
    return "\n".join(lines)