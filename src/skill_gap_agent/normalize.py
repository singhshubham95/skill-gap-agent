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
    "prompt/context engineering for agent tool use": "Prompt engineering",
    "prompt/context engineering": "Prompt engineering",
    "agentic application development": "Agentic AI",
    "agentic application development (google adk)": "Agentic AI",
    "nl-to-sql agents": "NL-to-SQL agents",
    "llm-as-judge evaluation framework design": "LLM-as-judge evaluation",
    "llm-as-judge evaluation": "LLM-as-judge evaluation",
    "locally hosted llm deployment": "Locally hosted LLM deployment",
    "vector store implementation": "Vector databases",
    "vector store implementation (faiss)": "Vector databases",
    "sentence transformer embeddings": "Embeddings",
    "semantic clustering using word embeddings": "Embeddings",
    "word2vec (custom-trained embeddings)": "Embeddings",
    "word2vec": "Embeddings",
    "rag architecture design": "RAG (Retrieval-Augmented Generation)",
    "rag (retrieval-augmented generation) architecture design": "RAG (Retrieval-Augmented Generation)",
    "google bigquery": "BigQuery",
    "advanced bigquery sql": "SQL",
    "t-sql/general sql for cloud sql and azure-based systems": "SQL",
    "core libraries": "Python",
    "python": "Python",
    "pandas": "pandas",
    "numpy": "NumPy",
    "requests": "Python",
    "jupyter": "Jupyter",
    "pluralsight: python - advanced pandas (assessment)": "pandas",
    "google cloud skill badge: cost optimization on gcp": "Google Cloud Platform",
    "google cloud skill boost: docker hands-on lab": "Docker",
    "slb skillsoft percipio: using docker for devops - introduction to docker": "Docker",
    "slb degreed percipio: pl-300 series (power bi - data modeling, loading & transforming data, data analysis)": "Power BI",
    "pluralsight: terraform (course completion, verified badge)": "Terraform",
    "pluralsight: gcp fundamentals (course completion, verified badge)": "Google Cloud Platform",
    "gcp cloud composer administration and upgrades": "GCP Composer",
    "gcp composer": "GCP Composer",
    "gcp dataproc": "GCP Dataproc",
    "gke": "GKE",
    "vertex ai (platform exposure)": "Vertex AI",
    "vertex ai": "Vertex AI",
    "azure devops yaml-based ci/cd pipelines": "Azure DevOps",
    "azure build pipelines": "Azure DevOps",
    "ci/cd pipeline configuration": "CI/CD",
    "ci/cd for model deployment": "CI/CD",
    "pytorch to onnx export": "PyTorch",
    "onnx runtime inference": "ONNX",
    "sentence transformer embeddings": "Embeddings",
    "team mentoring": "Mentoring",
    "technical design guidance and architecture ownership for multi-team platforms": "Technical leadership",
    "code review leadership": "Technical leadership",
    "cross-functional stakeholder management": "Stakeholder management",
    "executive/leadership presentation and reporting": "Executive presentation",
    "vendor management coordination": "Vendor management",
    "sprint planning support": "Sprint planning",
    "structured technical interviewing": "Technical interviewing",
    "interview framework/rubric design from scratch": "Technical interviewing",
    "candidate evaluation across etl stack competencies": "Technical interviewing",
    "requirements elicitation from ambiguous/non-technical stakeholders": "Requirements elicitation",
    "requirements gathering and metric standardization from ambiguous stakeholder input": "Requirements elicitation",
    "cross-hub team scaling": "Team scaling",
    "sprint planning support": "Sprint planning",
    "documentation and process/governance framework authoring": "Documentation",
    "one-on-one and group technical workshops": "Technical workshops",
    "org-wide public speaking": "Public speaking",
    "cross-team knowledge sharing sessions": "Knowledge sharing",
    "dashboard architecture and governance across multiple business lines": "Dashboard architecture",
    "kpi/metric design": "KPI design",
    "data modeling": "Data modeling",
    "bookmarks": "Power BI",
    "custom tooltips": "Power BI",
    "row-level security implementation": "Power BI",
    "non-linear aggregation design": "Power BI",
    "enterprise workspace/app view governance": "Power BI",
    "power query m language": "Power Query M",
    "data modeling (pl-300 level: relationships, calculated columns)": "Power BI",
    "dax (calculate, summarize, allexcept, allselect, dynamic/weighted measures)": "DAX",
    "dax": "DAX",
    "bigquery, cloud storage (gcs), cloud sql, cloud run, cloud run jobs": "Google Cloud Platform",
    "cloud build, artifact registry": "Google Cloud Platform",
    "cloud monitoring and logging": "Cloud Monitoring",
    "secret manager": "Secret Manager",
    "iam (roles, permissions, principle of least privilege design)": "IAM",
    "iam": "IAM",
    "cloud sql administration and integration": "Cloud SQL",
    "azure devops (repository structuring: dev/qa/uat/prod branch strategy)": "Azure DevOps",
    "azure devops yaml-based ci/cd pipelines": "Azure DevOps",
    "azure build pipelines": "Azure DevOps",
    "azure data factory": "Azure Data Factory",
    "sap ibp (integrated business planning) - data integration and platform support": "SAP IBP",
    "sap analytics cloud (sac) - etl framework design, digital boardroom awareness": "SAP Analytics Cloud",
    "sap cpi (cloud platform integration) - troubleshooting/replacement": "SAP CPI",
    "cross-system data integration (gac, fdp, rite, sap, cim inventory systems)": "System integration",
    "oil & gas operations planning (sales & operations planning / s&op)": "Oil & gas domain",
    "surface production systems (sfp) business domain": "Oil & gas domain",
    "asset and materials & supply (mns) forecasting for oilfield operations": "Oil & gas domain",
    "demand planning and rolling forecast (rofo) processes": "Demand planning",
    "integrated business planning (ibp) process design": "Integrated Business Planning",
    "iit delhi - btech & mtech, mathematics and computing": "",
    "pluralsight": "",
    "slb degreed percipio": "",
    "slb skillsoft percipio": "",
    "google cloud skill badge": "",
    "google cloud skill boost": "",
}

