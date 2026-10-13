# Changelog (human tier)

> **Non-authoritative.** Per-task summaries only. Full history — decisions,
> verification records, learnings — lives in `specs/02-decisions.md` and
> `specs/03-milestones.md`.

Format: `- T-<id>: <what changed, one or two lines> (spec: <link>)`

Lines are added by the agent at task close (end-to-end pipeline, single
session). Milestone history M1–M15 predates this file and lives in
[specs/03-milestones.md](../specs/03-milestones.md) — not duplicated here.

## Entries

- T-M9-fix-intake: Item-level intake freshness — a `completed` profile no
  longer silently skips the chat (it hid new items after an extraction
  change, and a scripted validation run had polluted the real session);
  re-opened chats derive completion from the turn machine (never the stale
  flag); "use as-is" is sticky + terminal; extraction class unified across
  chat/graph halves (M24 rule-mode respected); skipped chats surface
  `intake_note`; `SKILL_GAP_SESSIONS_DIR` isolates validation runs
  (spec: [13-intake.md](../specs/13-intake.md) §Freshness)
- T-M25: Fix gate-profiling crash on equal-confidence ties — `max()` over
  `(confidence, edge_dict)` tuples compared dicts on ties (TypeError right
  after judging; found by the M24 live pass 2026-10-12); compares plain
  floats now, red→green regression in `m7_check` (spec:
  [03-milestones.md](../specs/03-milestones.md) M24 learning (c))
- T-M9-impl: Conversational intake + skill validation (C3) built —
  in-panel intake chat at Analyze gaps, SHA-keyed session store
  (`output/sessions/<sha>/profile.json`), depth-aware judge with
  profile-stamped caches, gate no-double-count rule, legacy global
  decision files retired; upload is rule-only (extraction moves to
  analyze). Verified: m9_check FULL PASS, ruff clean, pytest 51 passed,
  full check sweep green, live end-to-end run (degradation paths —
  provider key expired) (spec: [13-intake.md](../specs/13-intake.md))
- T-M24: Mode governs ingestion — free/paid/rule now applies to resume
  extraction too (rule = local regex, nothing leaves the machine); Setup
  order = AI access → mode + consent → resume; mode-aware extraction
  cache; `POST /api/resume` gains mode/provider/consent headers; live
  pass pending (spec: [12-extension.md](../specs/12-extension.md) §M24)
- T-M23: LinkedIn posture — assist, don't act: the content script never
  clicks page controls; truncated JDs get the "…see more" button scrolled
  into view, focused and highlighted (Ctrl+F-style) for the user to click
  themselves; capture guardrails explicit; mitigates L3 (spec:
  [12-extension.md](../specs/12-extension.md) §Capture)
- T-M22: Store readiness — hosted privacy policy (`docs/`, GitHub Pages)
  with the Limited Use statement + named destinations,
  `CHROMEWEBSTORE.md` submission register (per-permission justifications,
  declarations, listing copy with LinkedIn + AI disclaimers), generated
  placeholder icons + manifest wiring, `THIRD-PARTY-NOTICES`; prepares
  blockers L1/L2/L6/L7 (spec:
  [12-extension.md](../specs/12-extension.md) §Data disclosure)
- T-M21: Honest data disclosure — banned the "stays on your machine" claim
  (the file is local; the extracted text goes over HTTPS to the selected
  AI provider, never to the developer), named destinations (OpenRouter →
  DeepSeek, Z.ai GLM, OpenAI; GitHub gets skill-gap terms only), first-use
  consent gating upload + analyze with a server-enforced
  `X-Disclosure-Ack`; fixes S2 + the disclosure side of L5 (spec:
  [12-extension.md](../specs/12-extension.md) §Data disclosure)
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
