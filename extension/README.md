# Skill-Gap Agent — Chrome extension (M13 + M14)

The end goal from [../specs/09-practice-planner.md](../specs/09-practice-planner.md)
§End goal: open a JD in the browser, capture it, and get the skill gaps +
a hands-on plan (with live good-first-issues) in a side panel. Design:
[../specs/12-extension.md](../specs/12-extension.md).

## What it does

0. **Setup** — upload your resume (PDF/DOCX/TXT) and paste the LLM API key
   right in the panel. No command-line flags, no env vars: the key goes to
   the local agent, which keeps it in the OS keyring.
1. **Capture JD** — reads the LinkedIn job description on the active tab
   (same extraction as [../tools/linkedin_jd_bookmarklet.js](../tools/linkedin_jd_bookmarklet.js))
   and appends it to a list. Navigate to the next JD and capture again —
   the side panel stays open and the list only grows.
2. **Analyze gaps** — sends the collected JDs to the local agent
   (`server.py`) and shows the ranked gap table. First run takes minutes
   (LLM judge); re-analysis reuses cached judgments.
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
   - **Setup › Your resume** — upload a PDF/DOCX/TXT. It stays on your
     machine (`output/uploads/`); the panel shows the extracted skill
     count. First upload of a new resume can take minutes (LLM
     extraction); the same file is instant afterwards.
   - **Settings › LLM key** — paste the API key and click **Save key**.
     "Remember on this machine" stores it in the OS credential vault
     (Windows Credential Manager / macOS Keychain); uncheck it to keep the
     key for this server session only. The key is never stored in the
     browser.

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
  lost anyway, **Reopen plan** brings it straight back — `plan.html` stays
  on disk, no re-run needed.
- Capture is LinkedIn-only for now (like the bookmarklet); generic JD pages
  are recorded future work.
