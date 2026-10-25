# Skill-Gap Agent

Transferability-aware skill-gap analysis: given your skills dump and a set of
target job descriptions, the agent builds a weighted skill graph, scores how
much your existing skills transfer to missing ones (LLM judge), checks the
uncertain verdicts with you (human-in-the-loop), and outputs a ranked plan of
learning projects grounded in what you already know — not generic advice.

Validated against a sealed hand-performed gap analysis of the same data — the
pipeline's first run was scored against it as acceptance criteria (rubric and
results: [specs/08-gap-measurer.md](specs/08-gap-measurer.md) §Validation
rubric). Ongoing quality monitoring runs the pipeline over seeded JD subsets
and records which subset produced which plan — the sweep harness
(`sweep.py`, design in
[specs/11-sweep.md](specs/11-sweep.md)).

## Quickstart

Requirements: Python 3.11+, an [OpenRouter](https://openrouter.ai/keys) API
key (default model: DeepSeek V4 Flash — a full run costs well under a cent).

### Path A — Chrome extension (recommended)

No command-line flags: the side panel handles everything.

1. **Install once:**

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\pip install -e ".[dev]"
   ```

2. **Start the local agent:** double-click
   [tools/start-server.bat](tools/start-server.bat). The console window that
   stays open *is* the server — close it to stop.

3. **Load the extension:** open `chrome://extensions`, enable **Developer
   mode**, click **Load unpacked** and select the [extension/](extension/)
   folder. Click the toolbar icon — the side panel opens.

4. **Configure in the panel:** upload your resume in **Setup** (PDF/DOCX/TXT
   — the file is kept locally in `output/uploads/`; the extracted text is
   sent over HTTPS to the AI provider you select for analysis, never to
   the extension's developer) and, under **Analyze gaps**, keep
   **Use LLM intelligence** on (default) and paste your API key there
   (stored in the OS keyring — Windows Credential Manager / macOS
   Keychain — never in the browser). LLM mode without a key refuses to
   run; toggled off, you get a clearly labeled **Rule-based** run
   (keyword matching, no LLM calls).

5. **Use it:** open a LinkedIn JD → **Capture JD** (repeat per JD — the
   list only grows; if LinkedIn truncates the description, the panel
   highlights its "…see more" button — click it yourself and capture
   again) → **Analyze gaps** → **Generate plan**. Every gap row
   and plan section states its source (`LLM` / `LLM (cached)` /
   `Rule-based`).

Full details (including troubleshooting): [extension/README.md](extension/README.md).
After pulling code changes, restart the server and reload the extension.

### Where your data lives

`output/` is the **current session** — one central location, no per-run
folders:

- `plan.md` — the ranked plan (start here)
- `plan.html` — clickable issue links, served by the local UI / extension
- `graph.json` — the full skill graph
- `judge_report.json` — audit trail of every judgment
- `oss_issues.json` — per-gap issue cache (re-runs make zero API calls)
- `profile.json` — your intake answers, implied-skill decisions, depth and
  intent (the decisions that persist across re-runs)
- `extracted_skills.json` — the resume extraction cache
- `current.json` — which resume this workspace belongs to
- `uploads/` — your resume
- `captured_jds/` — the JDs you captured
- `saved_sessions/` — named snapshots you saved from the panel

Uploading a different resume clears the artifacts derived from the previous
one (profile answers, extraction cache, judgment caches) so one resume's
depth answers can never reach another's analysis. Clearing the JD list in
the panel deletes those files here too; **delete everything** wipes the
session artifacts while keeping `logs/`, `sweeps/` and `saved_sessions/`.

Root-owned (not session state): `checkpoints.sqlite`, `logs/`, `sweeps/`.

## What v1 does — and deliberately doesn't

| Does | Doesn't (yet) |
|---|---|
| Skills JSON ingestion with implied-skill detection (you approve) | Automatic JD discovery/scraping (capture is bookmarklet/extension) |
| Resume PDF/DOCX/TXT ingestion (M8) | Chat follow-up Q&A over the graph |
| JD parsing via a curated, auditable keyword lexicon | Per-JD mention-modality classification ("such as" vs "must have") — hand-set policies for now |
| LLM transferability judge (calibrated 0–1 + rationale) | Neo4j persistence (v1 is networkx + JSON) |
| Alternative-group semantics ("cloud: AWS/Azure/GCP" = any one) | Issue-quality ranking / curated-only results (search-and-reason loop is next) |
| Human gate on ambiguous verdicts (depth + intent, persisted) | In-page gap marking on the JD text (extension renders a gap table) |
| Ranked plan with JD traceability + grounded projects | Chrome Web Store packaging / multi-user hosting |
| Conversational intake chat + evidence-backed skill validation (M9) |  |
| OSS good-first-issue sourcing per top gap (M10 thin slice, unauthenticated) + `plan.html` |  |

Full trade-off list with restore triggers: [specs/03-milestones.md](specs/03-milestones.md) §Deferred.

**Roadmap (M7–M16 built — M9 built 2026-10-12):** LangGraph
orchestration with resumable human-in-the-loop steps, resume PDF/DOCX
ingestion, GFI issue sourcing, minimal local UI
(`python -m skill_gap_agent.server`), the JD-subset sweep evaluation
harness (`python -m skill_gap_agent.sweep`), and the Chrome extension with
self-serve setup (JD capture → gaps → plan in a side panel; resume upload,
keyring key entry, [tools/start-server.bat](tools/start-server.bat)
launcher) are built. Conversational intake returned **inside
the panel** at Analyze gaps (M9) — upload stays rule-only; extraction, the
profile chat and skill validation run with the captured-JD context, and
every artifact is tied to the uploaded resume via a SHA-keyed session
store ([specs/13-intake.md](specs/13-intake.md)).
Design detail in
[specs/13-intake.md](specs/13-intake.md),
[specs/11-sweep.md](specs/11-sweep.md) and
[specs/12-extension.md](specs/12-extension.md); build order in
[specs/03-milestones.md](specs/03-milestones.md).

## Privacy & store readiness

Data handling is described in [docs/privacy-policy.md](docs/privacy-policy.md)
(what leaves the machine: the AI provider you choose + GitHub search terms;
the developer receives nothing). Chrome Web Store submission material —
permission justifications, declarations, listing copy — is maintained in
[CHROMEWEBSTORE.md](CHROMEWEBSTORE.md); bundled dependency licenses in
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

## For contributors

The specs are the onboarding path — they document not just the design but the
*reasoning* behind every decision, including revisions made during building:

1. [specs/01-system-overview.md](specs/01-system-overview.md) — stage map, stage↔code table, data flow, repo map, component router (start here)
2. [specs/02-decisions.md](specs/02-decisions.md) — locked decisions, append-only, with rationale (including decisions that were *revised* and why)
3. [specs/03-milestones.md](specs/03-milestones.md) — roadmap: build order + learnings + deferred trade-offs + open questions
4. S1–S7 stage files ([specs/04-reader.md](specs/04-reader.md) … [specs/10-flow-runner.md](specs/10-flow-runner.md)) — per-stage mechanics + status
5. Non-stage component files ([specs/11-sweep.md](specs/11-sweep.md), [specs/12-extension.md](specs/12-extension.md), [specs/13-intake.md](specs/13-intake.md)) — sweep harness, extension shell, intake + validation

Conventions: specs are numbered by reading order and are **living
target-state documents** — they describe the full system being built, with
every component marked Built or Designed (never version-split into
`specs/v2/`; milestone numbers stay linear). `02-decisions.md` is append-only
(mark superseded, never rewrite); the graph schema in
[01-system-overview.md](specs/01-system-overview.md) is deliberately Neo4j-shaped so
the store can migrate without redesign. The full spec-evolution rules and
code conventions live in
[.github/copilot-instructions.md](.github/copilot-instructions.md) — read it
before changing code or specs.

## Specs

All specifications live in [`specs/`](specs/). Start with the system overview,
then dive as needed:

| File | Contents |
|---|---|
| [specs/01-system-overview.md](specs/01-system-overview.md) | **Start here** — stage map, stage↔code table, data flow, repo map, component router |
| [specs/02-decisions.md](specs/02-decisions.md) | Locked technology and scope decisions, with rationale |
| [specs/03-milestones.md](specs/03-milestones.md) | Roadmap: build order + learnings + deferred trade-offs + open questions |
| [specs/04-reader.md](specs/04-reader.md) … [specs/10-flow-runner.md](specs/10-flow-runner.md) | Per-stage mechanics (S1–S7); skill-graph schema in [06-skill-map.md](specs/06-skill-map.md) |
| [specs/11-sweep.md](specs/11-sweep.md) | JD-subset sweep evaluation harness (M12) |
| [specs/12-extension.md](specs/12-extension.md) | Chrome extension + self-serve setup (M13 + M14) |
| [specs/13-intake.md](specs/13-intake.md) | Intake + skill validation (M9, Built 2026-10-12 — in-panel chat + session store) |