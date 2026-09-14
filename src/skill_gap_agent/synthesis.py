"""LLM project synthesis (milestone 5, specs/2-architecture.md #7).

Per gap, generate standalone project ideas grounded in the user's EXISTING
skills — the synthesis prompt receives the gap plus its top TRANSFERS_TO edges
with rationales, so ideas leverage what transfers ("reuse your ADK
orchestration patterns to learn LangGraph's graph model"), not generic advice.

Writes Project nodes + CLOSES_GAP edges back to the graph.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .graph import Project, SkillGraph
from .llm import LLMConfig, judge
from .ranking import Gap

SYSTEM_PROMPT = (
    "You are a senior engineer designing hands-on learning projects for a "
    "career-gap plan. Projects must be grounded in the person's EXISTING "
    "skills — reuse what they know, target exactly the missing skill. No "
    "generic ideas like 'build a todo app'. Respond with ONLY a valid JSON object."
)

PROMPT_TEMPLATE = """Gap to close: the person lacks "{target}" (required by {weight} target job descriptions).
Transfer verdict: {verdict}

Their relevant existing skills (with LLM-judged transferability to the gap):
{transfers}

Their broader skill background (for grounding):
{background}

Design ONE standalone project that closes this gap:
- title: short, concrete
- description: 2-3 sentences. MUST explicitly reuse specific skills from their
  background where applicable ("reuse your X to do Y while learning Z").
- why_this_project: 1-2 sentences on how it closes the gap given their transfer path.

Respond with JSON exactly like:
{{"title": "...", "description": "...", "why_this_project": "..."}}"""


@dataclass
class SynthesizedProject:
    gap: Gap
    title: str
    description: str
    why: str
    error: str | None = None


def _transfer_block(gap: Gap, sg: SkillGraph) -> str:
    """All TRANSFERS_TO edges into this gap, strongest first."""
    edges = [
        (float(d["confidence"]), u.removeprefix("skill:"), d.get("rationale", ""))
        for u, _, d in sg.g.in_edges(f"skill:{gap.target}", data=True)
        if d.get("type") == "TRANSFERS_TO"
    ]
    edges.sort(reverse=True)
    return "\n".join(f"- {s} (transfer {c:.2f}): {r}" for c, s, r in edges[:5]) or "- none"


def _background_block(sg: SkillGraph, limit: int = 25) -> str:
    skills = sorted(sg.current_skills())
    return ", ".join(skills[:limit]) + (f" (+{len(skills) - limit} more)" if len(skills) > limit else "")


def synthesize_project(
    gap: Gap, sg: SkillGraph, cfg: LLMConfig | None = None
) -> SynthesizedProject:
    prompt = (
        f'Gap to close: the person lacks "{gap.target}" '
        f"(required by {gap.weight} target job descriptions).\n"
        f"Transfer verdict: {gap.verdict}\n\n"
        f"Their relevant existing skills (with LLM-judged transferability):\n"
        f"{_transfer_block(gap, sg) or '- none identified'}\n\n"
        f"Their broader background: {_background_block(sg)}\n\n"
        "Design ONE standalone project that closes this gap:\n"
        "- title: short, concrete\n"
        '- description: 2-3 sentences. MUST explicitly reuse specific skills from '
        'their background where applicable ("reuse your X to do Y while learning Z").\n'
        "- why_this_project: 1-2 sentences on how it closes the gap given their "
        "transfer path.\n\n"
        'Respond with JSON exactly like: {"title": "...", "description": "...", '
        '"why_this_project": "..."}'
    )
    try:
        result = judge(prompt, system=SYSTEM_PROMPT, cfg=cfg or LLMConfig())
        title = str(result["title"]).strip()
        desc = str(result["description"]).strip()
        why = str(result.get("why_this_project", "")).strip()
    except Exception as e:  # noqa: BLE001
        return SynthesizedProject(gap=gap, title="", description="", why="", error=str(e))

    # Write Project node + CLOSES_GAP edge
    node_id = sg.add_project(Project(title=title, description=desc, type="standalone"))
    sg.add_closes_gap(node_id, gap.target)
    return SynthesizedProject(gap=gap, title=title, description=desc, why=why)


def synthesize_for_gaps(
    sg: SkillGraph, gaps: list[Gap], top_n: int = 5, cfg: LLMConfig | None = None
) -> list[SynthesizedProject]:
    """Synthesize projects for the top-n ranked gaps.

    Excludes bridges AND alt-bridged targets (the JD's capability intent is
    already satisfied by an alternative group member) and held skills.
    """
    results = []
    targets = [
        g for g in gaps if g.verdict not in ("bridge", "alt-bridged", "held")
    ][:top_n]
    for i, gap in enumerate(targets, 1):
        print(f"  [{i}] {gap.target} (score {gap.gap_score})...")
        r = synthesize_project(gap, sg, cfg=cfg)
        if r.error:
            print(f"      ERROR: {r.error}")
        else:
            safe = r.title.encode("ascii", "replace").decode("ascii")
            print(f"      -> {safe}")
        results.append(r)
    return results


def save_synthesis_report(results: list[SynthesizedProject], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    payload = [
        {
            "gap": r.gap.target,
            "verdict": r.gap.verdict,
            "gap_score": r.gap.gap_score,
            "title": r.title,
            "description": r.description,
            "why_this_project": r.why,
            "error": r.error,
        }
        for r in results
    ]
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")