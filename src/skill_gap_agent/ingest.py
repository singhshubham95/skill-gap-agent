"""Ingestion + target-ingestion nodes (milestone 2).

Ingestion: skills JSON -> canonical Skill nodes + HAS_SKILL edges.
Target-ingestion: JD texts -> target Skill nodes + REQUIRES edges with
weight = number of JDs mentioning the skill.

JD skill extraction in v1 is a curated keyword lexicon (deterministic, free,
auditable). LLM-based extraction is a possible upgrade but not needed to
reproduce the manual frequency tally.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .graph import JD, Skill, SkillGraph, SkillSource
from .normalize import canonical_term, normalize_name

# ---------------------------------------------------------------------------
# Ingestion (current skills)
# ---------------------------------------------------------------------------


def ingest_skills_json(
    sg: SkillGraph,
    path: str | Path,
    taxonomy=None,
    approvals_path: str | Path = Path("output/implied_skills.json"),
    auto_accept_implied: bool = False,
) -> dict[str, int]:
    """Parse skills JSON -> canonical Skill nodes + HAS_SKILL edges.

    Dedup: two raw phrases mapping to the same canonical term collapse into
    one Skill node. After explicit skills, runs implied-skill detection and
    proposes each to the user (with evidence) unless auto_accept_implied.
    Returns {"raw": n_raw, "canonical": n_canonical, "implied": n_implied}.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_phrases: list[tuple[str, str]] = []

    def walk(obj, category: str = "uncategorized") -> None:
        if isinstance(obj, str):
            raw_phrases.append((obj, category))
        elif isinstance(obj, dict):
            for key, value in obj.items():
                walk(value, category=key)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, category)

    walk(data.get("skills", data))

    seen: dict[str, str] = {}  # normalized -> canonical
    for raw, category in raw_phrases:
        canon = canonical_term(raw)
        if not canon:
            continue
        key = canon.lower()
        if key not in seen:
            seen[key] = canon
            sg.add_skill(Skill(name=canon, category=category, source=SkillSource.CURRENT))
        sg.add_has_skill(seen[key])

    # Implied-skill detection + user proposal flow (replaces static set)
    from .implied import detect_implied, propose_implied

    implied = detect_implied([r for r, _ in raw_phrases], set(seen.values()), taxonomy)
    accepted = propose_implied(
        implied, approvals_path=approvals_path, auto_accept=auto_accept_implied
    )
    for skill in sorted(accepted):
        if not sg.g.has_node(f"skill:{skill}"):
            sg.add_skill(
                Skill(name=skill, category="implied", source=SkillSource.CURRENT)
            )
        sg.add_has_skill(skill)

    return {
        "raw": len(raw_phrases),
        "canonical": len(seen),
        "implied": len(accepted),
    }


# ---------------------------------------------------------------------------
# Target-ingestion (JDs)
# ---------------------------------------------------------------------------

