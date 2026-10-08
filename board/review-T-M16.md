# Review — T-M16 (free-tier LLM access)

- **Reviewer:** reviewer session (branch `agents/reviewer-task-t-m16-verification`)
- **Diff reviewed:** `impl/T-M16` @ `2626fee` vs `b154b11` (task commits `fab38d8` + `2626fee`)
- **Verdict:** **REJECT** — 3 acceptance-criteria violations (2 of them
  functional breaks of the shipped pipeline), 1 spec defect filed separately.
- **Scope check:** PASS — the diff touches exactly the task's file list
  (`llm.py`, `server.py`, `cli.py`, `extension/sidepanel.{js,html,css}`,
  `test_m16.py`, `m16_check.py`, `board/verify-T-M16.md`). `cli.py` is not in
  the task's "Files to touch" list but is required run-state plumbing for
  `free_tier` and is explicitly named in the implementer handoff; treated as
  in-scope. No out-of-scope changes found.

## Violations

### V1 — CRITICAL: every LLM call is broken (`chat()` calls the wrong SDK resource)

`src/skill_gap_agent/llm.py:229`

```python
resp = client.completions.create(   # was: client.chat.completions.create
    model=model,
    messages=messages,
    temperature=cfg.temperature,
)
```

`client.completions` is the OpenAI **legacy text-completions** resource. Its
`create()` takes `prompt` (a string), not `messages`, and returns
`CompletionChoice` objects that carry `.text`, not `.message.content`. The
pre-M16 code used `client.chat.completions.create(...)` correctly.

Verified against the real SDK (`openai` 3.24.0):

```
params: ['self','model','prompt','best_of','echo',...]   # no 'messages'
has messages: False
CompletionChoice fields: ['finish_reason','index','logprobs','text']
```

and by running the shipped `chat()` with a dummy key:

```
CHAT FAILED: LLMError LLM call failed after 1 retries:
Missing required arguments; Expected either ('model' and 'prompt') or
('model', 'prompt' and 'stream') arguments to be given
```

Impact: **every** LLM touchpoint (extraction, bridge, judge, synthesis, OSS)
fails on the first attempt. Because the failure is a client-side `TypeError`
with no `status_code`, `_classify_error` (`llm.py:152-172`) falls through to
its "unknown errors are transient" branch, so each call burns its whole
attempt budget and then degrades loudly. The run still completes, but 100% of
LLM output is lost — M15's loud-degradation path masks a total outage as a
"flaky endpoint". This breaks acceptance criteria 2 and 4 and regresses the
M3/M15 built behavior.

Why the gate missed it: `m16_check.py` stubs `llm._client` with a fake whose
`completions.create(**kwargs)` accepts anything, so the wrong resource name
and the wrong response shape are never exercised. `m10_check`–`m15_check`
stub at the `judge`/`synthesis`/`oss` module boundary, so they never reach
`chat()` either. The suite is green while the real path is dead.

### V2 — HIGH: free-mode `judge()` still multiplies attempts (the spec's explicit fix is not delivered)

`src/skill_gap_agent/llm.py:286-291` and `llm.py:304-306`

```python
max_retries = RETRY_ATTEMPTS_FREE if cfg.free_tier else cfg.max_retries
for attempt in range(max_retries):
    raw = chat(prompt, system=system, cfg=_single_attempt(cfg))
```

`_single_attempt()` sets `max_retries=1` but leaves `free_tier=True`, and
`chat()` recomputes `max_retries = RETRY_ATTEMPTS_FREE if cfg.free_tier else
cfg.max_retries` (`llm.py:221`) — so the override is ignored and each
`chat()` spends 5 attempts. The outer loop then runs 5 times.

Verified with a stub where every API attempt is a transient 429:

```
free-mode judge API attempts (spec bound: 5): 25
```

Spec `05-ai-caller.md` §Retry & failure handling: "After M16 the total API
attempts per logical `judge()` call are bounded by `max_retries` regardless
of parse-retry nesting." Acceptance criterion 3 ("total attempts per logical
call ≤ `max_retries`") fails in free mode — the mode M16 exists for. The
non-free path is correct (3 attempts, verified), and `m16_check.py`'s
`check_bounded_attempts` only tests the non-free path, so the gap is untested.

