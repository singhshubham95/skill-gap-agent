# S4 — Skill Cleaner

Shared dictionary plus cleaning of both raw lists. One function,
two inputs — resume side and JD side are subsections, not files.

**Status: split** — manual path Built (M2 + M8 aliases); LLM bridge
code-exists-unwired (see below).

## Dictionary (`normalize.py`, `taxonomy.py`)

- `canonical_term()`: alias-table win → drop credentials → strip
  parens/brackets/suffixes → colon rule (generic labels only) →
  first-of-list → alias re-check.
- `ALIASES`: seeded from M2 merges + ~50 M8 extraction variants.
  Extend manually only for recurring variants.
- `taxonomy.py`: ESCO ICT loader, graceful fallback (data file pending —
  see `5-milestones.md` §Open: ESCO).

## Resume side (user skills)

`ingest.py::ingest_skills_json` → dedup on canonical → `HAS_SKILL`.
Implied skills (`implied.py`, `IMPLY_PATTERNS` + GKE from M8): detect
from parentheticals, propose y/n/a with evidence, persist
`output/implied_skills.json`, enter as `category: implied`.

## JD side (target skills)

`JD_SKILL_LEXICON` regex scan → `source: target` + `REQUIRES{weight}`.
JD skills are born canonical (lexicon keys pre-aligned); if extraction
ever goes LLM, normalization must run here too. Mention-modality
(`any-of` vs `must-have`) is hand-set policy in S5, not parsed —
see `5-milestones.md` §Open (modality).

## LLM vocabulary bridge (`vocab_bridge.py`) — UNWIRED

`bridge_vocabulary()` classifies unmatched canonical terms against the
full existing vocabulary (merge-or-new, batched, conservative);
`apply_bridge()` rewrites. Decisions persist to
`output/vocab_bridge.json`. **No caller wires it yet** — `ingest.py` /
`cli.py` never import it. Wiring is the open work; status flips to
Built only when a run exercises it end-to-end.

## History (links, not copies)

- Decisions: `3-decisions.md` (M8 bridge row; M2 implied-flow row).
- Milestones: `5-milestones.md` M2, M8; §Open (alias, canonical strategy,
  ESCO, implied precision, modality).
