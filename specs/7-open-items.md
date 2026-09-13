# Open Items

Unresolved items that don't block starting.

- **Confidence-gate threshold + scope** (for milestone 4) — full-run judge
  confidences cluster high (top-edge min 0.65, mean 0.84) because the pruner
  now surfaces many candidates per skill. A 0.5 threshold would flag nothing.
  Decide: threshold (~0.7–0.75?) and scope (review top edge per target skill
  vs. all edges above threshold). Validate against the Databricks-style case.
- **Alias table contents** for normalization — seeded (~130 entries) from the
  manual session's merge decisions; extend as new surface forms appear.
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