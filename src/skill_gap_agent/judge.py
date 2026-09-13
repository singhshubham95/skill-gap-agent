"""Transferability judge node (milestone 3, specs/architecture.md #4).

For each unmatched target skill: prune to top-k candidate current skills
(keyword overlap), then one LLM call per target skill scoring transferability
against its candidates. Output: TRANSFERS_TO edges {confidence, rationale}.

Pruning keeps this at ~1 LLM call per target skill (~21 calls on seed data)
instead of naive pairwise (~21 x 119 = ~2,500).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .graph import SkillGraph
from .llm import LLMConfig, judge
from .normalize import canonical_term

SYSTEM_PROMPT = (
    "You are a skill-transferability assessor for career-gap analysis. "
    "You judge how much a person's EXISTING skill transfers to a TARGET skill "
    "they lack. Be calibrated: reserve 0.8+ for near-equivalent skills, give "
    "0.4-0.7 for partial/adjacent transfer, below 0.3 for negligible transfer. "
    "Respond with ONLY a valid JSON object."
)

PROMPT_TEMPLATE = """Target skill the person LACKS: "{target}"

Person's existing skills (candidates):
{candidates}

For each candidate, score how well it transfers to the target skill:
- confidence: 0.0-1.0 (calibrated: 0.8+ near-equivalent, 0.4-0.7 partial, <0.3 negligible)
- rationale: one short sentence

Rules:
- Score ONLY meaningful transfer; if a candidate is unrelated, confidence must be < 0.2.
- Consider depth implied by the candidate's specificity.
- Include ALL candidates in the output.

