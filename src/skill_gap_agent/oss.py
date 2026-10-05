"""OSS issue sourcing (M10 thin slice, specs/09-practice-planner.md S6).

Per top gap (default top-5 non-bridge gaps, same filter as
`synthesis.synthesize_for_gaps`): curated repo list -> GitHub Search Issues
(`label:"good first issue"` + keywords) -> S2 relevance filter using the
gap's TRANSFERS_TO rationale + background grounding -> persist.

Thin-slice search loop (2 attempts max per gap):
  attempt 0: strict query — label + full gap keywords + language:python,
             results re-ranked to prefer CURATED_REPOS.
  attempt 1 (if <3 raw results): broadened query — first token only, no
             language filter (global fallback).

End goal (not this slice): a search-and-reason loop that refines queries
over a few attempts using LLM feedback (e.g. reformulate keywords from
TRANSFERS_TO rationales, per-repo topic search, stale/assigned detection).
That loop lives here once end-to-end holds — see specs/03-milestones.md
Deferred #3 (quality filtering remains deferred).

Auth: GITHUB_TOKEN via secrets.py keyring pattern (env var -> keyring);
None = unauthenticated (works for smoke tests, stricter rate limits).
Network: stdlib urllib only (no new dependency; spec allows
requests-or-urllib). No pagination / ETag handling in the thin slice.

Cache: output/oss_issues.json {gap_target: {query, attempts, timestamp,
issues:[...]}} — same override-file pattern as judge_report.json /
gate_overrides.json. Re-runs reuse silently (zero GitHub API calls).

Writes Project nodes (type="oss_issue", url/repo/labels/updated_at) +
CLOSES_GAP edges (reused unchanged).
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .graph import Project, SkillGraph
from .llm import (
    LABEL_LLM,
    LABEL_LLM_CACHED,
    LABEL_RULE,
    LLMConfig,
    judge,
    rule_unavailable_label,
)
from .ranking import Gap
from .secrets import get_secret

OSS_CACHE_PATH = Path("output/oss_issues.json")
GITHUB_SEARCH_URL = "https://api.github.com/search/issues"
PER_PAGE = 10
MAX_ATTEMPTS = 2

# Thin-slice curated list (~15 GenAI/Python/data repos covering the seed
# gaps: frameworks, LLM tooling, MLOps/orchestration, data quality/governance,
# streaming). Used as a *preference* re-rank, not a hard filter — hard
# filtering to curated repos leaves niche gaps (e.g. Data governance) with
# 0 results, failing the thin-slice done criteria (3-5 issues per top gap).
CURATED_REPOS: list[str] = [
    "langchain-ai/langchain",
    "langchain-ai/langgraph",
    "microsoft/autogen",
    "crewAIInc/crewAI",
    "run-llama/llama_index",
    "huggingface/transformers",
    "pytorch/pytorch",
    "tensorflow/tensorflow",
    "mlflow/mlflow",
    "apache/airflow",
    "prefecthq/prefect",
    "apache/spark",
    "great-expectations/great_expectations",
    "datahub-project/datahub",
    "apache/kafka",
]

FILTER_SYSTEM_PROMPT = (
    "You are a relevance filter for a career-gap learning plan. "
    "Given a missing skill and candidate GitHub good-first-issues, keep only "
    "the issues where working on them would teach the missing skill. "
    "Prefer small, well-scoped issues. Respond with ONLY a valid JSON object."
)

FILTER_PROMPT_TEMPLATE = """Missing skill (gap): "{target}" (required by {weight} job descriptions).
Why it matters / transfer context:
{transfers}

Person's background (for grounding):
{background}

Candidate GitHub issues:
{candidates}

Keep the 3-5 MOST relevant issues for learning "{target}". Drop unrelated,
mega-epics, or discussion-only threads.