# Phrases that are narrative, not skills — dropped during normalization.
_STOP_PATTERNS = [
    r"^iit delhi",           # credentials handled separately
    r"^btech",
    r"^mtech",
]

_PAREN = re.compile(r"\s*\([^)]*\)")          # "(...)" groups
_BRACKET = re.compile(r"\s*\[[^\]]*\]")       # "[...]" groups
_TRAILING_DETAIL = re.compile(r"\s+[-–—]\s+.*$")  # " - detail" suffixes

# Pre-colon labels that are generic groupings, not skills themselves.
_GENERIC_LABELS = {
    "core libraries",
    "environment management",
    "libraries",
    "tools",
    "frameworks",
    "certifications",
    "credentials",
    "education",
    "experience",
    "skills",
    "platforms",
    "languages",
}

# Skills the user demonstrably has but which never appear as a standalone
# phrase in the skills JSON (evidenced only inside other entries, e.g.
# "Custom Airflow operator authoring (Python)", "PyTorch to ONNX export").
# Curated from the manual session's gap analysis — these must NOT be flagged
# as gaps by the judge node.
IMPLIED_SKILLS: set[str] = {
    "Python",
    "Machine Learning",
    "NLP",
    "MLOps",
    "ETL",
    "Data pipelines",
    "Data visualization",
    "Hugging Face",
    "Google ADK",
    "NL-to-SQL agents",
    "LLM-as-judge evaluation",
    "Locally hosted LLM deployment",
    "Fine-tuning",
    "Model evaluation",
    "Multi-agent systems",
    "Data governance",
    "Streaming data",
    "Tableau",
    "TensorFlow",
    "AutoGen",
    "CrewAI",
    "LlamaIndex",
    "AWS",
    "AWS Bedrock",
    "Azure OpenAI",
    "Google Cloud Platform",
    "GenAI",
    "LLMs",
    "LangChain",
    "LangGraph",
}

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

    # Strip parenthetical/bracket detail and trailing "- detail" suffixes.
    text = _BRACKET.sub("", text)
    text = _PAREN.sub("", text)
    text = _TRAILING_DETAIL.sub("", text)

    # Colon handling: only strip the prefix when the pre-colon part is a
    # generic grouping label (e.g. "Core libraries:", "Environment management:").
    # Skill-bearing prefixes like "Advanced SQL: joins, ..." keep the FULL
    # pre-colon phrase, since the label IS the skill.
    if ":" in text:
        head, tail = text.split(":", 1)
        head = head.strip()
        if head.lower() in _GENERIC_LABELS:
            text = tail.strip() or head
        else:
            text = head
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