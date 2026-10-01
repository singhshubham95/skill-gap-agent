"""M10 verification: OSS thin-slice checks (offline-friendly).

Checks (no network, no LLM required):
1. oss.py imports; CURATED_REPOS non-empty; build_query strict/broad shapes.
2. source_oss_for_gaps with a stub search_fn + use_llm=False writes
   Project(type=oss_issue) nodes + CLOSES_GAP edges, persists the cache,
   and reuses it silently (second run makes zero search calls).
3. render_plan / render_plan_html include the issue links.

Run: python -m skill_gap_agent.m10_check
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .graph import Skill, SkillGraph, SkillSource
from .oss import (
    CURATED_REPOS,
    build_query,
    source_oss_for_gaps,
)
from .output import render_plan, render_plan_html
from .ranking import Gap


def _demo_graph() -> tuple[SkillGraph, list[Gap]]:
    sg = SkillGraph()
    sg.add_skill(Skill(name="Python", source=SkillSource.CURRENT))
    sg.add_skill(Skill(name="LangGraph", source=SkillSource.TARGET))
    sg.add_skill(Skill(name="Fine-tuning", source=SkillSource.TARGET))
    sg.add_jd(__import__("skill_gap_agent.graph", fromlist=["JD"]).JD(title="jd1"))
    sg.add_requires("jd:jd1", "LangGraph", weight=4)
    sg.add_requires("jd:jd1", "Fine-tuning", weight=5)
    sg.add_transfers_to("Python", "LangGraph", 0.2, "weak transfer")
    sg.add_transfers_to("Python", "Fine-tuning", 0.3, "some transfer")
    gaps = [
        Gap(target="Fine-tuning", weight=5, top_transfer_skill="Python",
            top_transfer_confidence=0.3, verdict="gap", gap_score=3.5,
            rationale="some transfer", source_jds=["jd1"]),
        Gap(target="LangGraph", weight=4, top_transfer_skill="Python",
            top_transfer_confidence=0.2, verdict="gap", gap_score=3.2,
            rationale="weak transfer", source_jds=["jd1"]),
    ]
    return sg, gaps


def _stub_search(query: str) -> list[dict]:
    calls.append(query)
    return [
        {
            "title": f"Good first issue about {query[:20]} #{i}",
            "html_url": f"https://github.com/langchain-ai/langchain/issues/{100 + i}",
            "repository_url": "https://api.github.com/repos/langchain-ai/langchain",
            "labels": [{"name": "good first issue"}],
            "updated_at": "2026-09-01T00:00:00Z",
            "body": "A small scoped task for newcomers.",
        }
        for i in range(4)
    ]


calls: list[str] = []


def main() -> None:
    assert CURATED_REPOS, "CURATED_REPOS must be non-empty"
    strict = build_query("Fine-tuning", 0)
    broad = build_query("Fine-tuning", 1)
    assert "good first issue" in strict and "language:python" in strict, strict
    assert "good first issue" in broad and "language:python" not in broad, broad
    print(f"queries OK: strict={strict!r} broad={broad!r}")

    sg, gaps = _demo_graph()
    with tempfile.TemporaryDirectory() as tmp:
        cache = Path(tmp) / "oss_issues.json"
        out1 = source_oss_for_gaps(
            sg, gaps, top_n=2, use_llm=False, cache_path=cache, search_fn=_stub_search
        )
        n_calls_first = len(calls)
        assert n_calls_first > 0, "stub search should have been called"
        assert set(out1) == {"Fine-tuning", "LangGraph"}, set(out1)
        for target, issues in out1.items():
            assert 1 <= len(issues) <= 5, (target, len(issues))
            assert all(it.url.startswith("https://github.com/") for it in issues)

        oss_nodes = [
            (n, d) for n, d in sg.g.nodes(data=True)
            if d.get("kind") == "Project" and d.get("type") == "oss_issue"
        ]
        assert oss_nodes, "expected Project(type=oss_issue) nodes"
        closes = [
            (u, v) for u, v, d in sg.g.edges(data=True) if d.get("type") == "CLOSES_GAP"
        ]
        assert closes, "expected CLOSES_GAP edges"
        assert cache.exists(), "cache file should be written"
        payload = json.loads(cache.read_text(encoding="utf-8"))
        assert "Fine-tuning" in payload and "timestamp" in payload["Fine-tuning"]

        # Second run: cache reuse => zero new search calls.
        calls.clear()
        out2 = source_oss_for_gaps(
            sg, gaps, top_n=2, use_llm=False, cache_path=cache, search_fn=_stub_search
        )
        assert len(calls) == 0, f"cache reuse failed: {len(calls)} search calls"
        assert set(out2) == set(out1)

    stats = {"canonical": 1, "implied": 0, "jds": 1}
    md = render_plan(gaps, [], stats, out1)
    assert "Good-First-Issues" in md and "github.com" in md, "plan.md missing issues"
    html_doc = render_plan_html(gaps, [], stats, out1)
    assert "<a href=" in html_doc and "github.com" in html_doc, "plan.html missing links"
    print(
        f"M10 CHECK PASS: {len(oss_nodes)} oss_issue projects, "
        f"{len(closes)} CLOSES_GAP edges, cache reuse OK, md+html OK."
    )


if __name__ == "__main__":
    main()