Respond with JSON exactly like:
{{"relevant": [{{"url": "<exact issue url from candidates>", "why": "<1 sentence>"}}]}}"""


@dataclass
class OssIssue:
    gap: str
    title: str
    url: str
    repo: str = ""
    labels: list[str] = field(default_factory=list)
    updated_at: str = ""
    body: str = ""
    relevance_why: str = ""
    error: str | None = None
    provenance: str = ""  # M15 label (llm.py): LLM / LLM (cached) / Rule-based / …


def build_query(gap_target: str, attempt: int = 0) -> str:
    """Build the GitHub Search Issues `q` param for an attempt.

    attempt 0 (strict): label + full target keywords + language:python.
    attempt 1+ (broad): label + first token only, no language filter.
    """
    keywords = gap_target.strip().strip('"')
    if attempt <= 0:
        return f'label:"good first issue" {keywords} language:python'
    first = keywords.split()[0] if keywords.split() else keywords
    return f'label:"good first issue" {first}'


def _repo_from_url(url: str) -> str:
    """Extract owner/repo from a GitHub issue/API url."""
    try:
        parts = urllib.parse.urlparse(url).path.strip("/").split("/")
        # api.github.com/repos/<owner>/<repo>/issues/<n>
        if "repos" in parts:
            i = parts.index("repos")
            return f"{parts[i + 1]}/{parts[i + 2]}"
        # github.com/<owner>/<repo>/issues/<n>
        if len(parts) >= 4 and parts[2] == "issues":
            return f"{parts[0]}/{parts[1]}"
    except (IndexError, ValueError):
        pass
    return ""


def github_search_issues(
    query: str,
    token: str | None = None,
    per_page: int = PER_PAGE,
) -> list[dict]:
    """One GitHub Search Issues call -> raw item dicts (no pagination)."""
    params = urllib.parse.urlencode(
        {"q": query, "per_page": per_page, "sort": "updated", "order": "desc"}
    )
    req = urllib.request.Request(
        f"{GITHUB_SEARCH_URL}?{params}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "skill-gap-agent-m10",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload.get("items", [])


def _raw_to_issue(gap_target: str, item: dict) -> OssIssue:
    repo = _repo_from_url(item.get("repository_url", "") or item.get("html_url", ""))
    labels = [
        lb.get("name", "") for lb in item.get("labels", []) if isinstance(lb, dict)
    ]
    return OssIssue(
        gap=gap_target,
        title=str(item.get("title", "")).strip(),
        url=str(item.get("html_url", "")).strip(),
        repo=repo,
        labels=labels,
        updated_at=str(item.get("updated_at", "")),
        body=str(item.get("body", "") or "")[:500],
    )


def _prefer_curated(issues: list[OssIssue]) -> list[OssIssue]:
    """Stable re-rank: curated-repo issues first, then the rest."""
    curated = {r.lower() for r in CURATED_REPOS}
    return sorted(issues, key=lambda i: (i.repo.lower() not in curated, i.repo, i.title))


def load_oss_cache(path: str | Path = OSS_CACHE_PATH) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — corrupt cache = start fresh
        return {}


def save_oss_cache(cache: dict, path: str | Path = OSS_CACHE_PATH) -> Path:
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return p


def _transfer_block(gap: Gap, sg: SkillGraph) -> str:
    edges = [
        (float(d["confidence"]), u.removeprefix("skill:"), d.get("rationale", ""))
        for u, _, d in sg.g.in_edges(f"skill:{gap.target}", data=True)
        if d.get("type") == "TRANSFERS_TO"
    ]
    edges.sort(reverse=True)
    return "\n".join(f"- {s} (transfer {c:.2f}): {r}" for c, s, r in edges[:5]) or "- none"


def _background_block(sg: SkillGraph, limit: int = 25) -> str:
    skills = sorted(sg.current_skills())
    return ", ".join(skills[:limit]) + (
        f" (+{len(skills) - limit} more)" if len(skills) > limit else ""
    )


def filter_issues_relevance(
    gap: Gap,
    sg: SkillGraph,
    issues: list[OssIssue],
    cfg: LLMConfig | None = None,
) -> tuple[list[OssIssue], str | None]:
    """S2 relevance filter: one judge() call per gap.

    Returns (kept_issues, error). On LLM failure the raw top-5 are kept —
    but never silently (M15): the caller labels them and marks the run
    degraded from the returned error.
    """
    if not issues:
        return [], None
    if len(issues) <= 5:
        candidates = issues
    else:
        candidates = issues[:10]
    listing = "\n".join(
        f"- {it.title} [{it.repo}] ({it.url})\n  {it.body[:200]}" for it in candidates
    )
    prompt = FILTER_PROMPT_TEMPLATE.format(
        target=gap.target,
        weight=gap.weight,
        transfers=_transfer_block(gap, sg),
        background=_background_block(sg),
        candidates=listing,
    )
    try:
        result = judge(prompt, system=FILTER_SYSTEM_PROMPT, cfg=cfg or LLMConfig())
    except Exception as e:  # noqa: BLE001 — LLM down: keep top raw (labeled)
        return _prefer_curated(candidates)[:5], str(e)
    relevant = result.get("relevant")
    if not isinstance(relevant, list) or not relevant:
        return (
            _prefer_curated(candidates)[:5],
            "LLM filter returned no usable selection",
        )
    by_url = {it.url: it for it in candidates}
    kept: list[OssIssue] = []
    for entry in relevant:
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url", ""))
        it = by_url.get(url)
        if it is None:  # match by title fallback (model may trim urls)
            continue
        it.relevance_why = str(entry.get("why", ""))
        kept.append(it)
        if len(kept) >= 5:
            break
    if not kept:
        return (
            _prefer_curated(candidates)[:5],
            "LLM filter returned no usable selection",
        )
    return kept, None


def source_oss_for_gaps(
    sg: SkillGraph,
    gaps: list[Gap],
    top_n: int = 5,
    cfg: LLMConfig | None = None,
    cache_path: str | Path = OSS_CACHE_PATH,
    search_fn=None,
    use_llm: bool = True,
    degraded_out: list | None = None,
) -> dict[str, list[OssIssue]]:
    """Source good-first-issues for the top-n actionable gaps.

    Same gap filter as synthesize_for_gaps (excludes bridge / alt-bridged /
    held). Cache-first: cached gaps write Project nodes with zero API calls.
    Returns {gap_target: [OssIssue, ...]}.

    M15: every issue carries a provenance label (llm.py vocabulary); an LLM
    filter failure keeps the raw top-5 but labels them and appends a record
    to degraded_out (if given) — never a silent fallback.
    """
    token = get_secret("GITHUB_TOKEN")
    search = search_fn or (lambda q: github_search_issues(q, token=token))
    cache = load_oss_cache(cache_path)
    dirty = False
    targets = [g for g in gaps if g.verdict not in ("bridge", "alt-bridged", "held")][
        :top_n
    ]
    out: dict[str, list[OssIssue]] = {}

    for gap in targets:
        cached = cache.get(gap.target)
        if cached and isinstance(cached.get("issues"), list):
            issues = [OssIssue(gap=gap.target, **{k: v for k, v in it.items() if k in OssIssue.__dataclass_fields__}) for it in cached["issues"]]
            # Reused LLM output must not read as fresh (M15 provenance).
            for it in issues:
                it.provenance = LABEL_LLM_CACHED if it.relevance_why else LABEL_RULE
            out[gap.target] = issues
            _write_projects(sg, gap, issues)
            continue

        # Live search: up to MAX_ATTEMPTS with query broadening.
        raw_items: list[dict] = []
        attempts: list[str] = []
        error: str | None = None
        for attempt in range(MAX_ATTEMPTS):
            query = build_query(gap.target, attempt)
            attempts.append(query)
            try:
                raw_items = search(query)
            except Exception as e:  # noqa: BLE001 — API down/limited: keep empty
                error = str(e)
                raw_items = []
                break
            if len(raw_items) >= 3 or attempt == MAX_ATTEMPTS - 1:
                break
        issues = _prefer_curated([_raw_to_issue(gap.target, it) for it in raw_items])
        if use_llm:
            issues, filter_err = filter_issues_relevance(gap, sg, issues, cfg=cfg)
            if filter_err:
                prov = rule_unavailable_label(filter_err)
                if degraded_out is not None:
                    degraded_out.append(
                        {"touchpoint": f"oss-filter({gap.target})", "error": filter_err}
                    )
            else:
                prov = LABEL_LLM
        else:
            issues = issues[:5]
            prov = LABEL_RULE
        if error and not issues:
            issues = [OssIssue(gap=gap.target, title="", url="", error=error)]
        else:
            issues = [it for it in issues if it.url][:5]
        for it in issues:
            it.provenance = prov

        cache[gap.target] = {
            "query": attempts[-1] if attempts else "",
            "attempts": attempts,
            "timestamp": datetime.now(UTC).isoformat(),
            "issues": [
                {
                    "title": it.title,
                    "url": it.url,
                    "repo": it.repo,
                    "labels": it.labels,
                    "updated_at": it.updated_at,
                    "body": it.body,
                    "relevance_why": it.relevance_why,
                    "provenance": it.provenance,
                }
                for it in issues
            ],
        }
        dirty = True
        out[gap.target] = issues
        _write_projects(sg, gap, issues)

    if dirty:
        save_oss_cache(cache, cache_path)
    return out


def _write_projects(sg: SkillGraph, gap: Gap, issues: list[OssIssue]) -> None:
    """Persist each issue as a Project(type=oss_issue) + CLOSES_GAP edge."""
    for it in issues:
        if not it.url:
            continue
        title = f"{it.repo}#{it.url.rstrip('/').rsplit('/', 1)[-1]}: {it.title}" if it.repo else it.title
        node_id = sg.add_project(
            Project(
                title=title[:200],
                description=(it.relevance_why or it.body[:300] or f"Good-first-issue for {gap.target}"),
                type="oss_issue",
                url=it.url,
                repo=it.repo,
                labels=it.labels,
                updated_at=it.updated_at,
            )
        )
        sg.add_closes_gap(node_id, gap.target)


def save_oss_report(
    oss_by_gap: dict[str, list[OssIssue]], path: str | Path = OSS_CACHE_PATH
) -> Path:
    """Write the cache-shaped report (thin slice: cache IS the report)."""
    cache = load_oss_cache(path)
    for gap_target, issues in oss_by_gap.items():
        entry = cache.get(gap_target, {})
        entry["issues"] = [
            {
                "title": it.title,
                "url": it.url,
                "repo": it.repo,
                "labels": it.labels,
                "updated_at": it.updated_at,
                "body": it.body,
                "relevance_why": it.relevance_why,
                "provenance": it.provenance,
            }
            for it in issues
        ]
        cache[gap_target] = entry
    return save_oss_cache(cache, path)
