# S6 — Practice Planner

How to close the gap. Consumes S5 `Gap` objects, writes `Project` nodes
+ `CLOSES_GAP` edges, renders the plan.

**Status: Built** for standalone projects (M5); **Designed** for OSS
issues (M10 — end goal below).

## End goal — Chrome extension (locked 2026-09-27, folded from `8-gfi-pivot.md`)

User opens one JD in the browser; the extension reads the local resume +
metadata and returns (1) skill gap + magnitude, (2) hands-on plan to close
it, prioritizing **live `good-first-issue` / `help-wanted` issues** on
open-source repos. Personal-first order: useful for the author before any
market sale. Low-quality GFI output in iteration one is explicitly
acceptable — end-to-end first, quality second. Priority: M8 resume path is
Built, so **M10 GFI thin slice → M11 minimal local UI → then M9** intake +
validation and the extension shell. Milestone numbers stay linear and
global (no M8a / v2-M1 renames).

## Standalone synthesis (`synthesis.py`, Built M5)

One S2 call per top non-bridge gap: gap + top `TRANSFERS_TO` rationales
+ background block → grounded project (must reuse existing skills).
Report: `output/synthesis_report.json`.

## OSS issue sourcing (`oss.py`, Designed M10 — thin slice)

Per top gap (default top-5 non-bridge gaps, same filter as
`synthesize_for_gaps`): curated repo list → GitHub Search Issues
(`label:good-first-issue` + repo/topic/language) → S2 relevance filter
using the gap's `TRANSFERS_TO` rationale + `_background_block()`
grounding → persist. `Project` gains `type="oss_issue"`
(`graph.py:33` today says `standalone only (oss_issue deferred)`) with
`url, repo, labels, updated_at`. `CLOSES_GAP` edge reused unchanged.
Cache: `output/oss_issues.json` (query + timestamp + results), same
override-file pattern as `judge_report.json` / `gate_overrides.json` —
re-runs reuse silently. Auth: `GITHUB_TOKEN` via the existing
`secrets.py` keyring pattern (`Authorization: Bearer`); unauthenticated
still works for smoke tests. No pagination / ETag handling in the thin
slice. New dep: `requests` (or stdlib `urllib`; prefer `requests`).
Builds on the M8 resume path (resume → skills JSON works); no dependency
on M9.

**Explicit non-goals for the thin slice:** no issue-quality ranking beyond
the LLM filter, no stale/assigned detection, no pagination, no per-JD
mention-modality fix, no manifest / content-script / hosting /
multi-user auth.

**Thin-slice done = all true:** (1) full run on seed data completes:
ranking → `oss.py` → `plan.md` + `plan.html` with no manual steps beyond
existing gate approvals; (2) top gaps each show 3–5 linked issues with
repo + labels + `updated_at`, links resolve (HTTP 200); (3) second run
with no code change makes zero GitHub API calls (cache reuse);
(4) `ruff check .` and `pytest` clean. Quality bar deliberately absent —
a follow-up milestone adds precision/recall on issue relevance once
end-to-end holds.

## Rendering (`output.py`)

`plan.md` (ranked table + verdicts + JD traceability + projects) and
`plan.html` (M11, same data, clickable issue links — later the
extension side-panel body).

## History (links, not copies)

- Milestones: `03-milestones.md` M5, M10, M11 (GFI thin slice + local UI).
- Deferred: `03-milestones.md` §Deferred #3 (→ Designed M10; quality
  filtering remains the deferred part).
