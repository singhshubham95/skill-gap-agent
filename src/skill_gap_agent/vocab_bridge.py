"""LLM-assisted vocabulary bridge (M8, specs/12-skill-cleaner.md S4).

The alias table was seeded from ONE curated document's phrasing (the seed
skills JSON). New inputs — like LLM-extracted resumes — phrase the same
skills differently ("Airflow orchestration" vs "Apache Airflow"), and exact/
alias matching cannot bridge them without a manual alias entry per variant.

This module closes that gap: for each canonical term from a new input that
matches no existing canonical term, ONE LLM call judges whether it is a
synonym/variant of an existing term (merge) or a genuinely new skill (keep).
Decisions persist to output/vocab_bridge.json (override-file pattern) and
are applied silently on re-runs — same philosophy as gate_overrides.json.
"""

from __future__ import annotations

import json
from pathlib import Path

from .llm import LLMConfig, judge

BRIDGE_PATH = Path("output/vocab_bridge.json")

SYSTEM_PROMPT = (
    "You are a skill-vocabulary normalizer for a career-gap analysis tool. "
    "You decide whether a skill term is the SAME skill as an existing term "
    "(just phrased differently) or a genuinely DIFFERENT skill. "
    "Respond with ONLY a valid JSON object."
)

PROMPT_TEMPLATE = """Existing skill vocabulary (canonical terms):
{existing}

New terms to classify (one verdict per term):
{terms}

For EACH new term, decide: is it the same underlying skill as one of the
existing terms (phrased differently), or a genuinely different skill?

Rules:
- Merge ONLY when both terms denote the same skill a hiring manager would
  treat as interchangeable. "Airflow orchestration" = "Apache Airflow" (same
  skill). "Kubernetes orchestration" = "Kubernetes" (same skill).
- Do NOT merge related-but-distinct skills: "Model serving" is NOT "FastAPI"
  (serving is the activity, FastAPI is one tool). When unsure, keep separate
  (a false merge loses information; a missed merge just leaves two nodes).
- Match against the CLOSEST existing term only.
- Return one verdict for EVERY new term, in order.

Respond with JSON exactly like:
{{"verdicts": [{{"term": "<new term>", "verdict": "merge", "match": "<existing term>"}},
              {{"term": "<new term>", "verdict": "new"}}]}}"""


def load_bridge(path: str | Path = BRIDGE_PATH) -> dict[str, str | None]:
    """Saved bridge decisions: new term -> existing term (or None = new)."""
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_bridge(
    decisions: dict[str, str | None], path: str | Path = BRIDGE_PATH
) -> Path:
    p = Path(path)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(decisions, indent=2), encoding="utf-8")
    return p


def bridge_vocabulary(
    new_terms: list[str],
    existing_terms: list[str],
    path: str | Path = BRIDGE_PATH,
    auto: bool = False,
    cfg: LLMConfig | None = None,
) -> dict[str, str | None]:
    """Classify unmatched new terms against the existing vocabulary.

    Returns {new_term: existing_term_or_None}. Saved decisions are reused
    silently; only genuinely unclassified terms hit the LLM (one call per
    term, batched into a single call per up-to-20 terms to bound latency).
    """
    saved = load_bridge(path)
    existing_set = set(existing_terms)
    decisions: dict[str, str | None] = {}

    pending = []
    for t in new_terms:
        if t in existing_set:
            continue  # already canonical
        if t in saved:
            decisions[t] = saved[t]
        else:
            pending.append(t)

    if not pending:
        return decisions

    if auto:
        # Auto mode: no LLM, keep everything as new (recorded, reviewable).
        for t in pending:
            decisions[t] = None
        return decisions

    # Batch: one LLM call per chunk of terms (bounded latency vs ~20 min
    # for a single huge call — see specs/5-milestones.md §Open: extraction latency).
    CHUNK = 20
    for i in range(0, len(pending), CHUNK):
        chunk = pending[i : i + CHUNK]
        prompt = PROMPT_TEMPLATE.format(
            existing="\n".join(f"- {e}" for e in sorted(existing_terms)),
            terms="\n".join(f"- {t}" for t in chunk),
        )
        try:
            result = judge(prompt, system=SYSTEM_PROMPT, cfg=cfg or LLMConfig())
        except Exception:  # noqa: BLE001 — LLM down: keep terms as new
            for t in chunk:
                decisions[t] = None
            continue
        verdicts = result.get("verdicts")
        if not isinstance(verdicts, list):
            # Malformed reply: keep chunk as new (recorded, reviewable).
            for t in chunk:
                decisions[t] = None
            continue
        for v in verdicts:
            term = str(v.get("term", ""))
            if v.get("verdict") == "merge" and v.get("match") in existing_set:
                decisions[term] = str(v["match"])
            else:
                decisions[term] = None

    # Persist only the newly decided entries (merge with saved).
    save_bridge({**saved, **decisions}, path)
    return decisions


def apply_bridge(
    canonical_terms: list[str],
    decisions: dict[str, str | None],
) -> list[str]:
    """Rewrite canonical terms per bridge decisions (merged -> target term)."""
    return [decisions.get(t, t) or t for t in canonical_terms]
