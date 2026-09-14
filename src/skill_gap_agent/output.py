"""Output node (milestone 5, specs/2-architecture.md #8).

Renders the ranked, human-readable plan to output/plan.md.
"""

from __future__ import annotations

from pathlib import Path

from .ranking import Gap, format_ranking
from .synthesis import SynthesizedProject

VERDICT_EXPLAIN = {
    "held": "**Already held** — matched to an existing skill by the matching ladder",
    "gap": "**True gap** — no meaningful transfer path; needs foundational learning + a from-scratch project",
    "partial": "**Adjacent skill** — partial transfer; a project that leverages what you already know closes it fastest",
    "bridge": "**Platform switch** — mostly transferable; a small bridging exercise suffices (not ranked for synthesis)",
    "alt-bridged": "**Alternative-satisfied** — the JDs list this brand as one interchangeable option; your depth in a comparable option from the same capability category satisfies the requirement (see note)",
    "declared-gap": "**User-declared gap** — you chose not to count the transfer path; treated as a full gap",
}


def render_plan(
    gaps: list[Gap],
    projects: list[SynthesizedProject],
    stats: dict,
) -> str:
    lines: list[str] = []
    lines.append("# Skill-Gap Plan")
    lines.append("")
    lines.append(
        f"Generated from {stats['canonical']} canonical + {stats['implied']} implied skills "
        f"vs. {stats['jds']} target job descriptions. Ranking weighs JD demand against "
        f"LLM-judged transferability (gap score = JD weight × (1 − top transfer confidence))."
    )
    lines.append("")

    # 1. Ranked gap list
    lines.append("## Ranked Gaps")
    lines.append("")
    lines.append("```")
    lines.append(format_ranking(gaps))
    lines.append("```")
    lines.append("")

    # 2. Verdict breakdown
    lines.append("## Gap Verdicts")
    lines.append("")
    for g in gaps:
        lines.append(f"### {g.target} — {g.verdict} (score {g.gap_score}, {g.weight} JDs)")
        lines.append("")
        if g.verdict == "bridge":
            lines.append(
                f"Mostly transferable from **{g.top_transfer_skill}** "
                f"({g.top_transfer_confidence:.2f}): {g.rationale}"
            )
            lines.append("")
            lines.append("_Not prioritized for a dedicated project — a small bridging exercise suffices._")
        elif g.top_transfer_skill:
            lines.append(
                f"Top transfer: **{g.top_transfer_skill}** ({g.top_transfer_confidence:.2f}). "
                f"{g.rationale}"
            )
        else:
            lines.append("No transfer path identified — foundational learning required.")
        if g.note:
            lines.append(f"- _Gate note: {g.note}_")
        if g.source_jds:
            lines.append("")
            lines.append(f"**Required by {g.weight} JD(s):**")
            for jd in g.source_jds:
                lines.append(f"- `{jd}`")
        lines.append("")

    # 3. Recommended projects
    lines.append("## Recommended Projects")
    lines.append("")
    if not projects:
        lines.append("_No projects synthesized._")
    for r in projects:
        lines.append(f"### {r.title}")
        lines.append("")
        lines.append(f"**Closes gap:** {r.gap.target} ({r.gap.verdict}, score {r.gap.gap_score})")
        lines.append("")
        lines.append(r.description)
        lines.append("")
        if r.why:
            lines.append(f"_Why this project: {r.why}_")
        lines.append("")

    return "\n".join(lines)


def write_plan(
    gaps: list[Gap],
    projects: list[SynthesizedProject],
    stats: dict,
    path: str | Path = Path("output/plan.md"),
) -> Path:
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    p.write_text(render_plan(gaps, projects, stats), encoding="utf-8")
    return p