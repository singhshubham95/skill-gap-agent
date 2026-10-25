# Third-party notices

Skill-Gap Agent (MIT — see [LICENSE](LICENSE)) bundles or depends on the
following third-party software. This list covers the runtime dependencies
declared in [pyproject.toml](pyproject.toml) plus the components shipped in
the M29 Windows companion installer. Development-only tools (`pytest`,
`ruff`) are not distributed with the product. The Chrome extension itself is
dependency-free JavaScript.

| Package | License | Used for |
|---|---|---|
| networkx | BSD-3-Clause | Skill graph (S3) |
| pydantic | MIT | Structured models |
| keyring | MIT | OS credential vault storage for API keys |
| langgraph | MIT | Pipeline orchestration (M7) |
| langgraph-checkpoint-sqlite | MIT | Optional run checkpoints |
| pypdf | BSD-3-Clause | Resume PDF text extraction |
| python-docx | MIT | Resume DOCX text extraction |
| lxml | BSD-3-Clause | XML backend for DOCX parsing (python-docx dependency) |
| openai | MIT | OpenAI-compatible LLM client (all providers) |
| langchain-core | MIT | LangGraph dependency / LangSmith hooks (M17) |
| pystray | LGPL-3.0 | Desktop tray icon/menu (M29) |
| six | MIT | pystray dependency |
| Pillow | MIT-CMU (HPND-style) | Tray image + icon generation (M29) |
| Python runtime | PSF-2.0 | Bundled interpreter in the frozen companion |
| PyInstaller bootloader | GPL-2.0-or-later with the PyInstaller exception | Frozen-app launcher |

Each package's full license text ships inside its own upstream distribution
(or is available from its project page). The companion installer ships this
notice file with the application. The LGPL-licensed pystray package is
included as an unmodified, replaceable Python module in the one-directory
build.
