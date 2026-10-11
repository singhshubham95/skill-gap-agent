# Skill-Gap Agent — Chrome extension (M13 + M14 + M18)

The end goal from [../specs/09-practice-planner.md](../specs/09-practice-planner.md)
§End goal: open a JD in the browser, capture it, and get the skill gaps +
a hands-on plan (with live good-first-issues) in a side panel. Design:
[../specs/12-extension.md](../specs/12-extension.md).

## What it does

0. **Setup** — upload your resume (PDF/DOCX/TXT). For LLM analysis the
   panel checks whether a key is saved and shows one of two states: with a
   key, pick **Free model**, **Paid model** or **Rule-based**; without one,
   **Create free LLM key** (one click, no key to paste) or run
   rule-based. No command-line flags, no env vars: keys go to the local
   agent, which keeps them in the OS keyring. **I already have a key**
   opens a paste form for other providers (GLM, OpenAI, OpenRouter).
1. **Capture JD** — reads the LinkedIn job description on the active tab
   (same extraction as [../tools/linkedin_jd_bookmarklet.js](../tools/linkedin_jd_bookmarklet.js))
   and appends it to a list. Navigate to the next JD and capture again —
   the side panel stays open and the list only grows.
2. **Analyze gaps** — sends the collected JDs to the local agent
   (`server.py`) and shows the ranked gap table. First run takes minutes
   (LLM judge); re-analysis reuses cached judgments. Every row states its
   source (`LLM` / `LLM (cached)` / `Rule-based`), and if any LLM call
   fails mid-run a banner says exactly which parts fell back — results
   are never silently non-LLM.
3. **Generate plan** — resumes the paused run: grounded projects +
   good-first-issues, rendered in the panel.

## Setup (once)

1. **Install + start the local agent** (the extension is a thin client;
   the pipeline runs on your machine): double-click
   [../tools/start-server.bat](../tools/start-server.bat), or run:

   ```powershell
   .\.venv\Scripts\python -m skill_gap_agent.server
   ```

   The console window that stays open *is* the server — close it to stop.
   Restart it after pulling code changes (a stale process otherwise keeps
   answering on port 8000). The `--skills` / `--port` flags still work but
   are optional — the panel handles the resume.

2. **Load the extension:**
   - open `chrome://extensions`, enable **Developer mode** (top right)
   - click **Load unpacked** and select this `extension/` folder
   - (if it was already loaded) click the reload icon after pulling changes

3. **Open the panel** (toolbar icon) and configure it:
   - **Setup › Your resume** — upload a PDF/DOCX/TXT. The file is kept
     locally under `output/uploads/`; the extracted text is sent over
     HTTPS to the AI provider you select for skill extraction (see the
     panel's data disclosure, which must be confirmed before the first
     upload) — it is never sent to the extension's developer. The panel
     shows the extracted skill count. First upload of a new resume can
     take minutes (LLM extraction); the same file is instant afterwards.
   - **Analyze gaps › key state** — the panel verifies a saved key with a
     free key-info call and shows `Key ✓ verified` (or "couldn't verify —
     runs will retry"; validation never blocks a run). **Create free LLM
     key** opens an OpenRouter login and stores the minted key in the OS
     credential vault (Windows Credential Manager / macOS Keychain).
     **I already have a key** reveals the paste form ("Remember on this
     machine" = keyring; uncheck for this server session only). The key is
     never stored in the browser. LLM modes with no key are refused up
     front — the panel will not quietly run without the LLM. Picking
     **Free model** reveals the consent block (free providers may log
     inputs); runs without consent are refused server-side too.

## First capture

Open a LinkedIn job description (`linkedin.com/jobs/...`) and click
**Capture JD**. (Tabs opened *before* the extension was installed need a
one-time reload — the content script is injected on page load.)

## Notes

- The panel calls `http://127.0.0.1:8000` (configurable in the panel's
  Settings). Manifest `host_permissions` cover `localhost`/`127.0.0.1` on
  any port — no CORS headers are involved (decision in
  [../specs/02-decisions.md](../specs/02-decisions.md)).
- JD text is untrusted web content — the panel renders it with `textContent`
  only; the plan renders in a sandboxed iframe served by the local agent.
  Every link in the plan opens in a **new browser tab**, so a mis-click
  cannot navigate the panel away from the plan; if the plan view ever gets
  lost anyway, a **Reopen plan** button appears automatically and brings
  it straight back — `plan.html` stays on disk, no re-run needed.
- Capture is LinkedIn-only for now (like the bookmarklet); generic JD pages
  are recorded future work.
