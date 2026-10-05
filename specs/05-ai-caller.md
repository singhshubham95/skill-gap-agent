# S2 — AI Caller

Single door to the language model. Every LLM call in the pipeline goes
through here; node modules never touch provider SDKs.

**Status: Built** (M3; M8 secrets change — see below). M15 LLM presence
policy: **✅ Built 2026-10-05** (verification record in
`03-milestones.md` M15). M16 free-tier routing + retry hardening:
**Designed** (sections below).

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

## LLM presence policy (M15 — ✅ Built 2026-10-05)

One rule governs every LLM touchpoint: **the output always states whether
the LLM was used.** No caller may fall back to rule-based output
silently. Origin: user report 2026-10-05 — with the keyring key deleted,
"Analyze gaps" + "Generate plan" ran to completion and produced
rule-based output that nothing identified as non-LLM (failed judge calls
read as confidence-0 gaps). Decision rows: `02-decisions.md` M15.

### Intent — a run-level mode

`use_llm` is a run-level flag (default **on**). Surfaces: the extension's
LLM toggle ([12-extension.md](12-extension.md) §M15) and the CLI
(`--no-llm`, today extraction-only — it widens to the full rule-based
mode here). Two deliberate modes, each labeled in its output:

- **LLM mode** — every touchpoint uses the LLM or degrades *loudly*
  (below).
- **Rule-based mode** — a legitimate, labeled mode, not an error: regex
  extraction (S1), no transfer judging (targets render **unjudged**; the
  gap list stays, ranked by JD weight alone — never fake confidence 0),
  keyword-only GFI selection, and no synthesized projects (the plan says
  so instead of showing templates). Every output carries "Rule-based
  mode" up front so non-LLM output is expected rather than suspect.

### Availability — fail fast at start

Before any work the runner probes the selected provider's key
(`secrets.get_secret(PROVIDERS[p]["key_env"])`; `GET /api/providers`
already exposes this as `key_set`). LLM mode + no key → the run is
**refused** with an actionable error naming the provider and where to
enter the key; nothing partial is produced (server: 409; CLI: non-zero
exit). The check is presence-only; an invalid key fails at the first
call, which is the loud-degradation path below.

### Degradation — loud, bounded, labeled

If a touchpoint's call fails mid-run (network, rate limit, bad key), the
run continues — one failed call must not waste the rest (the judge makes
one call per target) — but every failure (a) records `error` in its
result object (`JudgeResult` / `SynthesizedProject` / `OssIssue` already
carry one), (b) marks the run **degraded** with the reason, and (c)
renders its rule-based output under a provenance label (below). The
panel shows a banner: "Parts of this result were generated without the
LLM (reason) — re-run after fixing the key." A call that has exhausted
its retries (§Retry & failure handling) is one such failure — retried
below, surfaced once above.

| Touchpoint | Rule-based behavior | LLM-mode failure behavior (M15) |
|---|---|---|
| S1 extraction | regex lexicon scan | unchanged mechanics (already warns); the warning becomes the standard provenance label |
| S5 judge (`TRANSFERS_TO`) | skip — targets render **unjudged** | failed targets render **unjudged (LLM unavailable)** — a missing edge must never read as a measured "full gap" |
| S6 synthesis | section replaced by a labeled note | failed gaps show the labeled placeholder, not an empty project |
| S6 GFI filter | keyword results, labeled | keep the raw top-5 but label it "keyword matches — not LLM-ranked" |

### Provenance vocabulary (shared — defined here)

Every rendered section and gap row states its origin using exactly these
labels: `LLM` · `LLM (cached)` · `Rule-based` · `Rule-based (LLM
unavailable — <reason>)`. Cache reuse — `reuse_judged` edges,
`output/oss_issues.json`, the extraction sidecar — renders `LLM
(cached)`: reused LLM output must not read as fresh. Run status gains
`llm_mode` (`"llm" | "rule-based"`) and `degraded_reasons
[{touchpoint, error}]`, served by `GET /api/status` (M16 adds
`free_tier` + `llm_model` — §Free-tier routing below). S6 `output.py` and
the C2 panel render these labels; this table is the only definition.

