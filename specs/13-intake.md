# C3 — Conversational Intake + Skill Validation

How the agent gathers evidence and how it verifies claimed depth before
ranking. Two coupled concerns: an in-panel chat that assembles and confirms
the profile at analyze time (with the captured-JD context), and a
validation protocol that replaces
self-report with elicited, evidence-backed proficiency.

**Status: ✅ Built — 2026-10-12 (M9: the conversation returned, inside the
panel).** Supersedes the 2026-10-04 "no conversational flow"
deferral (row struck in [02-decisions.md](02-decisions.md)): the chat lives
**inside the extension side panel** and runs at **Analyze gaps** (placement
revision 2026-10-12: upload stays rule-only; extraction → chat → profile
saved happen at analyze, with the captured-JD context), so the 2026-10-04
constraint "any restored version must live inside the panel flow" is
satisfied and no second interaction model appears. The restore trigger's evidence clause (§Deferred #13
brainstorm) is bypassed by explicit user decision 2026-10-12, logged in the
decision row. Scope: **full C3 in one implementation pass** — intake chat +
skill validation + the depth-aware judge. Built as `sessions.py` (session
store), `intake.py` (conversation state machine), `validate.py`
(calibration protocol), with depth-aware judging in `judge.py` and
session routing through `resume.py` / `cli.py` / `server.py` / `m5_plan.py`
/ `m4_gate.py`. Design originally folded from `2-architecture.md` §§11–12.

## In-panel conversational intake (at Analyze gaps)

**Placement (user decision 2026-10-12, revised same day):** the
conversation runs at **Analyze gaps**, not at upload. The three-step flow:

1. **Upload resume** — file saved + *rule-based* processing only (text
   extraction, scanned-PDF guard; **no LLM call** — nothing leaves the
   machine at upload).
2. **Capture JDs** — unchanged (M13).
3. **Analyze gaps** — triggers LLM skill extraction, implied-skill
   detection, and this intake chat (pause → chat → profile saved) **with
   the captured-JD set in context**; then the pipeline runs as today
   (judge → rank → gaps pause → Generate plan). Two pause points in one
   run — intake, then the existing gaps preview — over the same
   pause/resume shape as the M13 two-phase run; question/answer turns are
   `/api/intake/*` request/response (pre-graph, so no LangGraph
   `interrupt()` is needed here) and state survives panel close via the
   session store.

The chat is a region of the same side panel (M18 surface) — one surface,
not a second interaction model. This also keeps the M14 upload disclosure
precise: at upload nothing is sent anywhere; the "sent for skill
extraction and analysis" step happens at analyze.

Turns, in order:

1. **Extracted phrases** — review what extraction found, **focus first,
   background automatic** (design revision 2026-10-17, replacing the
   original "keep all, or edit the list" wording — see §Phrase review
   below). Replaces the y/n/a flow of `review_extracted`; retires
   `extracted_approvals.json`.
2. **Implied skills** — proposals with evidence, keep/drop each. Replaces
   `propose_implied`'s y/n/a flow; retires `implied_skills.json`.
3. **Depth + intent** — the gate's self-assessment questions (depth 1–5 +
   count / declared-gap), asked for the profile's ranking-relevant skills.
   Replaces `gate_overrides.json` prompting; the answers become the
   profile's depth facts, consumed by the depth-aware judge (§ below).
4. **Validation questions** — the calibration protocol below (this pass,
   per the 2026-10-12 scope decision).

