# C2 — Chrome Extension Shell

Browser surface for the pipeline: capture job descriptions on LinkedIn,
analyze gaps, and generate the learning plan in a side panel — with the
pipeline running in the local `server.py` process. The extension is a thin
client.

**Status: Built** (M13, 2026-10-03; link-navigation fix 2026-10-04 —
verification record in [03-milestones.md](03-milestones.md) M13). Code:
[../extension/](../extension/), `m13_check.py`. End goal (why this exists):
S6 [09-practice-planner.md](09-practice-planner.md) §End goal. **M14
self-serve setup ✅ Built 2026-10-04 (§M14 below; verification record in
[03-milestones.md](03-milestones.md) M14).**

## End-user flow

The user browses LinkedIn job descriptions in Chrome. Clicking the extension
action opens a **side panel** — window-level, it stays open while the user
switches tabs or navigates between JDs. Per JD: click **Capture JD**
(append to an only-growing list shown in the panel). Then **Analyze gaps**
→ the ranked gap table renders in the panel. Then **Generate plan** →
projects + good-first-issues render below the gaps. Nothing navigates away;
the local pipeline does the thinking.

## UI surface = Chrome side panel

(decision rows in [02-decisions.md](02-decisions.md)). The popup was
rejected: it closes on any click-away, which kills the capture loop (browse
JD → return to panel). The in-page overlay was rejected: navigating to the
next JD destroys the DOM node, so state must survive in extension storage
anyway. The side panel is the platform's answer to exactly this workflow.

## Capture

A content script on `https://www.linkedin.com/jobs/*` ports the extraction
logic of
[../tools/linkedin_jd_bookmarklet.js](../tools/linkedin_jd_bookmarklet.js)
(find the `[id^="JobDetails_AboutTheJob_"]` block, take `innerText` +
`document.title` + `location.href`). The panel asks the active tab via
`chrome.tabs.sendMessage`; the content script answers with
`{title, url, text}`. The list lives in `chrome.storage.local`
(`capturedJds`, deduped by URL, re-capture updates text). No `tabs` /
`activeTab` permissions: the content script returns everything the panel
needs. JD text is **untrusted web content** — the panel renders it with
`textContent` only, never `innerHTML`.

**Collapsed descriptions — assist, don't act (M23).** LinkedIn truncates
long JDs behind a "…see more" control
(`[data-testid="expandable-text-button"]`). The script **never clicks it**
(or anything else on the page) — a synthetic click is state-changing
automation and the strongest ToS signal in the product. Instead, when the
block is still truncated at capture time, the script:

1. scrolls the control to the center of the viewport
   (`scrollIntoView({block: "center"})`) and focuses it (focus ring),
