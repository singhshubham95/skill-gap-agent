"""JD-subset sweep evaluation harness (milestone 12, specs/01-system-overview.md §M12 design).

Runs the pipeline's stage functions once per seeded JD subset and writes a
reviewable record that maps every generated plan to the exact JD subset that
produced it. Not a pipeline stage: the stages are called exactly as
`m5_plan.py` / `cli.py` call them (never re-implemented), with every artifact
path explicit:

    output/sweeps/<sweep-id>/
    ├── manifest.json   seed/k/n/model/temperature + resume & JD content hashes
    ├── index.md        reviewer entry point: subset -> JDs -> top gaps -> plan
    ├── metrics.json    stability / appearance / churn / consistency / grounding
    ├── _shared/        judge_report, gate_overrides, oss_issues, implied_skills
    └── sNN/            per-subset graph.json, plan.md, plan.html + jds/ copies
                        (the JD copies double as subset membership on disk)

Key cost property: judge, gate and OSS results are subset-independent — the
judge scores target T against the resume's current skills only, the gate asks
about the *source* skill, and the OSS query is built from the gap name — so
their caches live in `_shared/` and are reused across subsets: one judge call
per distinct target per sweep, not per subset. JD ingestion, `gap_score`
weights and synthesis are genuinely subset-dependent.

Sampling (seeded, `random.Random(seed)`): random k-subsets (default k=3) plus
contrastive subsets — the most-similar and least-similar triples by token
Jaccard, the full set, and evenly spaced singletons.

Run: python -m skill_gap_agent.sweep [--seed 42] [--k 3] [--n 6]
                                        [--singletons 4] [--top 5] [--list]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import urllib.request
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from itertools import combinations
from pathlib import Path

from .gate import DEFAULT_THRESHOLD, review_targets
from .graph import SkillGraph
from .ingest import ingest_jds, ingest_skills_json
from .judge import JudgeResult, judge_target
from .llm import PROVIDERS, LLMConfig
from .oss import OssIssue, source_oss_for_gaps
from .output import write_plan, write_plan_html
from .ranking import Gap, rank_gaps
from .synthesis import SynthesizedProject, save_synthesis_report, synthesize_for_gaps
from .taxonomy import load_taxonomy

SWEEPS_ROOT = Path("output/sweeps")
JD_SUFFIXES = (".txt", ".md")

# Shared caches: subset-independent results + user decision records. Seeded
# from output/ on first sight so earlier interactive decisions (implied-skill
# approvals, gate depth/intent) carry into every subset of the sweep.
CACHE_NAMES = (
    "judge_report.json",
    "gate_overrides.json",
    "oss_issues.json",
    "implied_skills.json",
)
RESUME_CACHE_NAMES = ("extracted_skills.json", "extracted_approvals.json")

# Synthesis/oss gap filter — mirrors synthesize_for_gaps: bridges, alt-bridged
# and held targets need no dedicated project.
ACTIONABLE_EXCLUDED = ("bridge", "alt-bridged", "held")


@dataclass
class Subset:
    """One JD subset of a sweep. `id` is assigned after dedupe (s01, s02...)."""

    id: str
    family: str  # "random" | "contrastive:*" | "singleton"
    jd_files: list[str] = field(default_factory=list)


@dataclass
class SubsetResult:
    subset: Subset
    stats: dict
    gaps: list[Gap]
    projects: list[SynthesizedProject]
    oss_by_gap: dict[str, list[OssIssue]]
    current_skills: list[str]
    judge_reused: int
    judge_called: int
    out_dir: Path


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / max(1, len(a | b))


def _mean_pairwise(tok: dict[str, set[str]], names: Sequence[str]) -> float:
    pairs = list(combinations(names, 2))
    if not pairs:
        return 0.0
    return sum(_jaccard(tok[a], tok[b]) for a, b in pairs) / len(pairs)


def build_subsets(
    jd_files: Iterable[str],
    texts: dict[str, str],
    seed: int = 42,
    k: int = 3,
    n_random: int = 6,
    singletons: int = 4,
) -> list[Subset]:
    """Seeded random k-subsets + contrastive subsets, deduped by JD set.

    Contrastive construction (deterministic): the triples with the highest and
    lowest mean pairwise token Jaccard, the full set, and evenly spaced
    singletons across the sorted pool. Random draws come from
    random.Random(seed), so (data, seed, k, n) fully determines the sweep.
    """
    pool = sorted(jd_files)
    if not pool:
        return []
    tok = {f: _tokens(texts.get(f, "")) for f in pool}
    subsets: list[Subset] = []
    seen: set[frozenset[str]] = set()

    def add(family: str, files: Sequence[str]) -> bool:
        key = frozenset(files)
        if not files or key in seen:
            return False
        seen.add(key)
        subsets.append(Subset(id="", family=family, jd_files=sorted(files)))
        return True

    # 1. Contrastive triples: most similar first, then most diverse.
    if len(pool) >= 3:
        scored = sorted(
            ((_mean_pairwise(tok, t), tuple(sorted(t))) for t in combinations(pool, 3)),
            key=lambda x: (-x[0], x[1]),
        )
        add("contrastive:near-identical", scored[0][1])
        add("contrastive:diverse", scored[-1][1])
    # 2. Contrastive full set.
    add("contrastive:all", pool)
    # 3. Random k-subsets (seeded; skips duplicates of existing subsets).
    rng = random.Random(seed)
    drawn = 0
    attempts = 0
    while drawn < n_random and attempts < max(20, n_random * 20):
        attempts += 1
        if len(pool) < k:
            break
        if add("random", rng.sample(pool, k)):
            drawn += 1
    # 4. Singletons, evenly spaced across the sorted pool.
    n_single = min(singletons, len(pool))
    if n_single > 0:
        if n_single == 1:
            idxs = [0]
        else:
            idxs = sorted({round(i * (len(pool) - 1) / (n_single - 1)) for i in range(n_single)})
        for i in idxs:
            add("singleton", [pool[i]])

    for i, s in enumerate(subsets, 1):
        s.id = f"s{i:02d}"
    return subsets


# ---------------------------------------------------------------------------
# Shared caches (judge scores are subset-independent — see module docstring)
# ---------------------------------------------------------------------------


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_caches(
    cache_dir: Path, names: Iterable[str], source_dir: Path = Path("output")
) -> dict[str, dict]:
    """Copy decision/cache files from source_dir on first sight.

    Re-runs reuse silently (repo convention): a missing cache file is seeded
    from the interactive runs' output/ artifact; an existing one is left
    alone. Returns {name: {"path", "seeded_from"}} for the manifest.
    """
    provenance: dict[str, dict] = {}
    for name in names:
        dst = cache_dir / name
        src = source_dir / name
        seeded_from = None
        if not dst.exists() and src.exists():
            shutil.copy2(src, dst)
            seeded_from = str(src)
        provenance[name] = {"path": str(dst), "seeded_from": seeded_from}
    return provenance


def load_judge_cache(path: str | Path) -> dict[str, dict]:
    """Judge cache: {target: {target, error, scores}} — judge_report.json shape."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        rows = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {
        r["target"]: r
        for r in rows
        if isinstance(r, dict) and r.get("target")
    }