### V3 — HIGH: the OAuth exchange can never succeed from the panel (contract mismatch)

`extension/sidepanel.js:256` sends `{code_verifier, state}` — no `code`.
`src/skill_gap_agent/server.py:783-787` requires `code`:

```python
code = body.get("code")
if not isinstance(code, str) or not code:
    self._json(400, {"error": "code must be a non-empty string"})
```

The panel never learns the code: `GET /api/oauth/pending` returns only
`{"pending": bool}` (`server.py:556-561`), and the callback page
(`server.py:551`) stores the code server-side without echoing it. So the
panel's exchange POST always gets 400, `exchangeOauth()` throws, and the
panel shows "Connect failed: code must be a non-empty string".

Impact: acceptance criterion 1 ("a keyless user reaches 'Connected ✓ (OS
keyring)' from the panel via one click + OpenRouter login") is not met — the
connect flow cannot complete end-to-end. `m16_check.py` passes only because
it hand-crafts `{"code": "one-time-code", "code_verifier": ...}` and never
exercises the panel's actual request body.

### V4 — MEDIUM: `llm_model` is never populated, so the status field is always null

`src/skill_gap_agent/server.py:241` reads `values.get("llm_model")` from
graph state, but nothing ever writes `llm_model` into `AgentState` or into
`_run` (grep: the only occurrences are the read, the `None` initializer at
`server.py:87`, the reset at `server.py:675`, and the panel's read at
`sidepanel.js:333`). `GET /api/status` therefore always reports
`llm_model: null`, and the panel's free-mode header always falls back to
"model chosen at run time from the free list".

Spec `05-ai-caller.md` §Free-tier routing: "`llm_model` (the `:free` ID
currently answering calls — it moves when the fallback list rotates) join
`llm_mode` / `degraded_reasons` on `GET /api/status`." Acceptance criterion 2
("`GET /api/status` reports `free_tier` + `llm_model`") is only half met —
`free_tier` is wired, `llm_model` is a dead field.

### V5 — MEDIUM: free-mode fallback does not advance on 429/5xx exhaustion

`src/skill_gap_agent/llm.py:238-243` rotates only when `_model_unavailable(e)`
is true (404, or the message contains "unavailable"/"not a valid model").
Spec §Retry & failure handling: "On attempts exhausted via 429/5xx, or on
model-unavailable, advance to the next `FREE_MODELS` entry (one rotation
through the list) before failing the call."

Verified: five 429s in free mode try the same model five times —

```
models tried on 429 exhaustion:
['google/gemma-4-26b-a4b-it:free', 'google/gemma-4-26b-a4b-it:free',
 'google/gemma-4-26b-a4b-it:free', 'google/gemma-4-26b-a4b-it:free',
 'google/gemma-4-26b-a4b-it:free']
```

The 404/model-unavailable half works (verified: entry 0 → entry 1). The
429/5xx half — the case the spec calls out for flaky free endpoints — does
not. Acceptance criterion 3's "free-mode fallback advances to the next model
on model-unavailable" is met literally; the 429/5xx rotation is not.

### V6 — LOW: per-touchpoint timeout is not wired per touchpoint

`src/skill_gap_agent/llm.py:145-146` applies `DEFAULT_TIMEOUT_SECONDS` (120s)
to every call unless a caller sets `cfg.timeout`. No caller sets it:
`EXTRACTION_TIMEOUT_SECONDS` (`llm.py:76`) is defined but never referenced,
and `free_cfg()` (`llm.py:309`) is dead code (no call sites). So extraction
gets 120s, not the specified 30-minute budget — spec §Retry & failure
handling: "extraction keeps a 30-minute budget until §Open (extraction
latency) resolves the speed side."

This is a real behavior change for extraction (a ~19-minute call per
`05-ai-caller.md` §Known limits would now time out at 120s and retry). It is
listed LOW only because V1 currently prevents any call from reaching the
network; it becomes HIGH once V1 is fixed.

## Acceptance criteria scorecard

