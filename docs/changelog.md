# Changelog (human tier)

> **Non-authoritative.** Per-task summaries only. Full history — decisions,
> verification records, learnings — lives in `specs/02-decisions.md` and
> `specs/03-milestones.md`.

Format: `- T-<id>: <what changed, one or two lines> (spec: <link>)`

Lines are added by the agent at task close (end-to-end pipeline, single
session). Milestone history M1–M15 predates this file and lives in
[specs/03-milestones.md](../specs/03-milestones.md) — not duplicated here.

## Entries

- T-M20: Public-release hardening — request-origin gate (web pages can no
  longer call the local agent), Content-Type enforcement, `skills_path`
  containment, https-only non-loopback `serverBase`; closes security
  findings S1/L4 (spec:
  [12-extension.md](../specs/12-extension.md) §Security posture)
- T-M19: Light/dark theme — panel + plan follow the OS theme
  (`prefers-color-scheme`) with a minimal Auto/Light/Dark override button;
  plan follows via serve-time `?theme=` injection (plan.html stays
  JS-free); visual pass confirmed 2026-10-11 (spec:
  [12-extension.md](../specs/12-extension.md) §M19)
- T-M18: Panel simplification — state-driven side panel (key check →
  free/paid/rule mode chips or "Create free LLM key"; paste form behind
  "I already have a key"), key validation via the free key-info endpoint
  (status chip only), collapsed Settings, merged gap-table provenance
  captions; live interactive pass pending (spec:
  [12-extension.md](../specs/12-extension.md) §M18)
- T-M16: Free-tier LLM access — panel "Connect free LLM" (OpenRouter OAuth
  PKCE → OS keyring, no pasting), opt-in free-model mode behind a consent
  gate, retry hardening (classification, bounded attempts, `:free`
  fallback, per-touchpoint timeouts); live interactive pass closed
  2026-10-11 via the M18 live pass (spec:
  [05-ai-caller.md](../specs/05-ai-caller.md) §Free-tier routing)