Label-resolution rules (built 2026-10-05): a gap row's label comes from
the winning `TRANSFERS_TO` edge — on equal confidence the reused edge
wins (the M12 purity insight makes tied values interchangeable, so
"LLM (cached)" is the honest source of a tied score). A judge result of
`"no candidates"` is structural — nothing plausible to judge against —
not an outage: the row keeps its structural verdict ("gap", confidence
0 by absence) labeled `Rule-based`, and no degraded banner fires. An
LLM-judged target that produced no usable scores renders the same
structural row labeled `LLM` (the LLM did look). Cache hits relabel from
the record itself: an OSS cache entry with a relevance rationale renders
`LLM (cached)`, without one `Rule-based`.

### Done criteria (M15)

1. LLM mode + no key: the run is refused before any work — server 409 /
   CLI non-zero — and the panel shows the actionable message next to the
   key field.
2. With a key present, a mid-run LLM failure completes the run with
   `degraded_reasons` set, a panel banner, and every affected row/section
   labeled — no rule-based result is ever presented as an LLM result.
3. Rule-based mode (toggle off) runs end-to-end; every output says
   "Rule-based mode" up front and unjudged targets are labeled, not
   scored 0.
4. Cache hits render `LLM (cached)`.
5. `m15_check.py` + `test_m15.py` cover pre-flight refusal, loud
   degradation (stubbed failing judge/oss), rule-based labeling, the
   provenance vocabulary, and panel markup (key never in
   `chrome.storage`); `ruff check .`, `pytest`, `node --check` clean;
   `m10_check`–`m14_check` regressions PASS.
6. One live interactive pass (panel toggle: keyless refusal, keyed run,
   deliberate OFF run) recorded in [03-milestones.md](03-milestones.md)
   M15.

## Free-tier routing (M16 — Designed)

Opt-in zero-cost path for users with no LLM subscription. `free_tier` is a
run-level flag (default **off**) that routes every call to OpenRouter
`:free` model IDs. It still requires an OpenRouter key of the user's own —
minted by the panel's Connect button or pasted via the M14 form (connect
flow: [12-extension.md](12-extension.md) §M16 A) — because OpenRouter free
models are $0-per-request, **not** keyless. The trade the mode makes,
stated once here: free endpoints may log or train on inputs, carry their
own rate limits (~50 requests/day without purchased credits, ~1000/day
once ≥$10 credits exist), and have lower availability than paid ones. The
consent gate and disclaimer copy are panel surface
([12-extension.md](12-extension.md) §M16 B); enforcement lives here: a run
with `free_tier: true` is refused (409) unless `privacy_ack: true`
accompanies it — the gate must not be UI-only.

- **Free model list.** `FREE_MODELS` — an ordered fallback list of `:free`
  IDs in `llm.py` config (examples as of 2026-10-05:
  `google/gemma-4-26b-a4b-it:free`, `nvidia/nemotron-3-super-120b-a12b:free`);
  the free set churns, so this list is config, not a spec constant. Every
  touchpoint (extraction, bridge, judge, synthesis, OSS) uses it. Quality
  warning that belongs in the disclaimer: extraction and judging are the
  quality-sensitive calls, and free models may measurably degrade gap
  analysis vs. the default DeepSeek V4 Flash.
- **Interaction with M15.** `use_llm: false` wins — rule-based mode
  ignores `free_tier` entirely. M15's pre-flight refusal message (LLM
  mode, no key) gains a "Connect free LLM" action
  ([12-extension.md](12-extension.md) §M16 A). Mid-run quota exhaustion —
  a 429 that survives retries — is an ordinary loud degradation:
  `degraded_reasons` gets `free quota exhausted — add your own key or wait
  for the reset`, rendered in the M15 banner. Provenance labels are
  unchanged (`LLM` is `LLM` whatever the price); the status fields carry
  the mode instead.
