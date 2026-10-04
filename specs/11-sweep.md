# C1 — JD-Subset Sweep Harness

Evaluation harness over the built pipeline. Not a pipeline stage: it runs
the existing stage functions many times over different JD subsets and
produces a reviewable record mapping every plan to the exact JD subset that
produced it.

**Status: Built** (M12, validated 2026-10-03 — verification record in
[03-milestones.md](03-milestones.md) M12). Code: `sweep.py`, `m12_check.py`.

## Purpose

A single run over all JDs produces one plan with no way to tell whether the
plan is *right* or merely *plausible*. Varying the JD set shows whether the
plan tracks the input signal: a gap that appears for one JD and vanishes for
another is evidence the ranking responds to demand; a gap that appears
regardless is either a genuine constant or a bug.

## Sampling

Two families, both seeded (`random.Random(seed)`) for replicability:

| Family | Construction | Question it answers |
|---|---|---|
| Random | `k=3` JDs drawn without replacement, `n` draws | Typical-case behaviour; the baseline distribution |
| Contrastive | 3 near-identical JDs; 3 maximally different JDs; all JDs; singletons (`k=1`) | Stability under redundancy, fragmentation under diversity, full-signal baseline, per-JD coherence |

Random-only sampling is deliberately **not** the whole design: with 16 JDs
there are 560 triples and random draws overlap heavily, so most runs would
be near-duplicates of each other. Contrastive subsets buy more information
per run.

## Key insight — most LLM work is subset-independent

In [judge.py](../src/skill_gap_agent/judge.py), `judge_target()` scores a
target against `prune_candidates(target, sg.current_skills())`. Current
skills come from the resume (constant across subsets); only the *target
list* comes from the JDs. The judge's score for target `T` is therefore a
pure function of `T` — it does not depend on which subset surfaced `T`. The
same holds for gate overrides (the question is about the user's depth in the
*source* skill — constant) and OSS issues (the query is built from
`gap.target` alone).

Consequence: judge / gate / OSS caches are **shared across all subsets**
(`_shared/`), so a sweep costs ~23 judge calls total instead of
`n_subsets × ~20`. What *is* genuinely subset-dependent: JD ingestion
(which targets exist), `gap_score = weight × (1 − confidence)` (weight =
JDs in the subset), and synthesis (top-N selection + the weight in the
prompt). So: **shared caches, per-subset graphs and plans.**

## Runner shape (design revision 2026-10-03)

`sweep.py` calls the pipeline's stage functions directly —
`ingest_skills_json` + `ingest_jds`, cached judging, `review_targets`,
`rank_gaps`, `synthesize_for_gaps`, `source_oss_for_gaps`, `write_plan` —
the same functions `m5_plan.py` and the `cli.py` graph nodes call, with
every path passed explicitly. The first design drove the `cli.py` LangGraph
graph once per subset; in `--auto` mode (the only mode a sweep runs) the
graph adds no conditional behaviour and no interrupts, while its hardcoded
`output/` paths would have to be threaded through nodes that M11's server
also uses. Direct calls keep the harness isolated from the shipped runners.
The invariant the first design protected — **never re-implement a pipeline
stage inside the harness** — still holds (decision rows in
[02-decisions.md](02-decisions.md)).

## Output layout

Per-subset directories; no output collision:

```
output/sweeps/<sweep-id>/
├── manifest.json          # seed, k, n, model, temperature, resume + JD hashes
├── index.md               # subset -> JD titles -> top-5 gaps -> plan link
├── metrics.json           # stability / appearance / churn / consistency / grounding
├── _shared/               # judge_report.json, gate_overrides.json, oss_issues.json,
│                          #   implied_skills.json
└── s01/, s02/, ...        # graph.json, plan.md, plan.html, synthesis_report.json
                           # + jds/ (the subset's JD copies = membership on disk)
```

## Manifest must record subset membership explicitly

`Gap.source_jds` ([ranking.py](../src/skill_gap_agent/ranking.py)) records
which JDs *mention* a gap — it does **not** record which JDs were *in the
subset*. Without membership you cannot distinguish "this JD doesn't need
Spark" from "this JD wasn't in the run", which is exactly the confusion that
makes manual inspection useless. Each JD also gets a content hash so a
renamed or edited file cannot silently invalidate an old sweep.

## Pre-computed metrics

Automatic; they tell the reviewer *where* to look rather than replacing
review:

- **Stability** — Jaccard overlap of top-5 gap sets across subset pairs;
  per-gap appearance rate. High variance is itself a finding.
- **Superset consistency** — a gap present in subset A should still appear
  when JDs mentioning it are added. Violations are bugs, not opinions.
- **Rank churn** — rank distribution per gap across subsets (is
  "Fine-tuning" always #1, or does it swing?).
- **Grounding check** — the synthesis prompt requires reusing a named
  existing skill; a string check catches drift.
- **GFI link validity** — HTTP status per issue URL (M10 did this by hand).

## Two-pass manual review

Avoids confirmation bias: (1) score plan quality with the JD list hidden;
(2) reveal the subset and check whether the plan actually matches what those
JDs demand. The gap between the two scores is the interesting number.

## Replicability caveat

The seed gives **subset** replicability, not **output** replicability:
`LLMConfig.temperature` is 0.2, so re-running the same subset will not give
byte-identical plans. Sweep runs therefore set `temperature=0` and record it
in the manifest (decision row in [02-decisions.md](02-decisions.md)).

## Done criteria (met at M12 — verification record in roadmap M12)

1. `sweep.py` runs N subsets end-to-end with shared caches and writes the
   layout above, and exposes a `--list` dry run that prints the subsets
   without any LLM calls.
2. `manifest.json` + `index.md` let a reviewer jump from any plan to its
   exact JD subset.
3. `m12_check.py` verifies the sweep offline (stubbed LLM/search) —
   deterministic sampling, no output collision, cache sharing, manifest
   completeness.
4. `ruff check .` and `pytest` clean.

## History (links, not copies)

- Decisions: [02-decisions.md](02-decisions.md) (M12 rows — harness shape,
  shared caches, sampling, manifest, temperature, metrics, seed growth).
- Milestones: [03-milestones.md](03-milestones.md) M12 (verification record
  + learnings).
- Open: [03-milestones.md](03-milestones.md) §Open (sweep ground truth).