def save_judge_cache(cache: dict[str, dict], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [cache[t] for t in sorted(cache)]
    p.write_text(json.dumps(rows, indent=2), encoding="utf-8")


def judge_unmatched_cached(
    sg: SkillGraph,
    cache_path: str | Path,
    judge_fn=None,
    cfg: LLMConfig | None = None,
) -> tuple[list[JudgeResult], int, int]:
    """Judge unmatched targets, replaying cached scores instead of re-calling.

    The judge scores target T against `sg.current_skills()` only (the resume
    side), so a score computed in one subset is valid in every other. Cached
    entries are replayed as TRANSFERS_TO edges; only unseen targets hit the
    LLM. Cache is persisted after each new target, so an interrupted sweep
    resumes without re-spending calls. Returns (results, n_reused, n_called).
    """
    judge_fn = judge_fn or judge_target
    cache = load_judge_cache(cache_path)
    results: list[JudgeResult] = []
    reused = called = 0

    for target in sorted(sg.unmatched_target_skills()):
        scores = (cache.get(target) or {}).get("scores") or []
        if scores:
            for s in scores:
                skill = str(s.get("skill", ""))
                if skill and sg.g.has_node(f"skill:{skill}"):
                    sg.add_transfers_to(
                        skill, target, float(s["confidence"]), str(s.get("rationale", ""))
                    )
            results.append(JudgeResult(target=target, scores=[dict(s) for s in scores]))
            reused += 1
            continue
        r = judge_fn(sg, target, cfg=cfg)
        results.append(r)
        called += 1
        if r.scores and not r.error:
            cache[target] = {"target": target, "error": None, "scores": r.scores}
            save_judge_cache(cache, cache_path)
    return results, reused, called


# ---------------------------------------------------------------------------
# Per-subset pipeline run (same stage functions as m5_plan.py / cli.py)
# ---------------------------------------------------------------------------


def _safe(text: str) -> str:
    return text.encode("ascii", "replace").decode("ascii")


def actionable(gaps: Sequence[Gap]) -> list[Gap]:
    """Gaps the plan acts on — same filter as synthesize_for_gaps."""
    return [g for g in gaps if g.verdict not in ACTIONABLE_EXCLUDED]


def run_subset(
    subset: Subset,
    skills_path: str | Path,
    jd_source_dir: str | Path,
    out_root: str | Path,
    cache_dir: str | Path,
    top_n: int = 5,
    cfg: LLMConfig | None = None,
    skip_oss: bool = False,
    use_llm_oss: bool = True,
    taxonomy=None,
    judge_fn=None,
    synthesize_fn=None,
    search_fn=None,
) -> SubsetResult:
    """Run the full pipeline for one JD subset into its own directory."""
    cfg = cfg or LLMConfig()
    out_dir = Path(out_root) / subset.id
    cache_dir = Path(cache_dir)
    jd_source_dir = Path(jd_source_dir)
    jd_dir = out_dir / "jds"
    jd_dir.mkdir(parents=True, exist_ok=True)
    for name in subset.jd_files:
        shutil.copy2(jd_source_dir / name, jd_dir / name)

    sg = SkillGraph()
    stats = ingest_skills_json(
        sg,
        skills_path,
        taxonomy=taxonomy,
        auto_accept_implied=True,
        approvals_path=cache_dir / "implied_skills.json",
    )
    stats.update(ingest_jds(sg, jd_dir))
    print(
        f"[{subset.id}] {subset.family}: {len(subset.jd_files)} JD(s) -> "
        f"{stats.get('target_skills', 0)} target skill(s)"
    )

    _results, reused, called = judge_unmatched_cached(
        sg, cache_dir / "judge_report.json", judge_fn=judge_fn, cfg=cfg
    )
    review_targets(
        sg,
        threshold=DEFAULT_THRESHOLD,
        overrides_path=cache_dir / "gate_overrides.json",
        auto=True,
    )
    gaps = rank_gaps(sg)

    synth = synthesize_fn or synthesize_for_gaps
    projects = synth(sg, gaps, top_n=top_n, cfg=cfg) if top_n > 0 else []

    oss_by_gap: dict[str, list[OssIssue]] = {}
    if not skip_oss:
        oss_by_gap = source_oss_for_gaps(
            sg,
            gaps,
            top_n=top_n,
            cfg=cfg,
            cache_path=cache_dir / "oss_issues.json",
            search_fn=search_fn,
            use_llm=use_llm_oss,
        )

    write_plan(gaps, projects, stats, out_dir / "plan.md", oss_by_gap)
    write_plan_html(gaps, projects, stats, oss_by_gap, out_dir / "plan.html")
    save_synthesis_report(projects, out_dir / "synthesis_report.json")
    sg.save(str(out_dir / "graph.json"))

    tops = ", ".join(
        f"{g.target} ({g.gap_score})" for g in actionable(gaps)[:3]
    ) or "-"
    print(f"[{subset.id}] top gaps: {_safe(tops)}")
    return SubsetResult(
        subset=subset,
        stats=stats,
        gaps=gaps,
        projects=projects,
        oss_by_gap=oss_by_gap,
        current_skills=sorted(sg.current_skills()),
        judge_reused=reused,
        judge_called=called,
        out_dir=out_dir,
    )


# ---------------------------------------------------------------------------
# Metrics (target the review; they do not replace it)
# ---------------------------------------------------------------------------


def compute_metrics(results: Sequence[SubsetResult]) -> dict:
    """Stability / appearance / churn / superset consistency / grounding.

    Top-5 sets use the actionable filter (the plan's substance): held, bridge
    and alt-bridged targets need no project. Ranks are 1-based positions in
    the full ranked list.
    """
    by_id = {r.subset.id: r for r in results}
    sids = sorted(by_id)
    top5 = {
        sid: [g.target for g in actionable(by_id[sid].gaps)][:5] for sid in sids
    }
    sets = {sid: set(v) for sid, v in top5.items()}

    sims: list[float] = []
    pairs: dict[str, float] = {}
    for a, b in combinations(sids, 2):
        union = len(sets[a] | sets[b])
        j = (len(sets[a] & sets[b]) / union) if union else 1.0
        pairs[f"{a}|{b}"] = round(j, 3)
        sims.append(j)
    stability = {
        "mean_pairwise_jaccard": round(sum(sims) / len(sims), 3) if sims else None,
        "min_pairwise_jaccard": round(min(sims), 3) if sims else None,
        "pairs": pairs,
    }

    counts: dict[str, int] = {}
    for targets in top5.values():
        for t in targets:
            counts[t] = counts.get(t, 0) + 1
    n = len(results) or 1
    appearance = {
        t: round(c / n, 3)
        for t, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    }

    ranks: dict[str, list[int]] = {}
    for sid in sids:
        for i, g in enumerate(by_id[sid].gaps, 1):
            ranks.setdefault(g.target, []).append(i)
    churn = {
        t: {
            "min": min(rs),
            "max": max(rs),
            "mean": round(sum(rs) / len(rs), 2),
            "runs": len(rs),
        }
        for t, rs in sorted(ranks.items())
    }

    # Superset consistency: for A ⊆ B, every top-5 gap of A must appear
    # anywhere in B's ranking. Violations are bugs, not opinions.
    violations: list[dict] = []
    pairs_checked = 0
    for a, b in combinations(sids, 2):
        ja = frozenset(by_id[a].subset.jd_files)
        jb = frozenset(by_id[b].subset.jd_files)
        if ja < jb:
            small_id, big_id = a, b
        elif jb < ja:
            small_id, big_id = b, a
        else:
            continue
        pairs_checked += 1
        big_targets = {g.target for g in by_id[big_id].gaps}
        for t in top5[small_id]:
            if t not in big_targets:
                violations.append(
                    {"subset": small_id, "superset": big_id, "target": t}
                )
    consistency = {"pairs_checked": pairs_checked, "violations": violations}

    # Grounding: each synthesized project should name an existing skill
    # (the synthesis prompt demands reuse "where applicable" — a miss is a
    # flag to look at, not an automatic failure).
    ungrounded: list[dict] = []
    checked = 0
    for r in results:
        skills_l = [s.lower() for s in r.current_skills]
        for p in r.projects:
            checked += 1
            text = f"{p.title} {p.description} {p.why}".lower()
            if not any(s in text for s in skills_l):
                ungrounded.append(
                    {"subset": r.subset.id, "project": p.title, "gap": p.gap.target}
                )
    grounding = {"projects_checked": checked, "ungrounded": ungrounded}

    return {
        "stability": stability,
        "appearance": appearance,
        "rank_churn": churn,
        "superset_consistency": consistency,
        "grounding": grounding,
    }


def check_gfi_links(results: Sequence[SubsetResult], timeout: float = 10.0) -> dict:
    """HEAD every distinct GFI url. Network touch — run only with --check-links."""
    urls = sorted(
        {
            it.url
            for r in results
            for issues in r.oss_by_gap.values()
            for it in issues
            if getattr(it, "url", "")
        }
    )
    out: dict[str, str] = {}
    for url in urls:
        try:
            req = urllib.request.Request(
                url, method="HEAD", headers={"User-Agent": "skill-gap-agent-sweep"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                out[url] = str(resp.status)
        except Exception as e:  # noqa: BLE001 — record, never abort the sweep
            out[url] = f"ERROR: {e}"[:120]
    return out


# ---------------------------------------------------------------------------
# Reporting: manifest.json / metrics.json / index.md
# ---------------------------------------------------------------------------


def build_manifest(
    *,
    sweep_id: str,
    seed: int,
    k: int,
    n_random: int,
    singletons: int,
    top_n: int,
    cfg: LLMConfig,
    skills_path: Path,
    extraction_source: str,
    jd_dir: Path,
    jd_files: Sequence[str],
    caches: dict[str, dict],
    subsets: Sequence[Subset],
    options: dict,
) -> dict:
    """The audit record: what produced each plan, reproducible from (seed, data).

    Subset membership is explicit per subset — `Gap.source_jds` records which
    JDs mention a gap, NOT which JDs were in the run; without membership a
    reviewer cannot tell "this JD doesn't need X" from "this JD wasn't there".
    JD hashes pin the exact inputs so a renamed/edited file invalidates an
    old sweep visibly instead of silently.
    """
    model = cfg.model or PROVIDERS.get(cfg.provider, {}).get("model", "")
    return {
        "sweep_id": sweep_id,
        "created_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "k": k,
        "n_random": n_random,
        "singletons": singletons,
        "top_n": top_n,
        "provider": cfg.provider,
        "model": model,
        "temperature": cfg.temperature,
        "skills": {
            "path": str(skills_path),
            "sha256": _sha256(skills_path),
            "source": extraction_source,
        },
        "jd_dir": str(jd_dir),
        "jd_count": len(jd_files),
        "jds": {
            name: {"sha256": _sha256(jd_dir / name), "title": Path(name).stem}
            for name in jd_files
        },
        "caches": caches,
        "options": options,
        "subsets": [
            {"id": s.id, "family": s.family, "jds": s.jd_files, "dir": s.id}
            for s in subsets
        ],
    }


def write_metrics(sweep_dir: Path, metrics: dict) -> Path:
    p = sweep_dir / "metrics.json"
    p.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return p


def write_manifest(sweep_dir: Path, manifest: dict) -> Path:
    p = sweep_dir / "manifest.json"
    p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return p


def write_index(
    sweep_dir: Path,
    manifest: dict,
    results: Sequence[SubsetResult],
    metrics: dict,
) -> Path:
    """Reviewer entry point: headline metrics + subset -> JDs -> top gaps -> plan."""
    lines: list[str] = []
    lines.append(f"# Sweep {manifest['sweep_id']} — JD-subset evaluation")
    lines.append("")
    lines.append(
        f"Seed {manifest['seed']}, k={manifest['k']}, random n={manifest['n_random']}, "
        f"singletons={manifest['singletons']}, top_n={manifest['top_n']}, "
        f"model `{manifest['model']}`, temperature {manifest['temperature']} — "
        f"skills `{manifest['skills']['path']}` "
        f"({manifest['skills']['source']}), {manifest['jd_count']} JDs in "
        f"`{manifest['jd_dir']}`. Per-JD hashes: [manifest.json](manifest.json)."
    )
    lines.append("")

    stab = metrics.get("stability", {})
    cons = metrics.get("superset_consistency", {})
    ground = metrics.get("grounding", {})
    lines.append("## Metrics (detail: [metrics.json](metrics.json))")
    lines.append("")
    lines.append(
        f"- Top-5 actionable stability: mean pairwise Jaccard "
        f"**{stab.get('mean_pairwise_jaccard')}** "
        f"(min {stab.get('min_pairwise_jaccard')})"
    )
    lines.append(
        f"- Superset consistency: **{len(cons.get('violations', []))} violation(s)** "
        f"across {cons.get('pairs_checked', 0)} subset⊆superset pair(s)"
    )
    lines.append(
        f"- Synthesis grounding: {len(ground.get('ungrounded', []))} of "
        f"{ground.get('projects_checked', 0)} project(s) name no existing skill"
    )
    links = metrics.get("gfi_links")
    if links is not None:
        ok = sum(1 for v in links.values() if v == "200")
        lines.append(f"- GFI links: {ok}/{len(links)} returned HTTP 200")
    else:
        lines.append("- GFI links: not checked (run with --check-links)")
    lines.append("")

    unstable = [t for t, rate in metrics.get("appearance", {}).items() if rate < 0.5]
    if unstable:
        lines.append(
            "Unstable gaps (in <50% of subset top-5s — look here first): "
            + ", ".join(f"`{t}`" for t in unstable)
        )
        lines.append("")

    lines.append("## Subsets")
    lines.append("")
    for r in results:
        m = next(s for s in manifest["subsets"] if s["id"] == r.subset.id)
        lines.append(f"### {r.subset.id} — {r.subset.family}")
        lines.append("")
        lines.append(
            "JDs: "
            + ", ".join(f"`{j}`" for j in m["jds"])
            + f"  (copies in [{r.subset.id}/jds/]({r.subset.id}/jds/))"
        )
        tops = [
            f"{i}. {g.target} (score {g.gap_score}, {g.verdict})"
            for i, g in enumerate(actionable(r.gaps)[:5], 1)
        ]
        lines.append("")
        lines.append("Top gaps: " + (" · ".join(tops) if tops else "_none actionable_"))
        lines.append("")
        lines.append(
            f"Plan: [plan.md]({r.subset.id}/plan.md) · "
            f"[plan.html]({r.subset.id}/plan.html) · "
            f"[graph.json]({r.subset.id}/graph.json)"
        )
        lines.append("")
    p = sweep_dir / "index.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def plan_subsets(
    jd_dir: str | Path,
    seed: int = 42,
    k: int = 3,
    n_random: int = 6,
    singletons: int = 4,
) -> list[Subset]:
    jd_dir = Path(jd_dir)
    jd_files = sorted(
        f.name for f in jd_dir.iterdir() if f.suffix.lower() in JD_SUFFIXES
    )
    texts = {
        n: (jd_dir / n).read_text(encoding="utf-8", errors="replace") for n in jd_files
    }
    return build_subsets(jd_files, texts, seed=seed, k=k, n_random=n_random, singletons=singletons)


def run_sweep(
    skills_path: str | Path,
    jd_dir: str | Path,
    out_root: str | Path = SWEEPS_ROOT,
    sweep_id: str | None = None,
    seed: int = 42,
    k: int = 3,
    n_random: int = 6,
    singletons: int = 4,
    top_n: int = 5,
    cfg: LLMConfig | None = None,
    skip_oss: bool = False,
    use_llm_oss: bool = True,
    check_links: bool = False,
    seed_from_output: bool = True,
    judge_fn=None,
    synthesize_fn=None,
    search_fn=None,
) -> tuple[Path, list[SubsetResult], dict]:
    """Build subsets, run each through the pipeline, write the sweep record."""
    cfg = cfg or LLMConfig(temperature=0.0)
    skills_path = Path(skills_path)
    jd_dir = Path(jd_dir)
    jd_files = sorted(
        f.name for f in jd_dir.iterdir() if f.suffix.lower() in JD_SUFFIXES
    )
    subsets = plan_subsets(jd_dir, seed=seed, k=k, n_random=n_random, singletons=singletons)
    if not subsets:
        raise SystemExit(f"No JD files ({', '.join(JD_SUFFIXES)}) found in {jd_dir}")

    sweep_id = sweep_id or f"{datetime.now(UTC):%Y%m%d-%H%M%S}-seed{seed}"
    sweep_dir = Path(out_root) / sweep_id
    cache_dir = sweep_dir / "_shared"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Resume input: extract ONCE before the loop (skills side must stay
    # constant across subsets). Extraction artifacts live in _shared/ and are
    # seeded from output/ so the one-time extraction cost is never re-paid.
    extraction_source = "json"
    source_dir = Path("output")
    if skills_path.suffix.lower() != ".json":
        from .resume import resume_to_skills_json

        cache_names = list(RESUME_CACHE_NAMES)
        if seed_from_output:
            seed_caches(cache_dir, cache_names)
        json_path, _stats = resume_to_skills_json(
            skills_path,
            artifact_path=cache_dir / "extracted_skills.json",
            approvals_path=cache_dir / "extracted_approvals.json",
            use_llm=True,
            auto=True,
            cfg=cfg,
        )
        skills_path = Path(json_path)
        extraction_source = "resume-extraction"

    names = list(CACHE_NAMES)
    if seed_from_output:
        caches = seed_caches(cache_dir, names, source_dir=source_dir)
    else:
        caches = {n: {"path": str(cache_dir / n), "seeded_from": None} for n in names}

    taxonomy_loaded = load_taxonomy()

    results: list[SubsetResult] = []
    for subset in subsets:
        results.append(
            run_subset(
                subset,
                skills_path=skills_path,
                jd_source_dir=jd_dir,
                out_root=sweep_dir,
                cache_dir=cache_dir,
                top_n=top_n,
                cfg=cfg,
                skip_oss=skip_oss,
                use_llm_oss=use_llm_oss,
                taxonomy=taxonomy_loaded,
                judge_fn=judge_fn,
                synthesize_fn=synthesize_fn,
                search_fn=search_fn,
            )
        )

    metrics = compute_metrics(results)
    if check_links:
        metrics["gfi_links"] = check_gfi_links(results)

    manifest = build_manifest(
        sweep_id=sweep_id,
        seed=seed,
        k=k,
        n_random=n_random,
        singletons=singletons,
        top_n=top_n,
        cfg=cfg,
        skills_path=skills_path,
        extraction_source=extraction_source,
        jd_dir=jd_dir,
        jd_files=jd_files,
        caches=caches,
        subsets=subsets,
        options={
            "skip_oss": skip_oss,
            "use_llm_oss": use_llm_oss,
            "check_links": check_links,
            "seeded_from_output": seed_from_output,
        },
    )
    write_manifest(sweep_dir, manifest)
    write_metrics(sweep_dir, metrics)
    write_index(sweep_dir, manifest, results, metrics)
    return sweep_dir, results, metrics


def main() -> None:
    parser = argparse.ArgumentParser(
        description="JD-subset sweep evaluation harness (milestone 12)"
    )
    parser.add_argument(
        "skills",
        nargs="?",
        default="data/skillsdataset.json",
        help="skills JSON, or a resume file (.pdf/.docx/.txt) to extract from",
    )
    parser.add_argument("jds", nargs="?", default="data/jds")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--k", type=int, default=3, help="random subset size")
    parser.add_argument("--n", type=int, default=6, dest="n_random", help="random subset count")
    parser.add_argument("--singletons", type=int, default=4)
    parser.add_argument("--top", type=int, default=5, dest="top_n")
    parser.add_argument("--id", dest="sweep_id", default=None, help="sweep directory name")
    parser.add_argument("--no-oss", action="store_true")
    parser.add_argument("--no-llm-oss", action="store_true")
    parser.add_argument("--check-links", action="store_true", help="HTTP-check GFI urls")
    parser.add_argument(
        "--list", action="store_true", help="print the subsets and exit (no LLM calls)"
    )
    args = parser.parse_args()

    if args.list:
        for s in plan_subsets(
            args.jds,
            seed=args.seed,
            k=args.k,
            n_random=args.n_random,
            singletons=args.singletons,
        ):
            print(f"{s.id}  {s.family:28} {', '.join(s.jd_files)}")
        return

    sweep_dir, results, metrics = run_sweep(
        args.skills,
        args.jds,
        sweep_id=args.sweep_id,
        seed=args.seed,
        k=args.k,
        n_random=args.n_random,
        singletons=args.singletons,
        top_n=args.top_n,
        skip_oss=args.no_oss,
        use_llm_oss=not args.no_llm_oss,
        check_links=args.check_links,
    )
    called = sum(r.judge_called for r in results)
    reused = sum(r.judge_reused for r in results)
    print(f"\nSweep written: {sweep_dir}")
    print(f"  subsets: {len(results)} | judge calls: {called} new, {reused} cached")
    print(f"  stability (mean top-5 Jaccard): {metrics['stability']['mean_pairwise_jaccard']}")
    print(f"  review here: {sweep_dir / 'index.md'}")


if __name__ == "__main__":
    main()
