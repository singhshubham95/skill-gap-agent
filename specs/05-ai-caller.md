# S2 — AI Caller

Single door to the language model. Every LLM call in the pipeline goes
through here; node modules never touch provider SDKs.

**Status: Built** (M3; M8 secrets change — see below).

## What it does

- `llm.py::judge()` — structured prompt → JSON object, retries on parse
  failure. `llm.py::chat()` — raw text. JSON-extraction tolerates
  markdown fences.
- Providers: OpenRouter (default, `deepseek/deepseek-v4-flash-0731`),
  GLM + OpenAI as calibration fallbacks. Swap = config change.
- Secrets: **OS keyring only** (`secrets.py`, service `skill-gap-agent`).
  Resolution: env var override → keyring. No `.env` fallback
  (user decision 2026-09-27; `.env.example` deleted). Missing key raises
  `LLMError` with the keyring set command.
- Callers: S1 extraction (1 call), S4 bridge (batched), S5 judge
  (1 per target), S6 synthesis (1 per gap), S7 intake/validation (M9).

## Known limits

- Extraction call latency ~19 min on DeepSeek V4 Flash (one-time per
  resume via artifact reuse). Fix path: faster extraction model or
  timeout + retry — see `5-milestones.md` §Open (extraction latency).

## History (links, not copies)

- Decisions: `3-decisions.md` (provider rows, keyring-only secret rule).
- Milestones: `5-milestones.md` M3, M8.
- Deferred: `5-milestones.md` §Deferred #6 (local-model benchmark).
