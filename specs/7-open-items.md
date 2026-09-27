# Open Items

Unresolved items that don't block starting.

- **LangGraph wiring** — moved out of open items: it is now designed and
  scheduled as milestone M7 (see [5-milestones.md](5-milestones.md) and
  [2-architecture.md §9](2-architecture.md)).
- **Extraction call latency** — the M8 resume-extraction LLM call (one call,
  full resume text, hierarchical JSON out) took ~19 minutes via DeepSeek V4
  Flash on OpenRouter (2026-09-23), vs. ~3–10s for small/medium prompts.
  Likely the model's long reasoning on a structured-extraction task; the
  artifact-reuse design means it's a one-time cost per resume, but it makes
  interactive use painful. Options if it recurs: a smaller/faster extraction
  model (extraction is mechanical, not judgment — a flash-tier swap is a
  config change), or a request timeout + retry in `llm.py`. Revisit if M9's
  conversational intake needs faster turnaround.
- **Checkpoint msgpack type registration** — LangGraph (1.2.11) warns that
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
  **M7 update:** the automatic "re-judge with stricter rubric as a loop"
  branch was designed in §9 but explicitly deferred (decision recorded in
  [3-decisions.md](3-decisions.md)) — the gate's depth factor compensates
  and M6 validation showed ranking separates gaps from bridges. Revisit
  trigger: a validation pass where bridge/gap verdicts visibly misfire on
  clustered-high scores.
- **Alias table contents** for normalization — seeded (~130 entries) from
  merge decisions made while validating against the seed data, extended with
  ~50 M8 resume-extraction variants. The LLM-assisted vocabulary bridge
  (`vocab_bridge.py`, M8) now handles unanticipated variants; extend the
  manual table only for variants that recur across runs.
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