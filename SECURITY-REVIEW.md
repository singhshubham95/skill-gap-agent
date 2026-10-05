# Security & Legal Review — Public Release Readiness

**Date:** 2026-10-05 · **Scope:** full repository (Chrome extension, local agent
server, pipeline) · **Purpose:** assess data security and legal/compliance
implications of publishing the extension publicly (Chrome Web Store or another
central store).

> This document is a technical risk analysis, **not legal advice**. Have a
> lawyer review the LinkedIn ToS position and the privacy policy before release.

## Verdict

**No-Go for store release until the four blockers in §5 are fixed.** Code
quality is high — no XSS, no leaked secrets, minimal extension permissions —
but an unauthenticated local API and an inaccurate data-handling disclosure are
release blockers, and Chrome Web Store submission requires a privacy policy and
packaging work that does not exist yet.

## 1. Data flows (verified in code)

| Data | Leaves the machine? | Destination | Evidence |
|------|---------------------|-------------|----------|
| Resume (full PII) | Yes | LLM provider (OpenRouter default / Z.ai GLM / OpenAI), over HTTPS, up to 60 000 chars in the prompt | `src/skill_gap_agent/resume.py:138-149`, `src/skill_gap_agent/llm.py` |
| Job descriptions (LinkedIn page text) | Yes | Same LLM providers, during analysis | `src/skill_gap_agent/server.py`, `src/skill_gap_agent/judge.py` |
| Skill-gap search terms (derived from resume/JDs) | Yes | GitHub Search API | `src/skill_gap_agent/oss.py` |
| LLM API key | Yes (with each call) | Selected LLM provider; stored only in the OS keyring | `src/skill_gap_agent/secrets.py`, `extension/sidepanel.js` |
| Anything to the developer | **No** — no telemetry, no developer backend; server binds `127.0.0.1` only | — | `src/skill_gap_agent/server.py:630` |

Captured JDs also persist in `chrome.storage.local`; resumes land on disk under
`output/uploads/`. `data/` and `output/` are gitignored and untracked.

## 2. Security findings

### S1 — Local agent API is fully unauthenticated — MEDIUM (8/10)

**Files:** `src/skill_gap_agent/server.py:34-37, 406-608, 630`

State-changing endpoints (`POST /api/run`, `POST /api/key`, `POST /api/resume`)
and data endpoints (`GET /api/gaps`, `GET /plan.html`, `GET /jds/*`,
`GET /api/status`) accept any caller: no auth, no `Origin`/`Sec-Fetch-Site`
check, no CSRF token. Absent CORS headers block *reading* responses cross-origin
but not *sending* requests: a hostile web page can fire a `text/plain` POST with
a JSON body (no preflight) that the server executes. Impact: overwrite the
user's stored LLM key, spend their API credits on runs, write attacker bytes
into `output/uploads/` / `output/captured_jds/`, ingest arbitrary local files
via the `skills_path` body option (`server.py:177`), and let any local
process/OS account read resume-derived skills and plans. Chrome's Private
Network Access rules reduce the public-web vector; local pages and processes are
unaffected.

**Fix:** reject state-changing requests whose `Origin`/`Sec-Fetch-Site` is not
`chrome-extension://<id>`, the server's own origin, or absent (CLI); require a
per-session bearer token (minted at server start, given to the extension) on
every API call, including data-returning GETs.

### S2 — Inaccurate disclosure: "stays on your machine" — MEDIUM (10/10)

**Files:** `extension/sidepanel.html:15-18`, `extension/README.md`,
`src/skill_gap_agent/server.py:550-554`, `src/skill_gap_agent/resume.py:138-149`

The setup UI and README state the resume stays on the machine, while every
upload is immediately sent in full to the selected cloud LLM provider for skill
extraction; JD text and the skill list transit the same providers during
analysis. Transport is HTTPS and key handling is correct (OS keyring only), but
the disclosure is wrong — a privacy bug and a Chrome Web Store deceptive-copy /
data-use-disclosure risk in one.

**Fix:** replace the copy with an accurate disclosure, obtain explicit consent
before the first upload/analysis, and expose the existing regex-only extraction
path (`resume.extract_skills_regex`) as a no-cloud opt-out.

### Clean areas (verified)

No exploitable issues found in: XSS rendering (untrusted JD/gap data rendered
via `textContent`/`createElement` only; plan HTML escaped with `html.escape` in
a sandboxed iframe), extension message passing, path traversal (upload/JD
filenames basename-whitelisted), hardcoded secrets, remotely hosted code
(MV3-clean), or extension permissions (`sidePanel`, `storage`, localhost hosts,
LinkedIn-only content script — minimal for the feature set). `data/`/`output/`
correctly gitignored and untracked.

## 3. Legal & compliance findings

