# Third-party notices

Skill-Gap Agent (MIT — see [LICENSE](LICENSE)) bundles or depends on the
following third-party software. This list covers the runtime dependencies
declared in [pyproject.toml](pyproject.toml); development-only tools
(`pytest`, `ruff`) are not distributed with the product. The Chrome
extension itself is dependency-free JavaScript.

| Package | License | Used for |
|---|---|---|
| networkx | BSD-3-Clause | Skill graph (S3) |
| pydantic | MIT | Structured models |
| keyring | MIT | OS credential vault storage for API keys |
| langgraph | MIT | Pipeline orchestration (M7) |
| langgraph-checkpoint-sqlite | MIT | Optional run checkpoints |
| pypdf | BSD-3-Clause | Resume PDF text extraction |
| python-docx | MIT | Resume DOCX text extraction |
| openai | MIT | OpenAI-compatible LLM client (all providers) |
| langchain-core | MIT | LangGraph dependency / LangSmith hooks (M17) |

Each package's full license text ships inside its own distribution. If
the companion app is ever bundled into an installer, keep this file with
it.