# Curated lexicon: canonical skill -> surface patterns matched case-insensitively
# against JD text. Kept explicit (not auto-extracted) so the frequency tally is
# auditable against the manual run.
JD_SKILL_LEXICON: dict[str, list[str]] = {
    "Python": [r"\bpython\b"],
    "PyTorch": [r"\bpytorch\b", r"\btorch\b"],
    "TensorFlow": [r"\btensorflow\b"],
    "Hugging Face": [r"hugging\s*face", r"\btransformers\b"],
    "scikit-learn": [r"scikit[- ]learn", r"\bsklearn\b"],
    "LangChain": [r"\blangchain\b"],
    "LangGraph": [r"\blanggraph\b"],
    "LlamaIndex": [r"\bllamaindex\b"],
    "AutoGen": [r"\bautogen\b"],
    "CrewAI": [r"crew\.?ai"],
    "Google ADK": [r"\b(adk|agent development kit)\b"],
    "RAG (Retrieval-Augmented Generation)": [r"\brag\b", r"retrieval[- ]augmented"],
    "LLMs": [r"\bllms?\b", r"large language model"],
    "GenAI": [r"\bgen\s?ai\b", r"generative\s+ai"],
    "Agentic AI": [r"agentic"],
    "Vector databases": [r"vector\s+(database|store|db)s?", r"\bpinecone\b", r"\bmilvus\b", r"\bfaiss\b", r"\bchroma\b", r"\bweaviate\b", r"\bqdrant\b"],
    "Embeddings": [r"\bembeddings?\b"],
    "MLOps": [r"\bmlops\b", r"model\s+lifecycle"],
    "Docker": [r"\bdocker\b"],
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "CI/CD": [r"\bci/cd\b", r"continuous integration"],
    "Terraform": [r"\bterraform\b"],
    "Apache Airflow": [r"\bairflow\b"],
    "SQL": [r"\bsql\b"],
    "BigQuery": [r"\bbigquery\b"],
    "AWS": [r"\baws\b", r"amazon web services"],
    "Azure": [r"\bazure\b"],
    "Google Cloud Platform": [r"\bgcp\b", r"google cloud"],
    "Azure OpenAI": [r"azure\s+openai"],
    "AWS Bedrock": [r"\bbedrock\b"],
    "Vertex AI": [r"vertex\s+ai"],
    "FastAPI": [r"\bfastapi\b"],
    "pandas": [r"\bpandas\b"],
    "NumPy": [r"\bnumpy\b"],
    "Power BI": [r"power\s+bi"],
    "Tableau": [r"\btableau\b"],
    "Spark": [r"\b(pyspark|apache\s+spark|spark)\b"],
    "NLP": [r"\bnlp\b", r"natural language processing"],
    "Computer Vision": [r"computer\s+vision", r"\bcv\b(?!.*curriculum)"],
    "Deep Learning": [r"deep\s+learning"],
    "Machine Learning": [r"\bmachine\s+learning\b", r"\bml\b"],
    "Prompt engineering": [r"prompt\s+engineering"],
    "Fine-tuning": [r"fine[- ]tun"],
    "Model evaluation": [r"model\s+evaluation", r"\bevals?\b"],
    "Multi-agent systems": [r"multi[- ]agent"],
    "Conversational AI": [r"conversational\s+ai", r"dialogflow"],
    "Time series forecasting": [r"time\s+series", r"forecasting"],
    "Data visualization": [r"data\s+visualiz"],
    "ETL": [r"\betl\b", r"\belt\b"],
    "Data pipelines": [r"data\s+pipeline"],
    "A/B testing": [r"a/b\s+test"],
    "Recommender systems": [r"recommen(dation|der)\s+system"],
    "Reinforcement Learning": [r"reinforcement\s+learning", r"\brlhf\b"],
    "Graph databases": [r"graph\s+(database|db)"],
    "Streaming data": [r"\bkafka\b", r"stream(ing)?\s+data"],
    "Data governance": [r"data\s+governance", r"responsible\s+ai"],
    "Stakeholder management": [r"stakeholder"],
    "Technical leadership": [r"technical\s+leadership", r"team\s+lead", r"mentoring"],
}


def ingest_jds(sg: SkillGraph, jd_dir: str | Path) -> dict[str, int]:
    """Parse JD texts -> JD nodes, target Skill nodes, REQUIRES edges.

    Weight on REQUIRES = number of JDs mentioning the skill (incremented per
    JD), reproducing the manual frequency tally.
    Returns {"jds": n, "target_skills": n}.
    """
    jd_dir = Path(jd_dir)
    n_jds = 0
    for f in sorted(jd_dir.iterdir()):
        if f.suffix.lower() not in (".txt", ".md"):
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        jd_node = sg.add_jd(JD(title=f.stem, company="", raw_text_ref=str(f)))
        n_jds += 1
        low = text.lower()
        for canon, patterns in JD_SKILL_LEXICON.items():
            if any(re.search(p, low) for p in patterns):
                if not sg.g.has_node(f"skill:{canon}"):
                    sg.add_skill(Skill(name=canon, category="jd-extracted", source=SkillSource.TARGET))
                sg.add_requires(jd_node, canon, weight=1)
    return {"jds": n_jds, "target_skills": len(sg.target_skills())}


def build_seed_graph(
    skills_path: str | Path,
    jd_dir: str | Path,
    taxonomy=None,
    auto_accept_implied: bool = False,
) -> tuple[SkillGraph, dict]:
    """Full milestone-2 build: ingest skills + JDs into one graph."""
    sg = SkillGraph()
    stats = {}
    stats.update(
        ingest_skills_json(
            sg, skills_path, taxonomy=taxonomy, auto_accept_implied=auto_accept_implied
        )
    )
    jd_stats = ingest_jds(sg, jd_dir)
    stats.update(jd_stats)
    return sg, stats