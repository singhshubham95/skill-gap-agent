# Changelog (human tier)

> **Non-authoritative.** Per-task summaries only. Full history — decisions,
> verification records, learnings — lives in `specs/02-decisions.md` and
> `specs/03-milestones.md`.

Format: `- T-<id>: <what changed, one or two lines> (spec: <link>)`

Lines are added by the agent at task close (end-to-end pipeline, single
session). Milestone history M1–M15 predates this file and lives in
[specs/03-milestones.md](../specs/03-milestones.md) — not duplicated here.

## Entries

- T-M16: Free-tier LLM access — panel "Connect free LLM" (OpenRouter OAuth
  PKCE → OS keyring, no pasting), opt-in free-model mode behind a consent
  gate, retry hardening (classification, bounded attempts, `:free`
  fallback, per-touchpoint timeouts); live interactive pass pending (spec:
  [05-ai-caller.md](../specs/05-ai-caller.md) §Free-tier routing)
