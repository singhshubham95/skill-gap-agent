# Issue T-M16-01 — OAuth `code` transport is under-specified

- **Filed by:** reviewer (T-M16 review)
- **Severity:** spec defect (not an implementer rejection ground)
- **Status:** open
- **Related:** `specs/12-extension.md` §M16 A; `specs/05-ai-caller.md` §Done
  criteria (M16) #1; review note `board/review-T-M16.md` V3

## What is ambiguous

`specs/12-extension.md` §M16 A step 4 says:

> The panel polls `GET /api/oauth/pending?state=…` (state must match), then
> `POST /api/oauth/exchange {code, code_verifier}`.

But step 3 says the server "stores the one-time `code` (in-memory, 10-minute
TTL) and serves a tiny 'Connected — return to the side panel' page". The spec
never says how the panel comes to hold the `code` it is supposed to POST:

- the callback page does not echo it,
- `GET /api/oauth/pending` is described only as a poll target (the spec does
  not say whether it returns the code or just a pending flag),
- and the panel is a side panel, not the tab that received the redirect, so
  it cannot read the callback URL itself.

## Why it matters

The implementer resolved the ambiguity by having the server hold the code and
the panel send only `{code_verifier, state}`. The server handler, however,
validates `code` as a required non-empty string and rejects the panel's body
with 400 — so the connect flow cannot complete from the panel (review note
V3). Either reading is defensible; the spec must pick one so the panel and
the handler agree.

## Options for the planner

1. **Server-held code (matches the implementer's reading).** State explicitly
   that the panel never sees the code; `/api/oauth/exchange` takes
   `{code_verifier, state}` and the server pairs it with its stored code.
   Drop `code` from the step-4 contract.
2. **Panel-held code.** State that `/api/oauth/pending` returns the code once
   (and only to a matching `state`), and that the panel POSTs
   `{code, code_verifier}`. This makes the `state` check load-bearing and
   should say so.

Either way, §M16 A should also state whether `state` is validated server-side
or panel-side — the current text ("state must match") does not say which
component enforces it, and neither does today (see review note, security
section item 1).

## Resolution

**Option 1 — server-held code — adopted** (planner, 2026-10-06). The panel
never sees the code; `GET /api/oauth/pending` returns a pending flag only
and only for a matching `state`; `POST /api/oauth/exchange` takes
`{code_verifier, state}` and the server pairs the `state` with its stored
code. `state` is validated **server-side** at callback time (unknown or
missing `state` → rejected, nothing stored) and again at exchange time.
Rationale: keeps the short-lived code out of the extension entirely
(keyring-only secret rule), makes the `state` check load-bearing in one
place, and matches the implementer's reading. `specs/12-extension.md`
§M16 A steps 3–5 updated accordingly (2026-10-06).