- **Status fields (extends §Provenance vocabulary).** `free_tier` (bool)
  and `llm_model` (the `:free` ID currently answering calls — it moves
  when the fallback list rotates) join `llm_mode` / `degraded_reasons` on
  `GET /api/status`.

## Retry & failure handling (M16 — Designed)

Hardening of the `chat()`/`judge()` retry loops for flaky free endpoints;
it applies to every provider. All of it sits **below** M15's degradation
layer: retries are spent inside the single call, and the layer above sees
exactly one outcome — success, or one failure with one reason.

- **Classify before retrying.** Transient (429, 5xx, timeouts, connection
  errors) retry. Non-transient (401/403 bad key, 400 malformed request,
  404 unknown model) fail immediately into M15's loud-degradation path —
  retrying a bad key burns the whole run's budget for nothing.
- **Backoff.** Exponential with full jitter: base 2s, factor 2, cap 60s.
  Honor `Retry-After` when the response carries it (OpenRouter sends one
  on 429): wait `min(retry_after, 60s)` instead of the computed value.
  Free mode raises the attempt cap from 3 to 5 — free endpoints flap
  under load.
- **Bounded attempts — fix the nesting.** Today `judge()` parse-retries
  re-invoke `chat()`, each with its own `max_retries`, multiplying attempts
  up to `max_retries²` per logical call. After M16 the total API attempts
  per logical `judge()` call are bounded by `max_retries` regardless of
  parse-retry nesting.
- **Model fallback (free mode).** On attempts exhausted via 429/5xx, or
  on model-unavailable, advance to the next `FREE_MODELS` entry (one
  rotation through the list) before failing the call.
- **Per-touchpoint timeout.** Request timeout becomes explicit instead of
  the SDK default: 120s for judge / synthesis / bridge / OSS; extraction
  keeps a 30-minute budget until
  [03-milestones.md](03-milestones.md) §Open (extraction latency) resolves
  the speed side. A timed-out call retries under the transient class.

## Done criteria (M16)

1. Connect: a keyless user reaches "Connected ✓ (OS keyring)" from the
   panel via one click + OpenRouter login, with no key ever pasted; the
   minted key lands in the `OPENROUTER_API_KEY` keyring slot; no key
   material is ever present in `chrome.storage`.
2. Free mode runs end-to-end on `:free` models; the server refuses
   `free_tier` without `privacy_ack` (409); `GET /api/status` reports
   `free_tier` + `llm_model`.
3. Retry behavior verified with stubs: transient failures recover within
   the attempt budget and honor `Retry-After`; non-transient errors fail
   on the first attempt; total attempts per logical call ≤ `max_retries`;
   free-mode fallback advances to the next model on model-unavailable.
4. Quota exhaustion degrades loudly through M15's banner + reason — never
   silently.
5. `m16_check.py` + `test_m16.py` cover the callback/exchange/keyring flow
   (stubbed exchange), the consent refusal path, retry classification,
   and model fallback; `ruff check .`, `pytest`, `node --check` clean;
   `m10_check`–`m15_check` regressions PASS.
6. One live interactive pass (connect with a real free OpenRouter account;
   one free-mode analyze + plan; one observed quota/429 message) recorded
   in [03-milestones.md](03-milestones.md) M16.

## Known limits

- Extraction call latency ~19 min on DeepSeek V4 Flash (one-time per
  resume via artifact reuse). Fix path: faster extraction model or
  timeout + retry — M16 implements the timeout + retry half
  (§Retry & failure handling); the faster-model half stays open. See
  `03-milestones.md` §Open (extraction latency).

## History (links, not copies)

- Decisions: `02-decisions.md` (provider rows, keyring-only secret rule,
  M15 presence-policy rows, M16 free-tier/retry rows).
- Milestones: `03-milestones.md` M3, M8, M15 (Built), M16 (Designed).
- Deferred: `03-milestones.md` §Deferred #6 (local-model benchmark).