2. paints a persistent Ctrl+F-style yellow highlight on it (inline style:
   outline + warm background) with a `title` tooltip ("Click to expand the
   job description, then press Capture again"),
3. answers `{ok: false, error: …}` so the panel's status line tells the
   user to expand and retry.

Only the user's click on LinkedIn's own control expands the text; the
next capture reads it normally. Capture-scoping guardrails (unchanged,
now explicit): strictly single-page, strictly one user click per capture,
no batch capture, no scroll harvesting, no reads outside
`https://www.linkedin.com/jobs/*`. Residual LinkedIn ToS exposure from
DOM extraction itself is inherent to the product's premise and recorded
in [02-decisions.md](02-decisions.md) (M23 row) — the assist-not-act rule
is what keeps the line defensible.

## Run contract (extension → local server)

`POST /api/run` body:
`{phase, jds, top_n, skills_path?, provider?, skip_judge?, skip_oss?, no_llm_oss?}`
(`use_llm?` arrives with M15 — §M15 below; `free_tier?` + `privacy_ack?`
with M16 — §M16 below).

| `phase` | Behaviour |
|---|---|
| `"gaps"` | Write each captured JD to `output/captured_jds/*.txt` (same `title\nurl\n\ntext` shape as the bookmarklet; `ingest.py::ingest_jds` reads the folder unchanged — it replaces `data/jds/` as `jds_path`), then run the `cli.py` graph with `two_phase=True`: the graph pauses at a `pause` node right after `rank` via `interrupt()`; status becomes `paused`. `GET /api/gaps` then serves `output/gaps.json` (written by the rank node). |
| `"plan"` | Resume the paused run (`Command(resume=...)`) through `synthesize` → `oss` → `output`; `GET /plan.html` serves the result. 409 if no run is paused. |
| (absent — legacy M11) | Full one-shot run, as before. |

Single-run guard unchanged (409 while `running`). `skills_path` defaults to
`data/skillsdataset.json` (server `--skills` flag); a resume file works too
(M8 extraction runs before the graph). Request expectations (origin gate,
Content-Type, `skills_path` containment) are in §Security posture — every
caller above satisfies them (the panel sends `application/json` /
`application/octet-stream` with its `chrome-extension://` origin).

## Why one graph with a pause, not two runs

The pause is the same `interrupt()` machinery the confidence gate uses (M7):
state continuity is free — the same `SkillGraph` instance and the same
`gaps` list flow from phase 1 into phase 2. A second full run would
re-ingest and re-judge (or require cache plumbing to avoid it). The
checkpointer records the pause; the SkillGraph itself stays in the in-memory
runtime registry (decision in [02-decisions.md](02-decisions.md)), so both
phases must run in one server process — true for the side-panel workflow.

## Judge cache reuse for re-analysis (`reuse_judged`)

The M12 insight (see [11-sweep.md](11-sweep.md)) — the judge's score for
target `T` is a pure function of `T` — means that re-analyzing after adding
one JD must not re-pay ~20 LLM calls. With `reuse_judged`, the judge node
first copies `TRANSFERS_TO` edges from `output/graph.json`, then judges only
targets still unmatched; the judge report merges by target. The CLI default
stays fresh-judging (the M6 validation semantics); the extension sets the
flag.

## Rendering

The gap table is rendered natively in the panel from `/api/gaps` JSON. The
full plan renders in an
`<iframe sandbox="allow-popups allow-popups-to-escape-sandbox">` pointed at
`/plan.html` — the M10 renderer (self-contained, escaped, no JS) becomes the
side-panel body as S6 predicted. Every plan link carries
`target='_blank' rel='noopener noreferrer'`, so clicking one opens a new
browser tab and can never navigate the iframe away from the plan (amended
2026-10-04 after a user-reported mis-click lost the plan — fix note in
[03-milestones.md](03-milestones.md) M13). The two `allow-popups*` tokens
are what make `target='_blank'` work inside a sandbox at all (without them
the popup is silently blocked or inherits the no-script sandbox);
`allow-scripts` stays off. A **Reopen plan** control re-points the iframe at
`/plan.html` — the file stays on disk, so recovery costs no re-run. JD links
resolve against `data/jds/` **and** `output/captured_jds/` (exact-name
matches only), so extension-run links work too.

## Security posture

Threat model (M20, from the public-release review —
[../SECURITY-REVIEW.md](../SECURITY-REVIEW.md) S1/L4): the user browses
hostile web pages on the same machine where the local agent holds their
resume-derived data and LLM keys. Primary attacker = **a web page using the
browser as a confused deputy** against `127.0.0.1`; secondary = stray local
processes on a shared machine. The realistic chain to kill: CSRF a run →
overwrite the stored LLM key → ingest an arbitrary local file via
`skills_path` → exfiltrate it through the attacker's key as LLM prompt text.

Three barriers, in order (server side):

1. **Request-origin gate — the primary barrier.** Any request that carries
   an `Origin` header must present the extension's origin
   (`chrome-extension://…`) or the server's own origin
   (`http://127.0.0.1:<port>` / `http://localhost:<port>` — the M11 index
   page's fetches); anything else — web pages, `Origin: null` — is refused
   **403 before any handler runs**. Requests with **no** `Origin` (browser
   navigations: the plan iframe, the JD viewer, the OAuth callback
   redirect; and non-browser clients: CLI and the `mN_check` harnesses)
   pass the gate unchanged. Web pages cannot omit or forge `Origin`, so
   every fetch/XHR/form attack is turned away at the door.
2. **Content-Type enforcement.** JSON endpoints (`/api/run`, `/api/key`,
   `/api/oauth/state`, `/api/oauth/exchange`) accept only
   `application/json`; `POST /api/resume` only `application/octet-stream`;
   anything else 415s. A cross-origin fetch with these content types
   triggers a CORS preflight, which fails (no `OPTIONS` handler, no
   `Access-Control-Allow-*`), so even a hypothetical origin-gate bypass
   could not smuggle a browser "simple request". *This corrects the M13
   claim (decision row superseded 2026-10-11) that preflight alone was the
   barrier: a JSON body sent as `text/plain` is a simple request and needs
   no preflight — the origin gate is what actually stops it.*
3. **`skills_path` containment (defense in depth).** An explicit run-body
   `skills_path` must be an existing `.json` under the repo root or the OS
   temp dir (check fixtures live there); anything else 400s before a run
   starts. `_resolve_skills` precedence is unchanged; `cli.py` keeps
   unrestricted paths (terminal-side).

Unchanged properties: the server binds `127.0.0.1` and sends **no CORS
headers**, so cross-origin reads stay impossible even for requests the gate
allows (navigations may *display* data to the user; a foreign page can never
*read* it).

**Transport (M20, L4):** the panel's `serverBase` accepts `http://` only for
`localhost`/`127.0.0.1` (the default); any other host must be `https://`.
Resume text, JDs and API keys must never transit plaintext to a non-loopback
host; invalid values fall back to the default and are never persisted.

**Accepted residual risk:** a process running **as the same OS user** sends
no `Origin`, passes the gate, and can read `output/` directly anyway — a
session token would not change that boundary (any local process can already
read the resume file on disk). Restore trigger for token pairing: the
product starts handling other users' data or runs as a service — recorded in
`03-milestones.md` §Deferred.

## Data disclosure (M21)

Goal (security finding S2/L5): every user-facing claim about where data
goes must be **accurate**, and the destinations must be **named** before
the user's first upload or analysis. A privacy policy cannot outrank an
in-product claim that contradicts it — the copy is the contract.

**Copy rules** (panel surfaces — this section is their one design home):

1. At the upload surface (setup hint + the `resumeprivacy` hint): the
   two-part truth, in these words' sense — the *file* is kept locally
   under `output/uploads/`; the *extracted text* is sent over HTTPS to the
   AI provider the user selects for skill extraction and analysis; it is
   never sent to the extension's developer. The old "It stays on your
   machine" phrasing is **banned** — it conflated file storage with data
   processing (struck in the M14 decision row, superseded by M21).
2. Named destinations + caveats (upload disclosure and near the provider
   select): OpenRouter forwards to the underlying model (default DeepSeek
   via OpenRouter); Z.ai GLM (`open.bigmodel.cn`) and OpenAI are the other
   providers — some process data outside your country (DeepSeek/Z.ai:
   China); free providers may log or use inputs for training (M16's
   verbatim disclaimer covers this and stays unchanged); GitHub Search
   receives skill-gap terms derived from the analysis, never resume text;
   the developer receives nothing (no telemetry, no backend).
   **M9 conversational intake (2026-10-12):** at Analyze gaps the panel
   asks short profile questions (skill review, depth, calibration); your
   **answers** are sent to the same AI provider for grading/analysis —
   named here alongside the resume-derived text, never a new silent flow.
3. The hosted privacy policy
   ([../docs/privacy-policy.md](../docs/privacy-policy.md), served from
   GitHub Pages) mirrors this destination list — it is the same register,
   restated for the store audience. When M17 lands, LangSmith is
   **developer-only tooling** — nothing in the product can activate it
   (§Scope boundary in
   [14-observability.md](14-observability.md)) — so it is **not** a panel
   destination and needs no consent surface: the privacy policy gains one
   completeness line and the store register notes the capability. Do not
   add even that before the code exists. The store-submission register (permission justifications,
   dashboard declarations, listing copy) is the derived
   [../CHROMEWEBSTORE.md](../CHROMEWEBSTORE.md) — same mirror rule.

**First-use consent (gate is not UI-only — the M16 lesson):** a
`#disclosureack` checkbox at the upload surface, never pre-checked, backed
by a versioned `disclosureConsent` flag in `chrome.storage.local`
({disclosure_consent_at, consent_version}, bumped when the copy changes —
same shape as M16's `freeConsent`). Upload **and** analyze refuse until it
is checked; `POST /api/resume` additionally requires `X-Disclosure-Ack: 1`
(409 otherwise), so no future client can upload without the disclosure
having been presented. Runs (`/api/run`) keep their existing gates (M15
pre-flight, M16 `privacy_ack`); adding a second ack there would churn
every harness for no new exposure — the upload-time consent covers the
first data flow.

**Deferred (user decision 2026-10-11, restore triggers in
`03-milestones.md` §Deferred):** PII minimization (strip names/contact
details before LLM calls — skill extraction never needs them). ~~and a
manual no-cloud extraction toggle~~ (superseded by the M24 row —
Rule-based mode is the no-cloud path). The disclosure copy is amended by
M24 (§M24): the destination is "selected above" and the copy states that
extraction follows the selected mode.

## M14 — self-serve setup (✅ Built 2026-10-04)

Goal: the end user never opens a terminal for setup — resume, LLM key and
server start all happen from the panel or one double-click. Three slices,
built independently. Decision rows in
[02-decisions.md](02-decisions.md) (M14); verification record in
[03-milestones.md](03-milestones.md) M14.

### A. Resume upload (panel + server)

- Panel "Your resume" section: file input `accept=".pdf,.docx,.txt"` (the
  exact set `resume.extract_text` supports). On selection the file is
  uploaded; the panel shows filename, extraction path (LLM / regex
  fallback / cached artifact) and extracted skill count.
- Transport: `POST /api/resume`, body = **raw file bytes**
  (`Content-Type: application/octet-stream`), original filename in an
  `X-Filename` header. No multipart: the stdlib `cgi` module is gone in
  Python 3.13+, and hand-rolled multipart parsing is a footgun — `fetch`
  can send the `File` object as the body directly.
- Server validation before anything touches disk: 10 MB cap (413),
  extension allow-list (415 otherwise), magic-byte sniff for PDF (`%PDF`)
  and DOCX (`PK\x03\x04`), sanitized basename only (no separators, no
  `..`) — server keeps the sanitized name under `output/uploads/`
  (`output/` is already gitignored, so resume PII never reaches git).
- On upload the server runs `resume_to_skills_json(use_llm=True, auto=True)`
  immediately and answers `{ok, filename, skills: n, source: "llm" |
  "regex" | "artifact", warning?}` — `source: "regex"` carries a warning
  that extraction quality is degraded (no key / provider down).
- **Extraction-cache correctness (required):** today
  `output/extracted_skills.json` is reused whenever it exists, regardless
  of which resume produced it — acceptable for one resume per session,
  wrong once the panel has an upload button. Cache is keyed by the source
  resume's SHA-256 in a sidecar `output/extracted_skills.sha256`; mismatch
  ⇒ re-extract. Sidecar, not artifact reshaping: ingest + `m8_check` read
  the artifact JSON directly.
- Run wiring: `skills_path` resolution precedence for `POST /api/run` =
  explicit body `skills_path` → uploaded resume → `--skills` default.
  `GET /api/status` gains `skills: {filename, count, source}` so the panel
  can always show what the next run will use.

### B. LLM key entry (panel + server)

The key is **entered** in the panel but must never be **stored** there.
`chrome.storage.local` is plaintext LevelDB in the Chrome profile — wrong
for secrets. Instead the panel is a secure input form for the existing
keyring path (`secrets.py`, locked 2026-09-27: OS keyring only).

- Panel Settings: provider dropdown (`openrouter` / `glm` / `openai` from
  `llm.PROVIDERS`), password-type key input, "Remember on this machine"
  checkbox (default on), Save. Status shows "key configured ✓ (OS
  keyring)" or "session only".
- `GET /api/providers` → `[{id, model, key_set}]` — booleans only, never
  key material. Any endpoint that could echo a key is a design bug.
- `POST /api/key` `{provider, api_key, remember}`:
  - `remember: true` → `secrets.set_secret(key_env, ...)` → Windows
    Credential Manager / macOS Keychain (encrypted at rest, per-user).
  - `remember: false` → process env var only (env beats keyring in
    `get_secret`); dies with the server process, nothing stored.
  - Response `{ok, key_set: true, stored: "keyring" | "session"}` — never
    echoes the key. POST-only (never GET/query strings — URLs land in
    logs); request bodies of this route never logged.
- Provider plumbing (small code change): `AgentState.provider` +
  `LLMConfig(provider=...)` at cli's three call sites and the resume
  extraction cfg; `POST /api/run` body gains `provider` (default
  `openrouter`).
- Honesty note for docs: resume text still travels to the chosen LLM
  provider at extraction/judge time (the existing cloud-tier decision) —
  uploading keeps it on loopback except for those calls.

### C. Server launcher (double-click, not Native Messaging)

- `tools/start-server.bat`: double-clickable; uses `.venv\Scripts\python.exe`
  if present, else `py -3`/`python`; runs `python -m skill_gap_agent.server`
  with passthrough args; on failure keeps the window open and shows the
  error. Extension offline-hint and READMEs point at it.
- Native-messaging auto-launch (the only way an extension can start a
  process) is deferred — registered host + registry entry + pinned
  extension ID that breaks when an unpacked folder moves. Restore trigger
  in [03-milestones.md](03-milestones.md) §Deferred #14.

### Done criteria (M14 — met 2026-10-04; verification record in roadmap M14)

1. Resume upload from the panel feeds the run without any CLI flag; a
   second, different resume re-extracts (hash check) instead of reusing
   the first one's skills.
2. Key entry works both "remember" (keyring) and "session only"; no
   endpoint or storage surface ever returns key material; nothing lands in
   `chrome.storage`.
3. `m14_check.py` offline PASS (upload validation + hash cache + key
   endpoint with stubbed secrets + run precedence, stubbed
   judge/synthesis/oss like `m13_check.py`); `test_m14.py` wrappers;
   `ruff check .`, `pytest`, `node --check` clean.
4. One live interactive pass (real resume + keyring + full run) recorded in
   [03-milestones.md](03-milestones.md) M14.

## M15 — LLM mode control (✅ Built 2026-10-05)

Semantics — what the toggle means, the pre-flight refusal, degradation
and the provenance labels — live in
[05-ai-caller.md](05-ai-caller.md) §LLM presence policy (the design
home). This section is the panel surface only. Decision rows:
`02-decisions.md` M15; done criteria: [05-ai-caller.md](05-ai-caller.md)
§Done criteria (M15).

- **LLM toggle** (on by default) in the run section. ON reveals the key
  area beneath it: provider dropdown + key state ("key saved ✓ (OS
  keyring)" / "not saved") from `GET /api/providers`, and the M14 key
  form (password input, "Remember on this machine", Save). OFF hides the
  key area and shows "Rule-based mode — no LLM calls".
- **Run contract** gains `use_llm` (bool, default true). LLM mode + no
  key for the selected provider → `/api/run` refuses (409) and the panel
  shows the actionable message inline next to the key field instead of
  starting a run. (`use_llm: false` implies the existing `no_llm_oss`.)
- **Degradation banner**: when `GET /api/status` reports
  `degraded_reasons`, a prominent banner lists them with a re-run hint;
  gap rows and plan sections carry the per-item provenance labels from
  [05-ai-caller.md](05-ai-caller.md) §Provenance vocabulary, and the
  plan header states the run's mode.

## M16 — free LLM access (✅ Built 2026-10-06)

Mechanics — free-model routing, refusal rules, retry semantics — live in
[05-ai-caller.md](05-ai-caller.md) §Free-tier routing + §Retry & failure
handling (the design homes). This section is the panel + server surface:
getting a key without pasting one, and the consent gate. Decision rows:
`02-decisions.md` M16; done criteria:
[05-ai-caller.md](05-ai-caller.md) §Done criteria (M16).

### A. "Connect free LLM" button (OAuth PKCE)

Lives in the M15 key area (LLM toggle ON), beside the M14 paste form —
which stays as the fallback for users who already hold a key from any
provider. A shared extension key was rejected at design time (decision
row, `02-decisions.md` M16): the bundle is world-readable, OpenRouter's
free quota is per-account, and key sharing breaks the provider's terms and
the per-user consent model. Flow:

1. The panel generates `code_verifier`, its S256 `code_challenge`, and a
   random `state` (Web Crypto — no bundler needed; base64url via `btoa`),
   keeping verifier and state in memory only.
2. `chrome.tabs.create` (no new permissions) to
   `https://openrouter.ai/auth?callback_url=http://localhost:8000/api/oauth/callback&code_challenge=…&code_challenge_method=S256&state=…&key_label=skill-gap-agent`.
   The user logs in or signs up — a free OpenRouter account needs no card —
   and authorizes.
3. OpenRouter redirects the tab to the local server, which stores the
   one-time `code` in memory keyed by `state` (10-minute TTL) and serves a
   tiny "Connected — return to the side panel" page. **The `state` is
   validated server-side at callback time**: a callback whose `state` is
   missing or unknown is rejected and stores nothing. Localhost callbacks
   on any port are supported; `server.py` is already bound to
   `127.0.0.1:8000`. The callback is a top-level browser navigation (no
   CORS involved), and the panel's subsequent polls behave like every other
   extension → server call under the existing security posture.
4. The panel polls `GET /api/oauth/pending?state=…` — it returns a pending
   flag only (**never the code**; the code stays server-side, consistent
   with the keyring-only secret rule) and only for a matching `state` —
   then `POST /api/oauth/exchange {code_verifier, state}`. The server pairs
   the `state` with its stored code and exchanges at `POST
   https://openrouter.ai/api/v1/auth/keys`, receives a **user-owned** key,
   and stores it in the OS keyring — the same `OPENROUTER_API_KEY` slot as
   the M14 paste form; the key transits the server's exchange handler only,
   never `chrome.storage` (extends the M14 keyring decision). The panel
   shows "Connected ✓" plus a "Manage key on OpenRouter" link (key-hash
   deep link) so the user can inspect or revoke the key at any time.
5. Failure paths: denial or 10-minute expiry → panel message + retry;
   state mismatch (rejected at callback time or at exchange time) or
   exchange failure → rejected, nothing stored.

### B. Free-mode consent gate

- **Toggle "Use free models (costs nothing)"** under the key area
  (`free_tier` in the run contract; default off). ON reveals the consent
  block and disables the run button until consented.
- **Disclaimer copy (verbatim):** "Free models cost nothing, but the
  providers behind them may log or use your inputs for training. Job
  descriptions are public — **your resume is not**: it contains personal
  information (name, contact details, work history) and will be sent to
  these third-party providers. Your own key's paid endpoints generally do
  not train on inputs. Consent is required before any free-mode run."
- Consent is one explicit checkbox (never pre-checked), recorded in
  `chrome.storage.local` as `{free_consent_at, consent_version}` — a flag
  and timestamp only, never data. Changing the copy bumps
  `consent_version` and re-prompts. The run contract sends
  `free_tier: true, privacy_ack: true` only while consented, and the
  server refuses without `privacy_ack`
  ([05-ai-caller.md](05-ai-caller.md) §Free-tier routing) — the gate is
  not UI-only.
- **Free-mode run header**: "Free mode — model: <llm_model>" from
  `GET /api/status`. Quota exhaustion surfaces through the M15 banner
  with the reason defined in
  [05-ai-caller.md](05-ai-caller.md) §Free-tier routing.

## M18 — panel simplification (✅ Built 2026-10-11; §Done criteria below)

The built panel (M13–M16) exposes every server knob in one flat scroll:
LLM toggle, provider dropdown, key form, remember checkbox, free-tier
toggle, consent block, top-N input, server URL. The actual happy path is
three clicks — Capture → Analyze → Plan. M18 is a **presentation-only**
milestone: the default view shrinks to the happy path and everything else
lives behind one disclosure. The run contract, keyring storage, consent
gate, and provenance labels are unchanged (their homes: §Run contract, M14
§B, M16 §B, [05-ai-caller.md](05-ai-caller.md) §Provenance vocabulary).
Decision rows in [02-decisions.md](02-decisions.md) (M18); roadmap entry
[03-milestones.md](03-milestones.md) M18. This section supersedes the
*panel surface* descriptions of M14 §B, M15 and M16 §B — their semantics
stay as written.

### Overall shape

Single scroll (a guided stepper was considered and rejected — hiding the
JD list behind Back/Next costs context). Every non-essential control moves
into one collapsed **Settings** block: server URL, top-N default, key
management ("change key"), re-upload resume. The panel body becomes:
connection state (silent when fine) → resume line → capture → analyze →
plan.

### Component-by-component

0. **Header / connection.** The "checking local agent…" line shows only
   when there is a problem ("Local agent not running — double-click
   `tools/start-server.bat`"), never when connected. Silence = healthy.
1. **Resume.** No resume → the current M14 §A upload section (with hint).
   After upload → one line `Resume: <file> (<n> skills) · Change`; the
   privacy reassurance copy moves behind a small "why?" disclosure. Upload
   validation, extraction-path display and SHA-256 cache behavior (M14 §A)
   unchanged.
2. **Capture.** Counter merges into the button label ("Capture JD (3)");
   list renders compact one-line titles; "Clear list" stays a quiet link,
   only when the list is non-empty.
3. **Analyze — state-driven mode selection.** On panel open and after any
   key change the panel reads `GET /api/providers` → `key_set` and renders
   one of two states:
   - **Key exists** — a state chip (`Key ✓ verified` / `checking…` /
     `couldn't verify — runs will retry`) plus exactly three mode chips:
     **Free model** ("costs nothing; provider may log inputs" →
     `free_tier: true`, reveals the M16 §B consent block),
     **Paid model** ("uses your key's credits" → `free_tier: false`),
     **Rule-based** ("instant, no AI" → `use_llm: false`).
   - **No key** — a **Create free LLM key** button (the existing M16 §A
     OAuth flow) plus a quiet "or run rule-based (no AI)" link. The button
     disappears once the key is created, saved to the keyring, and
     validated.
   - **Key validation** = `GET https://openrouter.ai/api/v1/key` with the
     stored key (auth-only, free, near-instant) — **not** a billable model
     call. Run once on panel open and after key changes, result cached;
     a status indicator only, never a hard gate (the M15 pre-flight 409
     remains the safety net; a key can pass validation and be revoked an
     hour later). Offline or unverifiable → neutral message, never
     blocking.
   - **"I already have a key"** quiet link reveals the current M14 §B
     paste form (provider dropdown, key, remember, save) — the fallback
     for OpenRouter-paid / GLM / OpenAI owners. Hidden by default; the
     free-OAuth button is not the only path in.
   - "Top gaps" moves to Settings. The M15 degradation banner and
     per-item provenance labels are unchanged.
4. **Gap table.** Columns shrink to `# | Skill gap | Score`; `JDs ·
   Verdict · Source` merge into one small caption line under the skill
   name (e.g. "demanded by 3 JDs · Weak · Rule-based"). Same information,
   provenance preserved per item.
5. **Plan.** Section unchanged (sandboxed iframe + M13 link fix);
   "Reopen plan" appears automatically only when the iframe fails to load
   instead of sitting in the layout permanently.

### Surface changes to earlier sections (once built)

- M14 §B paste form: default-hidden behind "I already have a key".
- M15 LLM toggle: replaced by the three mode chips
  ([05-ai-caller.md](05-ai-caller.md) §LLM presence policy semantics
  unchanged).
- M16 §B free-tier toggle: folded into the mode chips (consent block and
  verbatim disclaimer unchanged).
- Settings gains top-N default, key management, re-upload resume.

### Done criteria (M18)

1. Default view (key saved, some JDs captured) shows only: silent
   connection, resume line, capture control, three mode chips + Analyze +
   results, plan. No provider dropdown, key field, remember/save buttons,
   free-tier toggle, rulehint or top-N input in the body.
2. No-key state shows "Create free LLM key" + a rule-based path; the paste
   form is reachable via one link in both states.
3. Key validation uses the key-info endpoint only (no billable call, no
   key material ever returned); the panel never blocks on validation.
4. All existing behavior preserved: run-contract fields, M15 pre-flight
   refusal + provenance labels, M16 consent gate + server-side
   `privacy_ack` check, M14 SHA-256 resume cache, sandboxed iframe.
5. `m18_check.py` offline PASS (state rendering keyed off `key_set`,
   validation stub, mode → run-contract field mapping) +
   `test_m18.py` wrappers; `ruff check .`, `pytest`, `node --check`
   clean; one live interactive pass recorded in
   [03-milestones.md](03-milestones.md) M18.

## M19 — light/dark theme (✅ Built 2026-10-11; §Done criteria below)

The panel and the plan render in the OS theme by default, with one minimal
override button for when the user wants a different look. Decision rows
in [02-decisions.md](02-decisions.md) (M19); roadmap entry
[03-milestones.md](03-milestones.md) M19. Presentation-only: no run
contract, storage (beyond the one preference flag), or rendering-safety
change (escaping, link targets, sandbox all untouched).

### Theme source: system first, one button on top

- **System path (default, JS-free):** both surfaces carry CSS
  `@media (prefers-color-scheme: dark)` palettes — the browser reports the
  OS theme and the stylesheet follows. `color-scheme: light dark` lets
  form controls and scrollbars follow too.
- **Override button** in the panel header (`Theme: Auto/Light/Dark`):
  cycles Auto → Light → Dark. The choice persists in
  `chrome.storage.local` as `themePref` (a preference flag only). Auto
  removes the override and returns to the system path; Light/Dark set
  `data-theme="light|dark"` on the panel root, whose selectors outrank the
  media query.
- The same two forced palettes exist in `plan.html`'s stylesheet, keyed on
  `data-theme` — so the plan can be overridden by the same mechanism.

### Plan follows the panel

The plan iframe is cross-origin and script-blocked (M13 sandbox), so the
panel cannot reach into it. Instead the panel appends
`?theme=dark|light` to the iframe URL whenever the override is active
(Auto = no parameter), and `GET /plan.html` injects
`<html data-theme='…'>` at serve time for exactly those two values (any
other value is ignored — no attribute, no injection surface). The file on
disk is unchanged. **`plan.html` stays self-contained and JS-free** — the
sandbox has no `allow-scripts`, so an in-page theme script could not run
even if the no-JS decision allowed one.

### plan.html gains its first stylesheet

The M10 renderer emitted unstyled HTML. The theme work needs palettes, so
`render_plan_html` now emits one inline `<style>`: light/dark CSS-variable
palettes, readable typography, and the two `data-theme` override blocks.
Content, escaping and `target='_blank'` links are byte-identical.

### Done criteria (M19)

1. Panel and plan follow the OS theme with no interaction.
2. The header button cycles Auto/Light/Dark, persists across panel
   restarts, and overrides the system theme on both surfaces.
3. `GET /plan.html?theme=dark|light` injects the attribute; other values
   are ignored; `plan.html` on disk gains no JS and stays self-contained.
4. Both themes keep readable contrast on every panel element (inputs,
   buttons, banner, chips, gap captions).
5. `m19_check.py` + `test_m19.py` offline PASS; `ruff check .`, `pytest`,
   `node --check` clean; m10–m18 regressions PASS (record in
   [03-milestones.md](03-milestones.md) M19).

## M24 — mode governs ingestion; setup order (✅ Built 2026-10-11)

The M18 mode chips promised "Rule-based — instant, no AI" and "Free model
— costs nothing", but resume ingestion hardcoded `use_llm=True` with the
paid default config: a Rule-based user's resume still went to the LLM at
upload, and a Free-mode user paid for extraction. M24 makes the mode
govern **every** AI touchpoint on user data — extraction included — and
reorders the panel so key, mode and their consents are settled **before**
the first data flow. Security-review context: this closes the gap between
the §Data disclosure copy contract and actual behavior (copy is the
contract). Decision rows in [02-decisions.md](02-decisions.md) (M24);
roadmap entry [03-milestones.md](03-milestones.md) M24.

### Semantics: one mode, all touchpoints

`free | paid | rule` now governs resume extraction exactly as it governs
the run ([05-ai-caller.md](05-ai-caller.md) §LLM presence policy
unchanged for runs):

| Mode | Extraction at upload |
|---|---|
| `rule` | `extract_skills_regex` — local, nothing leaves the machine |
| `paid` | `extract_skills_llm` via the **active provider's** endpoint (fixes the old default-config gap: GLM/OpenAI selections now honored) |
| `free` | free-tier models (M16 routing) |

Rule-based extraction remains the labeled fallback when an LLM call
fails (M15 provenance vocabulary unchanged).

### Setup order (panel)

1. **AI access** — key chip (`Key ✓ verified` / rejected / no key),
   "Create free LLM key", "I already have a key" + paste form.
2. **Mode + consent** — the three chips and, on Free, the M16 verbatim
   consent block. Hidden entirely in the no-key state (rule is the only
   mode there).
3. **Your resume** — §Data disclosure copy (amended wording: destination
   "selected **above**" + extraction-follows-mode note), the `#disclosureack`
   gate, upload.

Then the unchanged loop: collect → analyze (a one-line mode summary
points back at the setting) → plan.

### `POST /api/resume` contract (M24)

New headers (all validated; defaults preserve the pre-M24 behavior):

- `X-Extraction-Mode: rule | paid | free` (default `paid`) — selects
  `use_llm` + `free_tier` for the extraction call.
- `X-Provider: openrouter | glm | openai` (default `openrouter`) —
  extraction cfg uses it.
- `X-Privacy-Ack: 1` — **required for `free`** (409 otherwise): the M16
  consent gate applies to free-mode ingestion exactly as to free-mode
  runs (the gate is not UI-only — M16 lesson).
- `X-Disclosure-Ack: 1` unchanged (M21).

### Mode-aware extraction cache

The SHA-256 sidecar gains a third line: the **requested mode** class
(`llm` / `rule`). Reuse rules:

- rule requests reuse `rule`-class regex artifacts only;
- llm requests reuse `llm`-class artifacts **only when they were actually
  produced by the LLM** (`source == "llm"`) — a regex-fallback artifact
  is re-extracted (the fallback condition may have passed; quality must
  follow the mode);
- classes never cross (switching modes re-extracts; regex re-extraction
  is instant);
- legacy two-line sidecars are read as class `llm` (the historical
  default), so existing LLM artifacts still hit.

This closes the "first upload freezes quality forever" trap: an upload
made without a key (rule class) upgrades automatically once a key exists
and the mode flips.

### Supersessions

- The Deferred **manual no-cloud extraction toggle** is superseded
  (restore trigger met): Rule-based mode *is* the no-cloud path now —
  extraction runs locally and nothing leaves the machine.
- [12-extension.md](12-extension.md) §Data disclosure copy rule 1's
  "you select below" wording is amended to "selected above" (the
  provider select moved into Setup); `DISCLOSURE_CONSENT_VERSION` bumps
  to 2. M16's verbatim free disclaimer is unchanged.

### Done criteria (M24)

1. Panel order and the mode summary as above; free consent sits with the
   chips and gates upload + analyze.
2. Upload honors mode + provider; free uploads refuse without
   `X-Privacy-Ack`; rule uploads make no LLM call at all.
3. Cache rules hold (incl. legacy sidecars); llm↔rule never cross;
   fallback artifacts are retried for llm requests.
4. m21_check needles all preserved; disclaimer verbatim-unchanged;
   `DISCLOSURE_CONSENT_VERSION == 2`.
5. `m24_check.py` + `test_m24.py` offline PASS; `ruff check .`,
   `pytest`, `node --check` clean; m10–m23 regressions PASS; one live
   pass recorded in [03-milestones.md](03-milestones.md) M24.

## Explicit non-goals (M13)

In-page gap marking on the JD text
([03-milestones.md](03-milestones.md) §Deferred #12), generic non-LinkedIn
JD pages (content-script matches are LinkedIn-only, like the bookmarklet),
run history, hosting, multi-user auth, Chrome Web Store packaging,
native-messaging server auto-launch ([03-milestones.md](03-milestones.md)
§Deferred #14), conversational intake
([03-milestones.md](03-milestones.md) §Deferred #13 — the interaction model
stays this panel).

## Done criteria (met at M13 — verification record in roadmap M13)

1. Capture → analyze → plan completes from the extension against the local
   server.
2. `phase: "gaps"` produces `/api/gaps` and pauses, `phase: "plan"` resumes
   to `plan.html` with GFI links.
3. `m13_check.py` verifies the flow offline (stubbed judge/synthesis/search)
   — two-phase pause/resume, captured-JD ingestion, gaps artifact, manifest
   validity.
4. `ruff check .` and `pytest` clean.

## History (links, not copies)

- Decisions: [02-decisions.md](02-decisions.md) (M13 rows — side panel,
  two-phase pause, captured JDs, no-CORS, M13-before-M9, gap table,
  `reuse_judged`, link fix, JD viewer fix; M14 rows — non-conversational
  model, resume upload transport, extraction-cache hashing, keyring key
  entry, provider plumbing, bat launcher; M15 rows — presence-policy
  home, pre-flight refusal, rule-based mode, provenance labels; M16
  rows — OAuth connect, shared-key rejection, free-mode consent gate,
  retry policy, keyring reuse; M18 rows — state-driven panel, key-info
  validation, paste-form fallback kept, provenance-preserving table
  merge).
- Milestones: [03-milestones.md](03-milestones.md) M13 (verification record
  + learnings), M14 (self-serve setup, Built), M16 (free LLM access,
  Built), M18 (panel simplification, Designed — §M18 above).
- Deferred: [03-milestones.md](03-milestones.md) §Deferred #12 (in-page gap
  marking), #13 (conversational intake), #14 (native-messaging launcher).
- Install / load-unpacked instructions: [../extension/README.md](../extension/README.md).