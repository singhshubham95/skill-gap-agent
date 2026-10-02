"""Output node (milestone 5, specs/09-practice-planner.md + specs/10-flow-runner.md).

Renders the ranked, human-readable plan to output/plan.md (M5) plus
output/plan.html (M10 thin slice — same data, clickable issue links).
"""

from __future__ import annotations

import html
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
    oss_by_gap: dict[str, list] | None = None,
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

    # 4. OSS good-first-issues (M10) — per actionable gap, after projects
    for g in gaps:
        issues = (oss_by_gap or {}).get(g.target, [])
        issues = [it for it in issues if getattr(it, "url", "")]
        if not issues:
            continue
        lines.append(f"## Good-First-Issues: {g.target}")
        lines.append("")
        for it in issues:
            label_str = f" ({', '.join(it.labels)})" if getattr(it, "labels", None) else ""
            updated = f" — updated {it.updated_at[:10]}" if getattr(it, "updated_at", "") else ""
            lines.append(f"- [{it.title}]({it.url}) — {it.repo}{label_str}{updated}")
            if getattr(it, "relevance_why", ""):
                lines.append(f"  _Why: {it.relevance_why}_")
        lines.append("")

    return "\n".join(lines)


def render_plan_html(
    gaps: list[Gap],
    projects: list[SynthesizedProject],
    stats: dict,
    oss_by_gap: dict[str, list] | None = None,
    jd_files: dict[str, str] | None = None,
) -> str:
    """Minimal plan.html (M10 thin slice): same data as plan.md, clickable links.

    Single self-contained file, no JS. Later becomes the M11 extension
    side-panel body (specs/10-flow-runner.md). When jd_files maps a gap's
    source-JD title -> JD filename, each verdict's JD list renders as links
    to the M11 /jds/<filename> viewer (served by server.py); without the
    map (plain CLI runs) titles render as plain text as before.
    """
    esc = html.escape
    parts: list[str] = []
    parts.append("<!doctype html><html><head><meta charset='utf-8'>")
    parts.append("<title>Skill-Gap Plan</title></head><body>")
    parts.append("<h1>Skill-Gap Plan</h1>")
    parts.append(
        f"<p>Generated from {stats.get('canonical', '?')} canonical + "
        f"{stats.get('implied', '?')} implied skills vs. "
        f"{stats.get('jds', '?')} target job descriptions.</p>"
    )
    parts.append("<h2>Ranked Gaps</h2><pre>")
    parts.append(esc(format_ranking(gaps)))
    parts.append("</pre>")
    parts.append("<h2>Gap Verdicts</h2>")
    for g in gaps:
        parts.append(f"<h3>{esc(g.target)} — {esc(g.verdict)} "
                       f"(score {g.gap_score}, {g.weight} JDs)</h3>")
        if g.top_transfer_skill:
            parts.append(
                f"<p>Top transfer: <strong>{esc(g.top_transfer_skill)}</strong> "
                f"({g.top_transfer_confidence:.2f}). {esc(g.rationale)}</p>"
            )
        else:
            parts.append("<p>No transfer path identified.</p>")
        if g.note:
            parts.append(f"<p><em>Gate note: {esc(g.note)}</em></p>")
        if g.source_jds:
            parts.append(f"<p><strong>Required by {g.weight} JD(s):</strong></p><ul>")
            for jd in g.source_jds:
                fname = (jd_files or {}).get(jd)
                if fname:
                    parts.append(
                        f"<li><a href='/jds/{esc(fname, quote=True)}'>{esc(jd)}</a></li>"
                    )
                else:
                    parts.append(f"<li>{esc(jd)}</li>")
            parts.append("</ul>")
    parts.append("<h2>Recommended Projects</h2>")
    if not projects:
        parts.append("<p><em>No projects synthesized.</em></p>")
    for r in projects:
        parts.append(f"<h3>{esc(r.title)}</h3>")
        parts.append(
            f"<p><strong>Closes gap:</strong> {esc(r.gap.target)} "
            f"({esc(r.gap.verdict)}, score {r.gap.gap_score})</p>"
        )
        parts.append(f"<p>{esc(r.description)}</p>")
        if r.why:
            parts.append(f"<p><em>Why this project: {esc(r.why)}</em></p>")
    if oss_by_gap:
        parts.append("<h2>Good-First-Issues</h2>")
        for g in gaps:
            issues = [it for it in (oss_by_gap.get(g.target, [])) if getattr(it, "url", "")]
            if not issues:
                continue
            parts.append(f"<h3>{esc(g.target)}</h3><ul>")
            for it in issues:
                label_str = f" ({esc(', '.join(it.labels))})" if getattr(it, "labels", None) else ""
                updated = f" — updated {esc(it.updated_at[:10])}" if getattr(it, "updated_at", "") else ""
                parts.append(
                    f"<li><a href='{esc(it.url, quote=True)}'>{esc(it.title)}</a> — "
                    f"{esc(it.repo)}{label_str}{updated}"
                    + (f"<br><em>Why: {esc(it.relevance_why)}</em>" if getattr(it, "relevance_why", "") else "")
                    + "</li>"
                )
            parts.append("</ul>")
    parts.append("</body></html>")
    return "\n".join(parts)


def write_plan(
    gaps: list[Gap],
    projects: list[SynthesizedProject],
    stats: dict,
    path: str | Path = Path("output/plan.md"),
    oss_by_gap: dict[str, list] | None = None,
) -> Path:
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    p.write_text(render_plan(gaps, projects, stats, oss_by_gap), encoding="utf-8")
    return p


def write_plan_html(
    gaps: list[Gap],
    projects: list[SynthesizedProject],
    stats: dict,
    oss_by_gap: dict[str, list] | None = None,
    path: str | Path = Path("output/plan.html"),
    jd_files: dict[str, str] | None = None,
) -> Path:
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    p.write_text(render_plan_html(gaps, projects, stats, oss_by_gap, jd_files), encoding="utf-8")
    return p