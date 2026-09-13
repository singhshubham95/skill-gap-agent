"""Implied-skill detection: find skills evidenced inside other CV phrases.

Replaces the static IMPLIED_SKILLS set (a design gap — see specs/architecture.md).
During ingestion, each raw phrase is scanned for skill mentions that differ from
the phrase's own canonical term. Every implication is surfaced to the user with
its evidence and a y/n/a choice; approvals persist to output/implied_skills.json
so re-runs don't re-ask.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .normalize import ALIASES, canonical_term

# Canonical skill -> evidence patterns (case-insensitive) that indicate the
# skill is being *used* inside a phrase about something else.
IMPLY_PATTERNS: dict[str, list[str]] = {
    "Python": [r"\(python\)", r"python-based", r"\bpython\s+\d"],
    "PyTorch": [r"pytorch"],
    "TensorFlow": [r"tensorflow"],
    "Hugging Face": [r"hugging\s*face", r"\btransformers\b"],
    "LangChain": [r"\blangchain\b"],
    "LangGraph": [r"\blanggraph\b"],
    "LlamaIndex": [r"\bllamaindex\b"],
    "AutoGen": [r"\bautogen\b"],
    "CrewAI": [r"crew\.?ai"],
    "Google ADK": [r"\bgoogle adk\b", r"\badk\b"],
    "FAISS": [r"\bfaiss\b"],
    "LLMs": [r"\bllms?\b", r"large language model"],
    "GenAI": [r"\bgen\s?ai\b", r"generative\s+ai"],
    "RAG (Retrieval-Augmented Generation)": [r"\brag\b", r"retrieval[- ]augmented"],
    "Vector databases": [r"vector\s+(store|database|db)", r"\bfaiss\b", r"\bpinecone\b", r"\bmilvus\b"],
    "Embeddings": [r"\bembeddings?\b"],
    "MLOps": [r"\bmlops\b", r"model\s+lifecycle"],
    "CI/CD": [r"\bci/cd\b"],
    "Docker": [r"\bdocker\b"],
    "Kubernetes": [r"\bkubernetes\b", r"\bk8s\b"],
    "Terraform": [r"\bterraform\b"],
    "Apache Airflow": [r"\bairflow\b"],
    "BigQuery": [r"\bbigquery\b"],
    "SQL": [r"\bsql\b"],
    "AWS": [r"\baws\b", r"amazon web services"],
    "Azure": [r"\bazure\b"],
    "Google Cloud Platform": [r"\bgcp\b", r"google cloud"],
    "NLP": [r"\bnlp\b", r"natural language processing"],
    "Machine Learning": [r"\bmachine\s+learning\b", r"\bml\b"],
    "Deep Learning": [r"deep\s+learning"],
    "Fine-tuning": [r"fine[- ]tun"],
    "Model evaluation": [r"\bevals?\b", r"model\s+evaluation"],
    "Multi-agent systems": [r"multi[- ]agent"],
    "ETL": [r"\betl\b"],
    "Data pipelines": [r"data\s+pipeline"],
    "Data governance": [r"data\s+governance", r"responsible\s+ai"],
    "Data visualization": [r"data\s+visualiz", r"\bdashboard"],
    "Streaming data": [r"\bkafka\b", r"stream(ing)?\s+data"],
    "Tableau": [r"\btableau\b"],
    "Power BI": [r"power\s+bi"],
    "Spark": [r"\b(pyspark|apache\s+spark|spark)\b"],
    "pandas": [r"\bpandas\b"],
    "NumPy": [r"\bnumpy\b"],
    "FastAPI": [r"\bfastapi\b"],
    "Prompt engineering": [r"prompt[/-]?\s*(context\s+)?engineering"],
    "NL-to-SQL agents": [r"nl[- ]to[- ]sql"],
    "LLM-as-judge evaluation": [r"llm[- ]as[- ]judge"],
    "Locally hosted LLM deployment": [r"locally\s+hosted\s+llm", r"\bgguf\b"],
    "Agentic AI": [r"agentic", r"agent\s+(development|orchestration|tool\s+use)"],
    "Stakeholder management": [r"stakeholder"],
    "Technical leadership": [r"technical\s+leadership", r"architecture\s+ownership"],
    "Mentoring": [r"mentoring", r"mentored"],
    "Time series forecasting": [r"time[- ]series", r"forecasting"],
    "Semantic search": [r"semantic\s+(search|clustering)"],
    "Word2Vec": [r"word2vec"],
    "ONNX": [r"\bonnx\b"],
    "GCP Composer": [r"cloud\s+composer", r"\bgcp\s+composer\b"],
    "Cloud SQL": [r"cloud\s+sql"],
    "IAM": [r"\biam\b"],
    "Secret Manager": [r"secret\s+manager"],
    "DAX": [r"\bdax\b"],
    "Power Query M": [r"power\s+query"],
    "scikit-learn": [r"scikit[- ]learn", r"\bsklearn\b"],
    "XGBoost": [r"\bxgboost\b"],
    "statsmodels": [r"\bstatsmodels\b"],
    "Weights & Biases": [r"weights\s*&\s*biases", r"\bwandb\b"],
    "Git": [r"\bgit\b(?!hub|lab)"],
    "Azure DevOps": [r"azure\s+devops"],
    "Cloud SQL": [r"cloud\s+sql"],
    "GCP Dataproc": [r"\bdataproc\b"],
    "Vertex AI": [r"vertex\s+ai"],
    "SAP IBP": [r"\bsap\s+ibp\b"],
    "SAP Analytics Cloud": [r"sap\s+analytics\s+cloud", r"\bsac\b"],
    "SAP CPI": [r"\bsap\s+cpi\b"],
    "PySpark": [r"\bpyspark\b"],
    "Docker Compose": [r"docker\s+compose"],
    "Helm": [r"\bhelm\b"],
    "Podman": [r"\bpodman\b"],
    "Conda": [r"\bconda\b"],
    "Jupyter": [r"\bjupyter\b"],
    "Homomorphic Encryption": [r"homomorphic"],
    "Trusted Execution Environments": [r"trusted\s+execution", r"\btee\b"],
    "Secure Multi-Party Computation": [r"multi[- ]party\s+computation", r"\bmpc\b"],
    "SARIMAX": [r"\bsarimax\b"],
    "XGBoost": [r"\bxgboost\b"],
}

# Phrases that are pure credentials — never evidence of skill use.
_CREDENTIAL_PAT = r"pluralsight|skillsoft|degreed|skill\s*badge|skill\s*boost|course completion|verified badge|hands-on lab|assessment\)"


@dataclass
class ImpliedSkill:
    skill: str          # canonical skill name
    evidence: str       # the raw CV phrase that implies it
    source: str         # "pattern" | "alias" | "taxonomy"


def detect_implied(
    raw_phrases: list[str],
    explicit_canonical: set[str],
    taxonomy=None,
) -> list[ImpliedSkill]:
    """Scan raw CV phrases for skills implied but not explicitly listed.

    A phrase implies skill S if S's pattern matches the phrase AND S is not
    the phrase's own canonical term AND S is not already explicit.
    """
    import re

    found: dict[str, ImpliedSkill] = {}
    for phrase in raw_phrases:
        low = phrase.lower()
        if re.search(_CREDENTIAL_PAT, low):
            continue
        own = canonical_term(phrase).lower()
        lexicon = dict(IMPLY_PATTERNS)
        if taxonomy is not None:
            for skill, pats in taxonomy.imply_patterns().items():
                lexicon.setdefault(skill, []).extend(pats)
        for skill, pats in lexicon.items():
            if skill.lower() in explicit_canonical or skill.lower() == own:
                continue
            if skill in found:
                continue
            for p in pats:
                if re.search(p, low):
                    found[skill] = ImpliedSkill(skill=skill, evidence=phrase, source="pattern")
                    break
    return sorted(found.values(), key=lambda i: i.skill)


def propose_implied(
    implied: list[ImpliedSkill],
    approvals_path: str | Path = Path("output/implied_skills.json"),
    auto_accept: bool = False,
) -> set[str]:
    """Interactive proposal flow: show evidence, ask y/n/a per skill.

    Previously approved skills are auto-included; previously rejected are
    auto-skipped. 'a' accepts all remaining. Returns the accepted skill set.
    """
    import re

    path = Path(approvals_path)
    saved: dict[str, bool] = {}
    if path.exists():
        saved = json.loads(path.read_text(encoding="utf-8"))

    accepted: set[str] = {s for s, ok in saved.items() if ok}
    pending = [i for i in implied if i.skill not in saved]

    if pending and not auto_accept:
        print(f"\n=== Implied skills detected: {len(pending)} ===")
        print("For each, decide whether it belongs in your skill graph.")
        print("  y = add   n = skip   a = add ALL remaining\n")

    for item in pending:
        if auto_accept:
            accepted.add(item.skill)
            continue
        while True:
            ans = input(
                f"  '{item.evidence[:70]}'\n    implies [{item.skill}] — add? [y/n/a]: "
            ).strip().lower()
            if ans in ("y", "n", "a"):
                break
        if ans == "a":
            accepted.add(item.skill)
            remaining = [i for i in pending if i.skill not in accepted and i.skill not in saved]
            accepted.update(i.skill for i in remaining)
            break
        elif ans == "y":
            accepted.add(item.skill)
        # n: skip

    # Persist decisions
    saved.update({i.skill: (i.skill in accepted) for i in implied})
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(dict(sorted(saved.items())), indent=2), encoding="utf-8")
    return accepted