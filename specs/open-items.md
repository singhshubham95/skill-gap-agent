# Open Items

Unresolved items that don't block starting.

- **Exact model pick** — starting with **GLM 5.3 Flash** (cheap tier, good
  structured-output compliance). At milestone 3, run a calibration check
  against one fallback cloud model (Haiku/GPT-class): verify confidence scores
  actually spread across 0–1 (not clustered at 0.7–0.9, which would make the
  gate never fire), check JSON failure rate, and compare cost for a full run.
  The `judge()` interface is provider-agnostic so this is a config change.
- **Alias table contents** for normalization — seed from the manual session's
  merge decisions.
- **Canonical-term extraction strategy** for descriptive skill phrases in the
  skills JSON (found in milestone 1, e.g. "Binary classification (large-scale,
  one-model-per-class reformulation...)" → "Binary classification") — regex
  parenthetical-stripping first, LLM fallback if needed; decide at milestone 2.
- **External skill taxonomy (ESCO)** — implemented as a loader with graceful
  fallback (`taxonomy.py`); the actual ESCO ICT data file is not yet downloaded.
  To enable: fetch the ESCO ICT skills subset (open data, EU Commission) and
  save as `data/taxonomy/esco_ict.json` with shape
  `[{"preferred": "...", "alt": [...], "broader": "..."}]`. Once present it
  automatically feeds alias resolution and implied-skill detection.
- **Implied-skill detection precision** — current pattern-based detection found
  14 implications on the seed data (spot-check quality is good: Python ←
  "Custom Airflow operator authoring (Python)", FAISS ← "Vector store
  implementation (FAISS)"). An LLM-assisted pass could catch subtler
  implications (e.g. "NL-to-SQL agents" implying SQL depth); consider after
  milestone 3 if the judge's gap list looks wrong.
- **Hosting choice for demo purposes** — local only for v1; AuraDB free tier
  becomes relevant when Neo4j is restored (deferred-enhancements #1).