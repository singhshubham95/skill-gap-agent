"""M12 verification: sweep harness checks (offline — no LLM, no network).

Checks:
1. Sampling: determinism (same seed -> identical subsets), contrastive
   ordering (near-identical triple more similar than diverse), shape
   (random count, singletons, full set), dedupe by JD set.
2. End-to-end run_sweep with fake judge/synthesis/search: per-subset output
   isolation (own plan.md/graph.json/jds copies, no collision).
3. Judge-cache sharing: overlapping targets are judged once across subsets.
4. manifest.json + index.md completeness: seed/k/n/model/temperature, JD
   hashes + subset membership, plan links.
5. compute_metrics on controlled results: Jaccard, appearance, rank churn,
   superset violations, grounding flags.

Run: python -m skill_gap_agent.m12_check
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from .judge import JudgeResult
from .ranking import Gap
from .sweep import (
    Subset,
    SubsetResult,
    build_subsets,
    compute_metrics,
    run_sweep,
)
from .synthesis import SynthesizedProject

# --- fixtures ---------------------------------------------------------------

# 8 sampling files in two similarity shapes: j0-j2 near-duplicates (share
# "kafka streaming data"), j3-j7 mutually distinct.
SAMPLE_TEXTS = {
    "j0.txt": "kafka streaming data pipelines kafka streaming data",
    "j1.txt": "kafka streaming data architecture kafka streaming data",
    "j2.txt": "kafka streaming data systems kafka streaming data",
    "j3.txt": "data governance responsible ai data governance",
    "j4.txt": "graph database graph db graph database",
    "j5.txt": "reinforcement learning agents reinforcement learning",
    "j6.txt": "stakeholder management stakeholder alignment",
    "j7.txt": "technical leadership team mentoring technical leadership",
}

# 4 run files: each JD contributes at least one lexicon target skill so every
# JD shows up in its plan's JD traceability (the collision test depends on it).
RUN_JD_TEXTS = {
    "alpha.txt": "kafka streaming data pipelines kafka streaming data",
    "beta.txt": "kafka streaming data architecture kafka streaming data",
    "gamma.txt": "data governance responsible ai data governance policies",
    "delta.txt": "graph database graph db graph database knowledge",
}

judge_calls: list[str] = []


def _fake_judge(sg, target, cfg=None, **kwargs):
    """Stand-in for judge.judge_target: one TRANSFERS_TO edge, counts calls."""
    judge_calls.append(target)
    cur = sg.current_skills()
    scores = []
    if cur:
        scores = [{"skill": cur[0], "confidence": 0.5, "rationale": "fake transfer"}]
        sg.add_transfers_to(cur[0], target, 0.5, "fake transfer")
    return JudgeResult(target=target, scores=scores)


def _fake_synthesize(sg, gaps, top_n=5, cfg=None):
    """Stand-in for synthesis.synthesize_for_gaps: grounded project per gap."""
    out = []
    for g in [g for g in gaps if g.verdict not in ("bridge", "alt-bridged", "held")][:top_n]:
        skill = sg.current_skills()[0] if sg.current_skills() else "existing skills"
        out.append(
            SynthesizedProject(
                gap=g,
                title=f"Project for {g.target}",
                description=f"Reuse {skill} while learning {g.target}.",
                why="fake",
            )
        )
    return out


def _fake_search(query: str) -> list[dict]:
    return [
        {
            "title": f"Issue for {query[:20]} #{i}",
            "html_url": f"https://github.com/example/repo/issues/{i}",
            "repository_url": "https://api.github.com/repos/example/repo",
            "labels": [{"name": "good first issue"}],
            "updated_at": "2026-09-01T00:00:00Z",
            "body": "small task",
        }
        for i in (1, 2, 3)
    ]


def _fixture(tmp: Path) -> tuple[Path, Path]:
    jd_dir = tmp / "jds"
    jd_dir.mkdir(parents=True)
    for name, text in RUN_JD_TEXTS.items():
        (jd_dir / name).write_text(text, encoding="utf-8")
    skills = tmp / "skills.json"
    skills.write_text(
        json.dumps({"skills": ["Python programming experience", "SQL databases"]}),
        encoding="utf-8",
    )
    return skills, jd_dir


def check_sampling() -> None:
    files = sorted(SAMPLE_TEXTS)
    a = build_subsets(files, SAMPLE_TEXTS, seed=42, k=3, n_random=3, singletons=3)
    b = build_subsets(files, SAMPLE_TEXTS, seed=42, k=3, n_random=3, singletons=3)
    assert [s.jd_files for s in a] == [s.jd_files for s in b], "same seed must reproduce subsets"
    assert [s.id for s in a] == [f"s{i:02d}" for i in range(1, len(a) + 1)], a

    fam = {s.family: s for s in a}
    near = fam["contrastive:near-identical"]
    diverse = fam["contrastive:diverse"]
    assert near.jd_files == ["j0.txt", "j1.txt", "j2.txt"], near.jd_files
    assert len(set(near.jd_files) & set(diverse.jd_files)) <= 1, diverse.jd_files
    assert fam["contrastive:all"].jd_files == files
    assert sum(1 for s in a if s.family == "random") == 3
    assert sum(1 for s in a if s.family == "singleton") == 3

    keys = [frozenset(s.jd_files) for s in a]
    assert len(keys) == len(set(keys)), "subsets must be deduped by JD set"

    c = build_subsets(files, SAMPLE_TEXTS, seed=7, k=3, n_random=3, singletons=3)
    assert [s.jd_files for s in c] != [s.jd_files for s in a], "different seed must differ"
    print(f"sampling OK: {len(a)} subsets (near-identical={near.jd_files})")


def check_run_and_cache(tmp: Path) -> tuple[list[SubsetResult], dict]:
    skills, jd_dir = _fixture(tmp)
    out_root = tmp / "sweeps"
    judge_calls.clear()
    sweep_dir, results, metrics = run_sweep(
        skills,
        jd_dir,
        out_root=out_root,
        sweep_id="check",
        seed=42,
        k=3,
        n_random=2,
        singletons=2,
        top_n=3,
        skip_oss=False,
        use_llm_oss=False,
        seed_from_output=False,
        judge_fn=_fake_judge,
        synthesize_fn=_fake_synthesize,
        search_fn=_fake_search,
    )

    # Per-subset isolation: own artifacts, own JD copies, no collision.
    plans = []
    for r in results:
        for fname in ("plan.md", "plan.html", "graph.json", "synthesis_report.json"):
            assert (r.out_dir / fname).exists(), f"{r.subset.id} missing {fname}"
        copied = sorted(p.name for p in (r.out_dir / "jds").iterdir())
        assert copied == sorted(r.subset.jd_files), (r.subset.id, copied)
        plan = (r.out_dir / "plan.md").read_text(encoding="utf-8")
        plans.append(plan)
        for name in r.subset.jd_files:
            assert f"`{Path(name).stem}`" in plan, f"{r.subset.id} plan missing {name}"
        for name in set(RUN_JD_TEXTS) - set(r.subset.jd_files):
            assert f"`{Path(name).stem}`" not in plan, f"{r.subset.id} plan leaked {name}"
    assert len(set(plans)) == len(plans), "distinct subsets must not collide into one plan"

    # Judge cache sharing: each distinct target judged exactly once.
    counts = {t: judge_calls.count(t) for t in set(judge_calls)}
    assert counts, "fake judge should have been called"
    assert all(c == 1 for c in counts.values()), f"target judged twice: {counts}"
    called_total = sum(r.judge_called for r in results)
    reused_total = sum(r.judge_reused for r in results)
    assert called_total == len(counts), (called_total, counts)
    assert reused_total > 0, "overlapping subsets must reuse the judge cache"
    assert (sweep_dir / "_shared" / "judge_report.json").exists()

    # manifest + index completeness.
    manifest = json.loads((sweep_dir / "manifest.json").read_text(encoding="utf-8"))
    for key in ("seed", "k", "n_random", "singletons", "model", "temperature", "subsets"):
        assert key in manifest, f"manifest missing {key}"
    assert manifest["temperature"] == 0.0
    assert manifest["skills"]["sha256"] and manifest["skills"]["source"] == "json"
    assert len(manifest["jds"]) == len(RUN_JD_TEXTS)
    assert all(v.get("sha256") for v in manifest["jds"].values())
    by_id = {s["id"]: s for s in manifest["subsets"]}
    for r in results:
        m = by_id[r.subset.id]
        assert m["jds"] == sorted(r.subset.jd_files), m
        assert m["family"] == r.subset.family
        assert set(m["jds"]).issubset(set(RUN_JD_TEXTS))

    index = (sweep_dir / "index.md").read_text(encoding="utf-8")
    for r in results:
        assert r.subset.id in index, f"index missing {r.subset.id}"
        assert f"({r.subset.id}/plan.md)" in index, f"index missing plan link for {r.subset.id}"
        for name in r.subset.jd_files:
            assert f"`{name}`" in index, f"index missing {name}"
    assert "temperature 0" in index and "stability" in index

    assert (sweep_dir / "metrics.json").exists()
    print(
        f"run/cache OK: {len(results)} subsets, judge calls {called_total} new + "
        f"{reused_total} cached"
    )
    return results, metrics


def check_metrics_controlled() -> None:
    def res(sid: str, jds: list[str], targets: list[str], projects=(), skills=("Python",)):
        gaps = [
            Gap(
                target=t,
                weight=1,
                top_transfer_skill="X",
                top_transfer_confidence=0.1,
                verdict="gap",
                gap_score=round(0.9, 2),
            )
            for t in targets
        ]
        return SubsetResult(
            subset=Subset(id=sid, family="random", jd_files=jds),
            stats={},
            gaps=gaps,
            projects=list(projects),
            oss_by_gap={},
            current_skills=list(skills),
            judge_reused=0,
            judge_called=0,
            out_dir=Path("."),
        )

    # s01 ranking [T1,T2,T3]; s02 ranking [T1,T2,T4,T5,T3] (T3 at rank 5).
    # top5 sets {T1,T2,T3} vs {T1,T2,T4,T5,T3}: jaccard 3/5 = 0.6.
    r1 = res("s01", ["alpha.txt"], ["T1", "T2", "T3"])
    r2 = res("s02", ["alpha.txt", "beta.txt"], ["T1", "T2", "T4", "T5", "T3"])
    m = compute_metrics([r1, r2])
    assert m["stability"]["pairs"]["s01|s02"] == 0.6, m["stability"]
    assert m["stability"]["mean_pairwise_jaccard"] == 0.6
    assert m["appearance"] == {
        "T1": 1.0, "T2": 1.0, "T3": 1.0, "T4": 0.5, "T5": 0.5,
    }, m["appearance"]
    assert m["rank_churn"]["T3"] == {"min": 3, "max": 5, "mean": 4.0, "runs": 2}
    assert m["superset_consistency"]["pairs_checked"] == 1
    assert m["superset_consistency"]["violations"] == [], m["superset_consistency"]

    # Violation: top-5 gap of the smaller subset vanishes in the superset.
    r3 = res("s03", ["alpha.txt", "beta.txt", "gamma.txt"], ["T1", "T2", "T4", "T5"])
    m2 = compute_metrics([r1, r3])
    assert m2["superset_consistency"]["pairs_checked"] == 1
    assert m2["superset_consistency"]["violations"] == [
        {"subset": "s01", "superset": "s03", "target": "T3"}
    ], m2["superset_consistency"]

    # Grounding: a project naming no existing skill is flagged.
    good = SynthesizedProject(
        gap=r1.gaps[0], title="Use Python for T1", description="Leverage Python.", why=""
    )
    bad = SynthesizedProject(
        gap=r1.gaps[0], title="Generic app", description="Build something.", why=""
    )
    m3 = compute_metrics([res("s01", ["alpha.txt"], ["T1"], projects=(good, bad))])
    assert m3["grounding"]["projects_checked"] == 2
    assert [u["project"] for u in m3["grounding"]["ungrounded"]] == ["Generic app"]
    print("metrics OK: jaccard 0.6, appearance, churn 3->5, violation + grounding flagged")


def main() -> None:
    with tempfile.TemporaryDirectory() as td:
        check_sampling()
        check_run_and_cache(Path(td))
        check_metrics_controlled()
    print(
        "M12 CHECK PASS: sampling deterministic, outputs isolated, judge cache shared, "
        "manifest+index complete, metrics verified."
    )


if __name__ == "__main__":
    main()
