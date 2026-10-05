"""Gap ranking (milestone 5, specs/08-gap-measurer.md S5).

Transferability-aware ranking: for each target skill (gap candidate), combine
JD demand (REQUIRES weight) with the gate-adjusted transfer confidence from
its top TRANSFERS_TO edge.

Verdict model (specs/08-gap-measurer.md §Ranking — the authoritative list):
- held            -> matched to a current skill by the matching ladder (not a gap)
- bridge          -> high transfer: platform switch (low urgency)
- alt-bridged     -> belongs to an any-of alternative group (e.g. cloud
  platform: AWS/Azure/GCP) and the user holds another member — the JD's
  capability intent is satisfied even though this brand is missing
- partial         -> adjacent skill (medium urgency, leverage what transfers)
- gap             -> no/low transfer: true gap (high urgency)
- declared-gap    -> user answered "not counted" at the gate: full urgency

Score: gap_score = weight * (1 - top_transfer_confidence), so a skill needed
by many JDs with no transfer path ranks highest. Declared-gap targets (user
said "not counted") keep full urgency regardless of transfer score.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import SkillGraph
from .llm import LABEL_LLM, LABEL_LLM_CACHED, LABEL_RULE, rule_unavailable_label
from .requirements import alternative_satisfied

# Verdict bands on top-transfer confidence (post-gate).
BRIDGE_THRESHOLD = 0.7  # >= this: platform switch, mostly transferable
PARTIAL_THRESHOLD = 0.4  # >= this: adjacent skill; below: true gap


@dataclass
class Gap:
    target: str
    weight: int  # JD demand
    top_transfer_skill: str
    top_transfer_confidence: float | None  # None = never judged (M15 "unjudged")
    verdict: str  # "held" | "alt-bridged" | "bridge" | "partial" | "gap" | "declared-gap" | "unjudged"
    gap_score: float  # weight * (1 - confidence); unjudged rows: weight alone
    rationale: str = ""
    note: str = ""  # gate note (depth/intent) if any
    alt_group: str = ""  # alternative group name if alt-bridged
    source_jds: list[str] = field(default_factory=list)  # JD titles requiring this skill
    provenance: str = ""  # M15 label: LLM / LLM (cached) / Rule-based / Rule-based (LLM unavailable — …)


def _source_jds(sg: SkillGraph, target: str) -> list[str]:
    """Titles of JD nodes with a REQUIRES edge into this target skill."""
    return sorted(
        u.removeprefix("jd:")
        for u, _, d in sg.g.in_edges(f"skill:{target}", data=True)
        if d.get("type") == "REQUIRES"
    )


def rank_gaps(
    sg: SkillGraph, unjudged: dict[str, str | None] | None = None
) -> list[Gap]:
    """Rank all target skills by gap_score = weight * (1 - top transfer).

    unjudged (M15): targets whose judge call was skipped or failed, mapped
    to its failure reason (None = deliberately not judged). Those rows
    render verdict "unjudged" with confidence None — a missing edge must
    never read as a measured confidence-0 gap
    (specs/05-ai-caller.md §LLM presence policy).
    """
    weights = sg.requires_weights()
    gaps: list[Gap] = []
    unjudged = unjudged or {}

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
                    provenance=LABEL_RULE,
                    source_jds=_source_jds(sg, target))
            )
            continue

        edges = [
            (d, u)
            for u, _, d in sg.g.in_edges(f"skill:{target}", data=True)
            if d.get("type") == "TRANSFERS_TO"
        ]
        if edges:
            # Ties prefer the reused edge (M15): when a cache-reused score
            # equals a re-judged one — the M12 purity insight says they are
            # the same value — the honest label is "LLM (cached)", not
            # freshly-judged.
            d, src = max(
                edges, key=lambda e: (e[0]["confidence"], 1 if e[0].get("cached") else 0)
            )
            conf = float(d["confidence"])
            top_skill = src.removeprefix("skill:")
            rationale = d.get("rationale", "")
            note = d.get("gate_note", "")
            intent = d.get("gate_intent", "")
            if intent == "declared-gap":
                provenance = LABEL_RULE  # the user's declaration, not a score
            else:
                provenance = LABEL_LLM_CACHED if d.get("cached") else LABEL_LLM
        elif target in unjudged and unjudged[target] != "no candidates":
            # M15: never judged (rule-based mode / judge failure) — labeled,
            # weight-ranked, and never scored as a measured 0.0 confidence.
            reason = unjudged[target]
            gaps.append(
                Gap(target=target, weight=weight,
                    top_transfer_skill="", top_transfer_confidence=None,
                    verdict="unjudged", gap_score=float(weight),
                    note=("" if reason is None else str(reason)),
                    provenance=(LABEL_RULE if reason is None
                                else rule_unavailable_label(str(reason))),
                    source_jds=_source_jds(sg, target))
            )
            continue
        else:
            # No transfer edges. Either the LLM judged and found none
            # (labeled LLM), or the target structurally had no candidates
            # ("no candidates" — rule-based matching, a true 0 by absence).
            conf, top_skill, rationale, note, intent = 0.0, "", "", "", ""
            provenance = LABEL_RULE if target in unjudged else LABEL_LLM

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
                provenance=provenance,
                alt_group=alt_group if intent != "declared-gap" and verdict == "alt-bridged" else "",
                source_jds=_source_jds(sg, target))
        )

    gaps.sort(key=lambda g: (-g.gap_score, g.target))
    return gaps


def format_ranking(gaps: list[Gap]) -> str:
    """Human-readable ranking table for the run log."""
    lines = ["  score  JDs  verdict        target <- top transfer"]
    for g in gaps:
        if g.top_transfer_confidence is None:
            transfer = "unjudged"
        else:
            transfer = (
                f"{g.top_transfer_skill or '—'} ({g.top_transfer_confidence:.2f})"
            )
        lines.append(
            f"  {g.gap_score:5.2f}  {g.weight:3d}  {g.verdict:13} "
            f"{g.target:25} <- {transfer}"
        )
    return "\n".join(lines)