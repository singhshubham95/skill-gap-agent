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
(find the `[id^="JobDetails_AboutTheJob_"]` block, click its expand button,
take `innerText` + `document.title` + `location.href`). The panel asks the
active tab via `chrome.tabs.sendMessage`; the content script answers with
`{title, url, text}`. The list lives in `chrome.storage.local`
(`capturedJds`, deduped by URL, re-capture updates text). No `tabs` /
`activeTab` permissions: the content script returns everything the panel
needs. JD text is **untrusted web content** — the panel renders it with
`textContent` only, never `innerHTML`.

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
(M8 extraction runs before the graph).

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

Server binds `127.0.0.1` only. **No CORS headers on purpose**: the extension
calls with `host_permissions` for `http://localhost:8000/*` +
`http://127.0.0.1:8000/*` (which bypass CORS entirely), while absent
`Access-Control-Allow-*` + no `OPTIONS` handler means hostile web pages can
neither read resume-derived gaps nor trigger runs (JSON `Content-Type`
forces a preflight, which fails). Trust model: any local process can reach
the server — same as M11, acceptable for a personal tool.

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

## M16 — free LLM access (Designed)

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
   one-time `code` (in-memory, 10-minute TTL) and serves a tiny
   "Connected — return to the side panel" page. Localhost callbacks on any
   port are supported; `server.py` is already bound to `127.0.0.1:8000`.
   The callback is a top-level browser navigation (no CORS involved), and
   the panel's subsequent polls behave like every other extension →
   server call under the existing security posture.
4. The panel polls `GET /api/oauth/pending?state=…` (state must match),
   then `POST /api/oauth/exchange {code, code_verifier}`. The server
   exchanges at `POST https://openrouter.ai/api/v1/auth/keys`, receives a
   **user-owned** key, and stores it in the OS keyring — the same
   `OPENROUTER_API_KEY` slot as the M14 paste form; the key transits the
   server's exchange handler only, never `chrome.storage` (extends the M14
   keyring decision). The panel shows "Connected ✓" plus a "Manage key on
   OpenRouter" link (key-hash deep link) so the user can inspect or revoke
   the key at any time.
5. Failure paths: denial or 10-minute expiry → panel message + retry;
   state mismatch or exchange failure → rejected, nothing stored.

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
  with the hint "add your own key or wait for the free quota to reset".

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
  retry policy, keyring reuse).
- Milestones: [03-milestones.md](03-milestones.md) M13 (verification record
  + learnings), M14 (self-serve setup, Built), M16 (free LLM access,
  Designed).
- Deferred: [03-milestones.md](03-milestones.md) §Deferred #12 (in-page gap
  marking), #13 (conversational intake), #14 (native-messaging launcher).
- Install / load-unpacked instructions: [../extension/README.md](../extension/README.md).