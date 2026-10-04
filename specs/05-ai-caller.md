# S2 — AI Caller

Single door to the language model. Every LLM call in the pipeline goes
through here; node modules never touch provider SDKs.

**Status: Built** (M3; M8 secrets change — see below); M14 tracing hook Designed.

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

## Tracing hook (M14) — 🎯 Designed, no code yet

- `_client()` will return `tracing.wrap_client(OpenAI(...))`: when tracing
  is on, every `chat.completions.create` becomes a LangSmith child run
  (prompt, response, tokens, latency); when off, the client is returned
  unchanged. `judge()` / `chat()` signatures do not change.
- `LANGSMITH_API_KEY` resolves through `secrets.get_secret()` like every
  other key (env → keyring). Tracing is opt-in and never raises.
- Design: `01-system-overview.md` §M14 design; decisions in
  `02-decisions.md` (M14 rows); milestone `03-milestones.md` M14 (14a).

## Known limits

- Extraction call latency ~19 min on DeepSeek V4 Flash (one-time per
  resume via artifact reuse). Fix path: faster extraction model or
  timeout + retry — see `03-milestones.md` §Open (extraction latency).

## History (links, not copies)

- Decisions: `02-decisions.md` (provider rows, keyring-only secret rule).
- Milestones: `03-milestones.md` M3, M8, M14 (Designed).
- Deferred: `03-milestones.md` §Deferred #6 (local-model benchmark).
