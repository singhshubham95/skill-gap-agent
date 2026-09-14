# Open Items

Unresolved items that don't block starting.

- **LangGraph wiring** — moved out of open items: it is now designed and
  scheduled as milestone M7 (see [5-milestones.md](5-milestones.md) and
  [2-architecture.md §9](2-architecture.md)).
- **Mention-modality classification (LLM pass)** — honest limitation of
  alternative groups (`requirements.py`): v1 cannot automatically classify
  each JD mention's modality ("such as LangChain, ..." = exemplar/any-of vs.
  "must have production experience with LangChain" = strict/all-of). The
  per-group mention policy (any-of vs. specific) is a hand-set approximation
  of what JDs typically do. A future LLM pass could classify modality per
  mention per JD and feed per-JD satisfaction into ranking — the proper fix,
  deferred until the hand-set policies visibly misfire.
- **Proficiency data upstream** — the skills JSON's own `self_assessment_flags`
  note suggests a future `skills_dataset_v2_rated.json` layering
  proficiency/recency per skill. If that file exists, the gate's depth
  question can pre-fill from it (and the judge prompt could use it too).
- **Judge score calibration** — full-run top confidences cluster high (min
  0.65, mean 0.84); the depth-factor multiplication from the gate partially
  compensates. If gap ranking still can't separate full gaps from bridges,
  consider re-prompting the judge with a stricter calibration rubric.
- **Alias table contents** for normalization — seeded (~130 entries) from
  merge decisions made while validating against the seed data; extend as new
  surface forms appear.
- **Canonical-term extraction strategy** — implemented in `normalize.py`
  (regex parenthetical/bracket stripping + generic-label colon handling +
  alias table). LLM fallback not needed so far; revisit only if extraction
  errors appear in new data.
- **External skill taxonomy (ESCO)** — implemented as a loader with graceful
  fallback (`taxonomy.py`); the actual ESCO ICT data file is not yet downloaded.
  To enable: fetch the ESCO ICT skills subset (open data, EU Commission) and
  save as `data/taxonomy/esco_ict.json` with shape
  `[{"preferred": "...", "alt": [...], "broader": "..."}]`. Once present it
  automatically feeds alias resolution and implied-skill detection.
- **Implied-skill detection precision** — pattern-based detection works (14
  implications on seed data, user-approved via the y/n/a flow). An LLM-assisted
  pass could catch subtler implications (e.g. "NL-to-SQL agents" implying SQL
  depth); consider if the judge's gap list looks wrong after milestone 5.
- **Hosting choice for demo purposes** — local only for v1; AuraDB free tier
  becomes relevant when Neo4j is restored (deferred-enhancements #1).