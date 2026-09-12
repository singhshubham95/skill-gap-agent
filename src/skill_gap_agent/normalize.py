"""Normalization: canonical skill terms + alias matching.

The load-bearing step (specs/architecture.md #3). Two jobs:

1. Canonical-term extraction — the skills JSON contains long descriptive
   phrases ("Docker (Dockerfile authoring, image build/tag/push/pull,
   registries)"); extract the short canonical term ("Docker").
2. Alias resolution — map surface forms ("PyTorch", "pytorch", "Torch") to one
   canonical name, so exact-match dedup works before the judge node.

v1 strategy (specs/open-items.md): regex parenthetical-stripping + alias table;
LLM-assisted merge only for ambiguous pairs (not yet wired).
"""

from __future__ import annotations

import re
from functools import lru_cache

# Surface form (lowercase) -> canonical name.
# Seeded from the manual session's merge decisions; extend as needed.
ALIASES: dict[str, str] = {
    "torch": "PyTorch",
    "hf": "Hugging Face",
    "huggingface": "Hugging Face",
    "transformers (hugging face)": "Hugging Face",
    "llm": "LLMs",
    "large language models": "LLMs",
    "genai": "GenAI",
    "generative ai": "GenAI",
    "rag": "RAG (Retrieval-Augmented Generation)",
    "retrieval-augmented generation": "RAG (Retrieval-Augmented Generation)",
    "vector database": "Vector databases",
    "vector db": "Vector databases",
    "k8s": "Kubernetes",
    "ci/cd": "CI/CD",
    "mlops": "MLOps",
    "bigquery sql": "SQL",
    "advanced sql": "SQL",
    "t-sql": "SQL",
    "gcp": "Google Cloud Platform",
    "google cloud": "Google Cloud Platform",
    "aws": "AWS",
    "azure openai": "Azure OpenAI",
    "crew.ai": "CrewAI",
    "crewai": "CrewAI",
    "autogen": "AutoGen",
    "llamaindex": "LlamaIndex",
    "langchain": "LangChain",
    "langgraph": "LangGraph",
    "scikit learn": "scikit-learn",
    "sklearn": "scikit-learn",
    "power bi": "Power BI",
    "airflow": "Apache Airflow",
    "cloud composer": "GCP Composer",
    "w&b": "Weights & Biases",
    "wandb": "Weights & Biases",
    "xgboost": "XGBoost",
    "fastapi": "FastAPI",
    "terraform": "Terraform",
    "docker compose": "Docker Compose",
    "pyspark": "PySpark",
    "numpy": "NumPy",
    "pandas": "pandas",
    "nlp": "NLP",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "deep learning": "Deep Learning",
    "dl": "Deep Learning",
    "mlops": "MLOps",
    "rag pipelines": "RAG (Retrieval-Augmented Generation)",
    "embeddings": "Embeddings",
    "vector databases": "Vector databases",
    "prompt engineering": "Prompt engineering",
}

# Phrases that are narrative, not skills — dropped during normalization.
_STOP_PATTERNS = [
    r"^iit delhi",           # credentials handled separately
    r"^btech",
    r"^mtech",
]

_PAREN = re.compile(r"\s*\([^)]*\)")          # "(...)" groups
_BRACKET = re.compile(r"\s*\[[^\]]*\]")       # "[...]" groups
_AFTER_COLON = re.compile(r"^[^:]{3,40}:\s+")  # "Core libraries: " prefixes
_TRAILING_DETAIL = re.compile(r"\s+[-–—]\s+.*$")  # " - detail" suffixes


@lru_cache(maxsize=None)
def canonical_term(raw: str) -> str:
    """Extract a short canonical skill term from a (possibly verbose) phrase.

    Examples:
      "Docker (Dockerfile authoring, image build/tag/push/pull, registries)"
        -> "Docker"
      "Core libraries: NumPy, pandas, Requests, Jupyter" -> "Core libraries"
      "Advanced SQL: joins, grouping, window/partition functions" -> "Advanced SQL"
    """
    text = raw.strip()
    low = text.lower()

    # Alias table wins outright.
    if low in ALIASES:
        return ALIASES[low]

    # Drop narrative/credential phrases.
    for pat in _STOP_PATTERNS:
        if re.match(pat, low):
            return ""

    # Strip parenthetical/bracket detail, leading "Label:" prefixes, trailing
    # "- detail" suffixes.
    text = _BRACKET.sub("", text)
    text = _PAREN.sub("", text)
    text = _AFTER_COLON.sub("", text)
    text = _TRAILING_DETAIL.sub("", text)
    text = text.strip(" ,;:")

    # If stripping left a comma-separated list, keep the first item (the head
    # term); e.g. "BigQuery, Cloud Storage (GCS), Cloud SQL..." -> "BigQuery".
    if "," in text:
        text = text.split(",")[0].strip()

    # Alias lookup again on the stripped form.
    low = text.lower()
    if low in ALIASES:
        return ALIASES[low]

    return text


def normalize_name(name: str) -> str:
    """Case-insensitive dedup key for a canonical term."""
    return canonical_term(name).lower()


def resolve(surface: str) -> str | None:
    """Resolve a surface form (e.g. from a JD) to a canonical name, or None."""
    low = surface.strip().lower()
    return ALIASES.get(low)