**Triage is JD-aware (the placement revision's payoff).** Because the chat
runs at analyze time, validation triage is C3's original: ranking-relevant
skills only — high JD `weight`, top-transfer *sources*, gate-flagged — cap
~10–15 questions. Anything unvalidated (skipped questions, obscure skills)
falls to the gate-shrink default (§Depth-aware judge + gate policy); the
CLI's interactive gate still covers such skills there.

Skippable end-to-end ("just use my resume as-is") → resume-claim fallback:
phrases auto-accepted, implied auto-accepted, depth unknown (gate-shrink
default applies). The chat never re-asks a persisted answer; a same-resume
re-upload resumes the session and only new questions are asked.

**Freshness is item-level, never run-level** (amended 2026-10-12, after the
first live extension run — learnings in roadmap M9): a `completed` profile
short-circuits the chat **only when the current run has nothing new to
ask**. A changed extraction (e.g. a regex fallback later upgraded to LLM),
newly captured JDs (new triage candidates), or any unanswered item
re-opens the conversation for exactly those items. The blanket
"completed → skip the chat" rule silently hid new questions — it is gone;
completion is derived from the profile's items, never trusted as a
run-level gate. The skip ("use as-is") choice is **sticky**: a skipped
session is never asked anything again; new extraction items are
auto-accepted under the same skip (depth stays unknown → gate-shrink
default). Whenever the chat is skipped, `/api/status` carries
`intake_note` (the reason) and the panel shows it — a silently skipped
conversation is never acceptable.

**Validation runs are isolated from real sessions** (operational rule,
same date): scripted/interactive validation runs must point the session
store at a scratch directory via the `SKILL_GAP_SESSIONS_DIR` env
override (default stays `output/sessions`). A validation run sharing the
real store can complete a real user's profile with scripted answers — the
exact incident this rule prevents (roadmap M9 learnings).

The existing capture paths are reused, not rewritten: the bookmarklet /
extension capture JDs ([12-extension.md](12-extension.md)), and
`resume_to_skills_json()` does resume extraction
([04-reader.md](04-reader.md) S1) — with its `ask_fn` seam now fed by the
chat instead of stdin.

## Phrase review — focus first, background automatic (revised 2026-10-17)

Origin: first live M9 run (2026-10-13) — the phrase turn listed all 80
extracted phrases in one question and accepted bare `none`/"`n`"/"`no`"
as "drop everything". The user answered "none" meaning "drop nothing" and
the run silently reduced the graph to 0 skills (post-mortem learnings in
roadmap M9). Two defects share one cause: a high-stakes parse on an
ambiguous one-word input, presented with more information than a person
can hold in one pass. The redesign fixes both.

**A. The list is triaged, not dumped.** The turn shows only the
**focus phrases** — the extracted phrases that can affect the gap table:

- phrases whose canonical term is a **target skill** of the captured JDs,
  or a **pruned candidate source** for one (`judge.prune_candidates` — the
  same keyword-overlap + lexicon-hints filter the judge itself uses), or
  an **alternative-group member** of some target
  (`requirements.group_for` — alt-bridged rows read these);
- everything else is **background**: structurally incapable of changing
  any gap row in this run (it enters the graph but no target draws a
  transfer from it). Background phrases are **kept automatically** — the
  safe default: keeping a skill can only add transfer evidence, never
  create a gap — and the turn states how many were auto-kept.
  `show background` lists them (grouped, numbered, same grammar) for the
  user who wants to review everything. Exception: when **no** focus phrase
  is pending (e.g. a re-run whose extraction only added background
  items), everything pending is listed instead — new items are never
  hidden when there is no focus list to show them against (same spirit as
  §Freshness: nothing new is ever silently absorbed).

**B. The focus list is grouped**, under the extraction's own conceptual
categories (the skills-JSON hierarchy's top-level keys — e.g. "Machine
Learning", "Data Engineering"): the user scans ~5 group headers, not 80
flat lines. Numbering stays global across groups so the answer grammar's
indices are unambiguous.

**C. The answer grammar is closed — no bare destructive word exists.**
Exactly these forms, everything else (including `none`, `n`, `no`, `y`,
`yes`, prose) is rejected with a hint restating them:

| Answer | Meaning |
|---|---|
| `keep all` (or `all`) | include every listed phrase (drop none) |
| `drop all` | include none of the listed phrases (the only whole-set destructive form — must be typed in full) |
| `drop: 3,5` | drop just those numbers, keep the rest |
| `keep: 3,5` | keep just those numbers, drop the rest |
| `add: <skill>` | add a missing skill |
| `show background` | list the auto-kept background phrases too |

The prompt states the three intents in the user's words — **include all**
(keep all), **include some** (`drop:`/`keep:` with numbers), **include
none** (`drop all`) — so the destructive reading is never a guess.
`drop all`/`keep all` apply to the **listed** set only; auto-kept
background phrases are never dropped without `show background` first.

**D. The panel gives immediate feedback (client contract).** On Send the
input and button disable at once and a pending hint appears ("sending…")
— a silent multi-second gap with a live blue button is indistinguishable
from a missed click and invites the double-Enter that produced stale-turn
400s in the first run. The Send path is single-flight (a second Enter
while a request is in flight is ignored); answers that the server rejects
re-render inline next to the input, not only in the status line, and
re-enable the input.

**Parser hardening (same root cause, other turns).** Depth answers must
be a bare `1`–`5` (optionally followed by `n`); checklist answers must be
per-concept `y`/`n` tokens. Pasted prose is rejected with a format hint —
a regex scraping the first digit or letter out of a paragraph silently
grades the wrong thing, which is worse than a rejected answer.

## Skill validation

Evidence-backed proficiency instead of trusting resume claims. Resumes
inflate; self-ratings inflate more; the agent *elicits* depth through
calibration questions. **Framing: calibration, not a test** — the tool
exists to build the user's own learning plan, so no anti-cheat is needed,
only honest framing.

- **Triage (mandatory).** Quizzing every skill is an interrogation. Only
  ranking-relevant skills are validated: high JD `weight`, skills that are
  top-transfer *sources* (their depth drives the confidence
  multiplication), gate-flagged skills. Cap ~10–15 questions total;
  explicitly skippable ("just use my resume as-is" → resume-claim
  fallback).
- **Tiered protocol per triaged skill** (adaptive stop; transport = the
  in-panel chat turns above — the earlier LangGraph
  `generate_question → interrupt → grade → route` subgraph is history from
  the pre-2026-10-04 design):
  1. **Concept checklist** — yes/no on ~4–6 sub-concepts. Cheapest to
     generate reliably and fastest to answer; per-concept granularity
     makes the *pattern* of yesses informative even if individual
     answers inflate.
  2. **One applied question** on a concept the user claimed — "walk me
     through how you'd deduplicate near-identical customer records in
     SQL" — graded by one LLM call against a hidden rubric. Applied
     over trivia: tests capability, and the user's own answer is stored
     as evidence.
  3. **Optional follow-up probe** — only if tier 2 is strong.
  Route: strong → stop or escalate once; vague → downshift and stop.
  Max 2–3 turns per skill.
- **Question authoring & leakage control.** Questions + hidden rubric
  are co-generated in one LLM call (rubric never shown). A mechanical
  string-overlap check between question text and rubric technique names
  catches answer leakage (same spirit as the judge's keyword pruner).
  Authoring is offline and cached, so the full question set is
  reviewable before any user sees it; obscure skills degrade gracefully
  to the self-report tier.
- **Persistence & consumers.** Grades map to the gate's 1–5 depth scale
  and persist in the **session profile** (`profile.json` in the input's
  session store, §Session store — replaces the global `proficiency.json` /
  `gate_overrides.json` pattern); the question *content* cache stays keyed
  by skill (shareable), answers are per-session. Consumers:
  (a) the **depth-aware judge** (§Depth-aware judge + gate policy) — its
  transfer scores reflect the elicited depth ("user has SQL at working
  depth, not expert"); (b) the gate **shrinks to unvalidated skills only**
  (an explicit, intended outcome, not gate redundancy) and applies no depth
  multiplier where depth is known — never count depth twice.
- **LLM touchpoints & degradation.** Question authoring and grading join
  the S2 presence policy: they are added to the touchpoint list and the
  provenance vocabulary in
  [05-ai-caller.md](05-ai-caller.md). In rule-based mode (M15) validation
  degrades to the self-report tier — no questions authored, depth
  self-reported in the chat — and the degradation is labeled loudly.
- **Semantics of a "no".** A failed concept lowers the *skill's* depth
  factor (nudge, never hard-reject — a soft signal modulates
  confidence, it does not remove a skill from the profile). Concept-level
  micro-gaps ("learn window functions" as a plan item) are a recorded
  future idea, not v2 scope.

## Depth-aware judge + gate policy (no double-count rule)

The judge prompt gains depth context ("GCP at working depth 3/5"), so its
transfer score reflects depth at the source. Two rules keep this honest:

1. **No double-count.** Where depth is known, the gate applies **no** depth
   multiplier — the score already reflects it. The gate shrinks to
   unvalidated skills (CLI: interactive questions as today; extension:
   depth-naive score with no multiplication — the documented default) and
   to intent (count vs. declared-gap) where not yet answered.
2. **Cache honesty (M14 sidecar pattern generalized).** A judge score is a
   pure function of (target, skills, depth profile) — the last term is
   new. Judge-cache entries and `TRANSFERS_TO` edges are stamped with the
   **depth-profile hash** of the session; reuse (`reuse_judged`,
   `judge_report` replay) happens only on stamp match; changed depth
   re-judges the affected targets. Without this, re-analysis silently
   serves scores computed under stale depth answers (mixed-profile graphs).

Consumers affected when built: `cli.py` `reuse_judged`, the judge report
format, `graph.py` edge props ([06-skill-map.md](06-skill-map.md)). The M12
sweep runs with an **empty** depth profile (see below), so its cache key is
constant and its behavior is unchanged.

## Session store — all artifacts tied to the input (user decision 2026-10-12)

Every data artifact of a run belongs to the session of the skills source it
came from, keyed by **SHA-256 of that source file** (uploaded resume or
skills JSON) — the M14 extraction sidecar generalized to the whole store:

```
output/sessions/<sha256>/
├── extracted_skills.json      # extraction artifact (M14 rules, in-session)
├── profile.json               # phrase review + implied decisions + depth/intent
│                              #   + proficiency grades (the chat's product)
├── captured_jds/              # this session's captured JDs
├── graph.json, judge_report.json, gaps.json
└── plan.md, plan.html, oss_issues.json
```

- **Same input re-uploaded → session resumes** (extraction cache honored
  via the existing SHA sidecar; stamped judge caches honored per the rule
  above; the chat only asks new questions). **Different input → fresh
  session.** Cross-profile misapplication is structurally impossible:
  one user's CLI-era answers can no longer leak into another profile.
- **CLI runs follow the same keying** (user decision 2026-10-12):
  `m5_plan.py` / `cli.py` write into the session store of their input
  file's SHA. The seams already exist — `approvals_path`, `overrides_path`,
  `artifact_path` parameters are simply routed to session paths.
- **Retired global files:** `output/extracted_approvals.json`,
  `output/implied_skills.json`, `output/gate_overrides.json`, and the
  global `output/extracted_skills.json` (+ sidecar) are **no longer created
  or read** by any flow. Migration = delete them. Their replacement is
  `profile.json` per session.

## What this pass does not change

- **Sweep harness (M12, [11-sweep.md](11-sweep.md)).** Stays
  non-conversational and depth-naive; it runs with an empty depth profile,
  so judge-cache keys are constant and `m12_check.py` passes unchanged
  (its "each target judged once, then reused" assertion is unaffected).
  Modifying the sweep to match the extension's conversational flow is
  deferred (user decision 2026-10-12).
- **Vocabulary bridge (`vocab_bridge.py`).** Stays unwired; the open item
  already recorded in [03-milestones.md](03-milestones.md) §Open stands,
  deferred out of this pass (user decision 2026-10-12).
- **M17 golden-set judge evaluation ([14-observability.md](14-observability.md)).**
  Not built yet; when it is, golden-set fixtures gain a depth-profile field
  (expected scores depend on depth), with depth-variant cases optional.

## Surface changes (landed with the code — mirror rule)

- [12-extension.md](12-extension.md): the run contract gained the intake
  pause (analyze pauses at intake, then at gaps); `POST /api/resume` is
  rule-only (M14's immediate extraction moved to analyze); the panel (M18
  surface) gained the chat region (`#intake`, `/api/intake/*`); the status
  payload gained `intake_note` (why the chat was skipped, when it is) and
  the panel shows it.
- [05-ai-caller.md](05-ai-caller.md): touchpoint list + provenance
  vocabulary gained question authoring / grading; rule-based degradation
  maps to the self-report tier.
- [12-extension.md](12-extension.md) §Data disclosure (M21) +
  `docs/privacy-policy.md`: the conversational data flow (calibration
  questions + the user's answers sent to the provider for grading) joined
  both disclosure lists.
- [03-milestones.md](03-milestones.md): M9 status flipped + verification
  record; §Deferred #13 entry notes the bypassed trigger.

## Done criteria (met at M9 — verification record in roadmap M9)

Full pass = intake chat + skill validation + depth-aware judge + session
store + legacy-file retirement. Shape follows the repo's verification
convention (offline check + `ruff check .` + `pytest` clean + one
interactive validation recorded in `03-milestones.md`). All met:

1. Upload (rule-only — no LLM call) → capture → Analyze (extraction +
   chat + validation with JD context) → gaps → plan works in the panel,
   including the skip ("use my resume as-is") path and panel-close/reopen
   persistence.
2. The retired files (`extracted_approvals.json`, `implied_skills.json`,
   `gate_overrides.json`, global `extracted_skills.json`) are no longer
   created or read by any flow — all state lives under
   `output/sessions/<sha>/`; same-input re-upload resumes the session,
   different input starts fresh.
3. Depth-aware judge: scores reflect elicited depth; edge/cache stamps
   enforce the depth-profile hash (changed depth re-judges affected
   targets — no mixed-profile graphs); the gate applies no depth
   multiplier where depth is known (verified: no double-count).
4. Sweep unaffected: `m12_check.py` passes unchanged.
5. The mirror-rule updates land with the code: `05-ai-caller.md`
   touchpoints + provenance, M21 disclosure lists + privacy policy.

## History (links, not copies)

- Decisions: [02-decisions.md](02-decisions.md) — M9-restore rows
  (2026-10-12) superseding the M14-design row (2026-10-04); the post-M6
  v2-direction row (origin of this design).
- Milestones: [03-milestones.md](03-milestones.md) M9 (status flips at
  build), §Deferred #13 (evidence trigger bypassed by user decision
  2026-10-12).
- Related: [04-reader.md](04-reader.md) S1 (extraction + ask_fn seam),
  [08-gap-measurer.md](08-gap-measurer.md) S5 (gate depth scale this
  feeds), [05-ai-caller.md](05-ai-caller.md) S2 (touchpoints, provenance),
  [12-extension.md](12-extension.md) (panel surface, M14 upload, M21
  disclosure), [11-sweep.md](11-sweep.md) (depth-naive sweep invariant).