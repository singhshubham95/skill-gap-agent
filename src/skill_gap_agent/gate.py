"""Confidence gate (milestone 4, specs/2-architecture.md #5).

Human-in-the-loop review of the judge's uncertain verdicts — redesigned after
user feedback. Design principle: the user lacks the target skill by definition,
so they cannot judge the LLM's semantic-transfer score. The gate therefore asks
**self-assessment questions only the user can answer**:

- DEPTH: how deep is their real experience with the *source* (top-transfer)
  skill? The judge scored similarity but implicitly assumed a proficiency
  level the CV doesn't state. Final confidence = judge score × depth factor.
- INTENT: does the user want this skill area counted toward their profile?
  "No" marks the target an explicit, user-declared gap regardless of score.

Scope: top TRANSFERS_TO edge per target skill (it determines the verdict).
Threshold: 0.75 (data-driven from milestone-3 edge distribution).
Decisions persist to output/gate_overrides.json; applied silently on re-runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .graph import SkillGraph

DEFAULT_THRESHOLD = 0.75
DEFAULT_OVERRIDES_PATH = Path("output/gate_overrides.json")

# Depth level -> multiplier on the judge's confidence.
DEPTH_FACTORS = {
    "1": 0.3,  # touched it once / awareness only
    "2": 0.6,  # basic: tutorials, small use
    "3": 0.85,  # working proficiency: real project use
    "4": 1.0,  # strong: multiple production projects
    "5": 1.0,  # expert (judge score already assumes strong source depth)
}

DEPTH_LABELS = {
    "1": "awareness only",
    "2": "basic (tutorials, small use)",
    "3": "working proficiency (real project use)",
    "4": "strong (multiple production projects)",
    "5": "expert",
}


@dataclass
class GateDecision:
    target: str
    top_skill: str
    judge_confidence: float
    final_confidence: float
    adjusted: bool
    depth: str = ""
    intent: str = ""  # "count" | "declared-gap" | ""
    note: str = ""


def load_overrides(path: str | Path = DEFAULT_OVERRIDES_PATH) -> dict[str, dict]:
    """Persisted decisions: target -> {final_confidence, depth, intent, note}."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _bare(name: str) -> str:
    return name.removeprefix("skill:")


def _top_edge(sg: SkillGraph, target: str) -> tuple[dict, str] | None:
    """Top TRANSFERS_TO in-edge for a target: (edge data, source node id)."""
    edges = [
        (d, u)
        for u, _, d in sg.g.in_edges(f"skill:{target}", data=True)
        if d.get("type") == "TRANSFERS_TO"
    ]
    if not edges:
        return None
    return max(edges, key=lambda e: e[0]["confidence"])


def _apply_decision(
    sg: SkillGraph,
    target: str,
    top_skill: str,
    final_conf: float,
    depth: str,
    intent: str,
    note: str,
) -> None:
    """Write the decision back onto the TRANSFERS_TO edge as properties."""
    src = top_skill if top_skill.startswith("skill:") else f"skill:{top_skill}"
    tgt = target if target.startswith("skill:") else f"skill:{target}"
    edge = sg.g[src][tgt]
    edge["confidence"] = final_conf
    edge["gate_depth"] = depth
    edge["gate_intent"] = intent
    if note:
        edge["gate_note"] = note


def review_targets(
    sg: SkillGraph,
    threshold: float = DEFAULT_THRESHOLD,
    overrides_path: str | Path = DEFAULT_OVERRIDES_PATH,
    auto: bool = False,
) -> list[GateDecision]:
    """Review the top TRANSFERS_TO edge of each sub-threshold target skill.

    Asks self-assessment (depth + intent), not score correction. Persisted
    decisions are applied silently. Returns all decisions.
    """
    weights = sg.requires_weights()
    saved = load_overrides(overrides_path)
    decisions: list[GateDecision] = []
    pending: list[tuple[str, dict]] = []

    for target in sorted(sg.target_skills()):
        top = _top_edge(sg, target)
        if top is None:
            continue
        d, src = top
        conf = float(d["confidence"])

        if target in saved:  # apply persisted decision silently
            sv = saved[target]
            final = float(sv["final_confidence"])
            decisions.append(
                GateDecision(target, _bare(src), conf, final, final != conf,
                             sv.get("depth", ""), sv.get("intent", ""),
                             sv.get("note", ""))
            )
            _apply_decision(sg, target, src, final, sv.get("depth", ""),
                            sv.get("intent", ""), sv.get("note", ""))
        elif conf < threshold:
            pending.append((target, {"src": src, "conf": conf, "data": d}))
        else:
            decisions.append(GateDecision(target, _bare(src), conf, conf, False))

    if pending and not auto:
        print(f"\n=== Confidence gate: {len(pending)} uncertain verdicts "
              f"(top-edge confidence < {threshold}) ===")
        print("You know your OWN experience best — answer about the source skill,\n"
              "not the target skill you haven't learned yet.\n")

    for target, info in pending:
        src_bare = _bare(info["src"])
        if auto:
            decisions.append(GateDecision(target, src_bare, info["conf"], info["conf"], False))
            continue

        print(f"  [{target}]  required by {weights.get(target, 0)} JDs")
        print(f"    judge: {info['conf']:.2f} transfer from your '{src_bare}'")
        print(f"    rationale: {info['data'].get('rationale', '')[:140]}")

        # Q1: depth of experience with the SOURCE skill
        while True:
            ans = input(f"    Your real depth with '{src_bare}' [1-5, s=skip]: ").strip().lower()
            if ans in DEPTH_FACTORS or ans == "s":
                break
        if ans == "s":
            decisions.append(GateDecision(target, src_bare, info["conf"], info["conf"],
                                          False, note="review skipped"))
            continue
        depth = ans

        # Q2: intent — count this skill area toward the profile?
        while True:
            intent = input(f"    Count '{target}' as a skill area you want? "
                           "[y=count toward profile / n=explicit gap]: ").strip().lower()
            if intent in ("y", "n"):
                break

        final = round(info["conf"] * DEPTH_FACTORS[depth], 2)
        note = f"depth={depth} ({DEPTH_LABELS[depth]})"
        if intent == "n":
            note += "; user-declared gap (not counted)"
        _apply_decision(sg, target, info["src"], final, depth,
                        "count" if intent == "y" else "declared-gap", note)
        saved[target] = {
            "final_confidence": final,
            "depth": depth,
            "intent": "count" if intent == "y" else "declared-gap",
            "note": note,
        }
        decisions.append(GateDecision(target, src_bare, info["conf"], final,
                                      final != info["conf"], depth,
                                      "count" if intent == "y" else "declared-gap", note))
        print(f"    -> final confidence: {info['conf']:.2f} x {DEPTH_FACTORS[depth]} = {final:.2f}\n")

    if not auto and pending:
        p = Path(overrides_path)
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(dict(sorted(saved.items())), indent=2), encoding="utf-8")
        print(f"Decisions saved to {p}")

    return decisions


def gate_summary(decisions: list[GateDecision]) -> str:
    """One-line-per-target summary for the run log."""
    lines = []
    for d in decisions:
        if d.intent == "declared-gap":
            flag = "USER-DECLARED GAP"
        elif d.adjusted:
            flag = f"depth-adjusted (x{DEPTH_FACTORS.get(d.depth, '?')})"
        else:
            flag = "confirmed"
        lines.append(f"  {d.target:25} {d.judge_confidence:.2f} -> {d.final_confidence:.2f}  [{flag}]")
    return "\n".join(lines)