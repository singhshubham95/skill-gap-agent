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
- **Hosting choice for demo purposes** — local only for v1; AuraDB free tier
  becomes relevant when Neo4j is restored (deferred-enhancements #1).