| # | Criterion | Result |
|---|---|---|
| 1 | Connect reaches "Connected ✓ (OS keyring)", key in keyring slot, never `chrome.storage` | **FAIL** (V3) |
| 2 | Free mode runs end-to-end on `:free`; 409 without `privacy_ack`; status reports `free_tier` + `llm_model` | **FAIL** (V1, V4) |
| 3 | Retry stubs: transient recovers + `Retry-After`; non-transient first attempt; attempts ≤ `max_retries`; fallback advances | **FAIL** (V2, V5) |
| 4 | Quota exhaustion degrades loudly through M15 banner + reason | **FAIL** (V1 — all calls fail; reason is a client-side TypeError, not a quota message) |
| 5 | `m16_check.py` + `test_m16.py` cover the flows; `ruff`/`pytest`/`node --check` clean; `m10`–`m15` regressions PASS | **PARTIAL** — suite is green (`board/verify-T-M16.md`) but does not exercise the real `chat()` path, the panel's exchange body, or free-mode bounded attempts |
| 6 | One live interactive pass recorded in `03-milestones.md` M16 | **NOT DONE** — human/planner step, correctly out of implementer scope |

## What is correct

- Consent gate is enforced server-side: `free_tier` without `privacy_ack` →
  409 before any work (`server.py:659-667`), verified by `m16_check.py`.
- Verbatim disclaimer copy matches `12-extension.md` §M16 B word-for-word;
  the consent checkbox is not pre-checked; consent persists as
  `{free_consent_at, consent_version}` only.
- No key material in `chrome.storage`; the minted key goes to the
  `OPENROUTER_API_KEY` keyring slot via `secrets.set_secret`
  (`server.py:806`); the exchange response is never echoed to the client.
- One-time code with a 10-minute TTL; mismatch and exchange failure store
  nothing (`server.py:551`, `_oauth_pending_code`).
- Non-transient classification (401/403/400/404) fails on the first attempt
  in the non-free path (verified: 1 attempt).
- `Retry-After` is honored as `min(retry_after, 60s)` (verified: sleep 7.0s).
- `ruff check .`, `pytest` (17 passed), `node --check`, `m10`–`m15` all PASS
  as recorded in `board/verify-T-M16.md`.

## Security-sensitive surface (for the human's periodic security review)

Flagged, not blocking:

1. **OAuth `state` is not validated server-side.** `12-extension.md` §M16 A
   step 4 says "state must match". The server stores the callback code
   without the state (`server.py:551`) and `/api/oauth/pending` ignores the
   `state` query param (`server.py:556-561`); the panel compares nothing
   either (`sidepanel.js:233`). The PKCE `code_verifier` still binds the
   exchange to the initiating client, so this is a CSRF-hardening gap rather
   than a key-disclosure hole — but the spec's stated check is absent.
2. **`/api/oauth/callback` accepts any `code` from any origin.** It is a
   top-level navigation on `127.0.0.1:8000` with no origin check; a malicious
   page could plant a code. The one-time TTL and the verifier requirement
   limit the impact.
3. **`_exchange_openrouter_code` uses `urllib.request.urlopen` with a fixed
   URL** (`server.py:285`) — no SSRF surface, but it does not set a
   `User-Agent` and surfaces raw exception text to the client
   (`server.py:797`), which could leak internal detail.
4. **`/api/oauth/pending` is unauthenticated** and reveals whether a code is
   waiting. Low impact on a localhost-only server.

## Spec defect (filed separately, not a rejection ground)

`board/issues/T-M16-01-oauth-code-transport.md` — the spec does not say how
the panel obtains the `code` to POST to `/api/oauth/exchange`. §M16 A step 4
says the panel "polls `GET /api/oauth/pending?state=…` (state must match),
then `POST /api/oauth/exchange {code, code_verifier}`", but step 3 has the
server store the code and never return it. The implementer's reading (server
holds the code, panel sends only the verifier) is a reasonable resolution of
an under-specified contract; V3 is the mismatch between that reading and the
handler's validation, which the spec should settle.

## Required before re-review

Fix V1–V5 (V6 recommended), then re-run the task's verify command. The
re-review will check only these violations plus the changed parts, per the
reviewer role's one-pass rule.