Chrome Web Store policy requirements were verified against the current
[Limited Use policy](https://developer.chrome.com/docs/webstore/program-policies/limited-use).

| # | Severity | Finding |
|---|----------|---------|
| L1 | 🔴 Blocker | **Privacy policy + declarations missing.** The extension handles personal information (resume) and web browsing activity (JD capture). A hosted privacy policy URL, the Chrome Web Store **Limited Use compliance statement**, and Privacy Practices declarations (data types: personal info, web page content, authentication info; purposes; third-party transfers to OpenRouter/Z.ai/OpenAI/GitHub) are mandatory before publishing. JD capture is permitted only as a prominently described user-facing feature — keep capture strictly user-initiated. |
| L2 | 🔴 Blocker | **Store packaging gaps.** No extension icons (128×128 mandatory); permission justifications needed for the LinkedIn content script and localhost hosts; the companion Python server requirement must be prominently documented for reviewers or the item risks rejection as non-functional. |
| L3 | 🟠 High | **LinkedIn Terms of Service exposure.** `extension/content.js` auto-clicks LinkedIn's expand button and copies JD DOM — LinkedIn's User Agreement prohibits automated access/scraping and copying data from the Services. Realistic exposure: store takedown (most likely), cease-and-desist/breach-of-contract claim; CFAA risk is low post-*Van Buren* / *hiQ v. LinkedIn*. Mitigations: keep capture single-page and user-initiated (never add batch capture), remove the synthetic `btn.click()` in favor of asking the user to expand the text themselves, and add "Not affiliated with, endorsed by, or sponsored by LinkedIn Corporation" to the listing (nominative trademark use only, no LinkedIn logos). |
| L4 | 🟠 High | **Plaintext transmission to configurable server.** `serverBase` (extension Settings) can point at any `http://…` host, sending resume, JDs, and the API key unencrypted to an arbitrary machine. Restrict non-loopback servers to `https://`, or drop configurability in the store build. (Same root as S1's exfiltration risk.) |
| L5 | 🟡 Medium | **LLM destination disclosure & PII minimization.** Name the actual destinations in the privacy policy — OpenRouter (aggregator: data also reaches the underlying model provider), DeepSeek (China), Z.ai/BigModel (China), OpenAI — and state that providers may retain/ train on inputs unless the user opts out. Cross-border flows to China matter for EU users (GDPR Chapter V disclosure) and PIPL on the receiving end. Strip names/contact details before the LLM skill-extraction call. Also disclose that GitHub receives skill-gap search terms. |
| L6 | 🟡 Medium | **AI transparency & scope.** Mark plans as AI-generated (EU AI Act Art. 50 spirit); the tool is not Annex III high-risk only because it serves job seekers' self-improvement — never market it to recruiters for ranking candidates. Avoid outcome guarantees in listing copy ("land interviews fast"). |
| L7 | ⚪ Low | **Housekeeping.** MIT license is store-compatible (keep the notice); add a third-party notices file if the server is bundled into an installer; trademark-search "Skill-Gap Agent"; GitHub API usage (cached, optional token) is compliant. |

**Privacy-law posture today:** with no developer-operated infrastructure the
developer collects nothing and is not a GDPR controller — a good position to
preserve. Adding analytics, crash reporting, accounts, or a hosted backend
changes that instantly (lawful basis, DSR process, EU representative, CCPA
flows). Children: state the extension is not directed at under-16s.

## 4. Distribution notes

- Chrome blocks consumer off-store `.crx` installs; the Web Store (or enterprise
  policy) is effectively the only channel. Submission needs a developer account
  (fee + ID verification), privacy policy URL, declarations, icons, and
  permission justifications.
- A bundled Windows server needs code signing (SmartScreen); macOS needs
  notarization.

## 5. Release blockers (fix before publishing)

1. Hosted privacy policy + Limited Use statement + Privacy Practices
   declarations covering resume, JD capture, and LLM/GitHub transfers. (L1, S2)
2. Honest in-product disclosure, explicit consent before first upload/analysis,
   and a no-cloud extraction opt-out. (S2)
3. Local API auth hardening: `Origin`/`Sec-Fetch-Site` checks + per-session
   bearer token on all endpoints. (S1)
4. Store packaging: icons, permission justifications, companion-server docs for
   reviewers; HTTPS-only custom `serverBase`. (L2, L4)

Strongly recommended alongside: remove the synthetic click on LinkedIn's UI and
add the non-affiliation disclaimer (L3); disclose DeepSeek/Z.ai flows and
provider retention/training caveats (L5); AI-generated-content notice (L6).

## 6. Residual risk after the above

Acceptable: remaining exposure is mainly LinkedIn contract/takedown risk
(inherent to the product's premise — manageable, not eliminable) and
third-party LLM data handling (disclosed, user-chosen).