Respond with JSON exactly like:
{{"scores": [{{"skill": "<candidate name>", "confidence": 0.0, "rationale": "<short>"}}]}}"""


@dataclass
class JudgeResult:
    target: str
    scores: list[dict] = field(default_factory=list)  # {skill, confidence, rationale}
    error: str | None = None


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9+#.]+", text.lower())) - {
        "the", "and", "for", "with", "of", "in", "a", "an", "to", "on",
    }


# Lexicon hints: target skill -> patterns that identify related current skills.
# Fixes the pruner's blind spot for framework-adjacent and platform-analog
# skills where keyword overlap is zero (e.g. "LangGraph" vs "Agentic
# application development (Google ADK)"). These candidates are ALWAYS included
# alongside the keyword-overlap picks.
PRUNER_HINTS: dict[str, list[str]] = {
    "LangGraph": [r"agentic", r"agent", r"adk", r"langchain", r"orchestration", r"nl-to-sql"],
    "LangChain": [r"agentic", r"agent", r"adk", r"langgraph", r"orchestration", r"nl-to-sql"],
    "LlamaIndex": [r"agentic", r"agent", r"rag", r"retrieval", r"langchain"],
    "AutoGen": [r"agentic", r"agent", r"adk", r"orchestration"],
    "CrewAI": [r"agentic", r"agent", r"adk", r"orchestration"],
    "AWS": [r"gcp", r"google cloud", r"azure", r"cloud"],
    "AWS Bedrock": [r"vertex", r"azure openai", r"genai", r"llm", r"cloud"],
    "Azure OpenAI": [r"vertex", r"bedrock", r"llm", r"genai", r"locally hosted"],
    "Google Cloud Platform": [r"aws", r"azure", r"cloud"],
    "Azure": [r"gcp", r"google cloud", r"aws", r"cloud"],
    "MLOps": [r"deployment", r"serving", r"retraining", r"ci/cd", r"monitoring", r"pipeline"],
    "Fine-tuning": [r"classification", r"xgboost", r"scikit", r"training", r"hyperparameter"],
    "Model evaluation": [r"llm-as-judge", r"evaluation", r"gold dataset", r"quality gates"],
    "Multi-agent systems": [r"agentic", r"agent", r"adk", r"orchestration"],
    "NLP": [r"word2vec", r"embedding", r"semantic", r"classification"],
    "Hugging Face": [r"transformer", r"embedding", r"pytorch", r"gguf", r"locally hosted"],
    "TensorFlow": [r"pytorch", r"scikit", r"deep learning", r"onnx"],
    "Tableau": [r"power bi", r"dax", r"dashboard", r"visualization"],
    "Data governance": [r"quality gates", r"sla", r"iam", r"security", r"responsible"],
    "Data pipelines": [r"etl", r"airflow", r"ingestion", r"pipeline"],
    "Streaming data": [r"kafka", r"pubsub", r"real-time", r"streaming"],
    "GenAI": [r"llm", r"rag", r"agent", r"prompt", r"gguf", r"nl-to-sql"],
    "LLMs": [r"llm", r"rag", r"prompt", r"gguf", r"nl-to-sql", r"judge"],
    "Prompt engineering": [r"prompt", r"context", r"agent"],
    "Agentic AI": [r"agent", r"adk", r"orchestration", r"nl-to-sql"],
    "Hugging Face Transformers": [r"transformer", r"pytorch", r"embedding"],
}


def prune_candidates(
    target: str, current_skills: list[str], k: int = 5
) -> list[str]:
    """Keyword-overlap pre-filter with lexicon hints: candidates for a target.

    Top-k by keyword overlap, plus any hint-matched skills (always included,
    even beyond k) — the judge can score them <0.2 if truly unrelated.
    """
    import re as _re

    t_tokens = _tokenize(canonical_term(target))
    scored = []
    for c in current_skills:
        c_tokens = _tokenize(c)
        overlap = len(t_tokens & c_tokens)
        rarity = sum(len(t) for t in t_tokens & c_tokens)
        scored.append((overlap * 10 + rarity, c))
    scored.sort(reverse=True)
    picked = [c for _, c in scored[:k]]

    # Hint-matched candidates: always include (dedup)
    low = target.lower()
    for pattern in PRUNER_HINTS.get(target, []):
        for c in current_skills:
            if c not in picked and _re.search(pattern, c.lower()):
                picked.append(c)
    return picked


def judge_target(
    sg: SkillGraph,
    target: str,
    cfg: LLMConfig | None = None,
    k: int = 5,
    min_confidence: float = 0.3,
) -> JudgeResult:
    """Judge one target skill against pruned candidates; write TRANSFERS_TO edges."""
    current = sg.current_skills()
    candidates = prune_candidates(target, current, k=k)
    if not candidates:
        return JudgeResult(target=target, scores=[], error="no candidates")

    cand_block = "\n".join(f"- {c}" for c in candidates)
    prompt = PROMPT_TEMPLATE.format(target=target, candidates=cand_block)
    try:
        result = judge(prompt, system=SYSTEM_PROMPT, cfg=cfg)
    except Exception as e:  # noqa: BLE001
        return JudgeResult(target=target, scores=[], error=str(e))

    scores = []
    for s in result.get("scores", []):
        try:
            conf = float(s["confidence"])
            skill = str(s["skill"])
            rationale = str(s.get("rationale", ""))[:300]
        except (KeyError, TypeError, ValueError):
            continue
        # map model-returned skill name back to a real current skill
        match = next((c for c in candidates if c.lower() == skill.lower()), None)
        if match is None:  # fuzzy: substring either way
            match = next(
                (c for c in candidates if skill.lower() in c.lower() or c.lower() in skill.lower()),
                None,
            )
        if match is None or conf < min_confidence:
            continue
        scores.append({"skill": match, "confidence": conf, "rationale": rationale})
        sg.add_transfers_to(match, target, conf, rationale)
    return JudgeResult(target=target, scores=scores)


def judge_all_unmatched(
    sg: SkillGraph,
    cfg: LLMConfig | None = None,
    k: int = 5,
    only: list[str] | None = None,
) -> list[JudgeResult]:
    """Judge every unmatched target skill (or a subset via `only`)."""
    targets = only if only is not None else sg.unmatched_target_skills()
    results = []
    for i, t in enumerate(sorted(targets), 1):
        r = judge_target(sg, t, cfg=cfg, k=k)
        results.append(r)
        top = max(r.scores, key=lambda s: s["confidence"], default=None)
        top_str = f"top: {top['skill']} @ {top['confidence']:.2f}" if top else "no transfer"
        err = f" ERROR: {r.error}" if r.error else ""
        print(f"  [{i}/{len(targets)}] {t}: {top_str}{err}")
    return results


def save_judge_report(results: list[JudgeResult], path: str | Path) -> None:
    """Persist judge output for the calibration check and README case study."""
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    payload = [
        {
            "target": r.target,
            "error": r.error,
            "scores": r.scores,
        }
        for r in results
    ]
    p.write_text(json.dumps(payload, indent=2), encoding="utf-8")