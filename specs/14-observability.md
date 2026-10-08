# C4 — Observability + Judge Evaluation

Tooling around the built pipeline, not a pipeline stage. Opt-in LangSmith
tracing answers *what happened inside a run*; a golden-set evaluation of
the transferability judge answers *is the judge right*. Planned code:
`tracing.py`, `judge_eval.py`, `evals/judge_golden.jsonl`, plus the repo's
first test/eval CI workflow.

**Status: 🎯 Designed** (M17, no code yet). Build order and slices
17a–17d: [03-milestones.md](03-milestones.md) M17. Decision rows:
[02-decisions.md](02-decisions.md) M17 rows. Per-runner hook notes live in
[05-ai-caller.md](05-ai-caller.md) §Tracing hook and
[10-flow-runner.md](10-flow-runner.md) (`--trace` flag) — this file is the
design home.

## Design

**Purpose.** Two questions the repo cannot answer today. (1) *What happened
inside a run?* — which prompt the judge saw for a target, what it answered,
how long each call took, what it cost, where a retry fired. Today the only
record is console prints plus the persisted `output/*.json` artifacts, which
hold results but not the calls that produced them. (2) *Is the judge right?*
— M3 calibration-checked 5 skills by hand, and M12 measures stability, not
correctness (§Open: sweep ground truth). Nothing tells us whether a prompt or
model change made the judge better or worse. M17 adds **tracing** for (1)
and a **golden-set evaluation** of the judge for (2). Like M12, this is
tooling around the built pipeline, not a new pipeline stage.

**Backend = LangSmith cloud, free Developer tier** (decision rows in
[02-decisions.md](02-decisions.md)). Background for newcomers: LangSmith is
a hosted service from the company behind LangGraph. A program sends it
"traces" — a tree of "runs", one per function or LLM call, each with
inputs, outputs, timing and token counts — and its web UI shows them. It is
already cloud-hosted, so there is nothing to deploy; self-hosting LangSmith
needs an Enterprise licence, which is why it is not the choice here.
LangGraph reports every graph node as a run automatically once tracing is
switched on — but `llm.py` calls the plain `openai` SDK, not LangChain, so
LLM calls are invisible until the client is wrapped (below).

**Tracing is opt-in and off by default.** The project is local-first:
resumes and JDs never leave the machine except to the LLM provider. With
tracing on, prompts — which contain resume-derived skills and JD text — are
also sent to LangSmith. So a run is traced **only** when the user asks:
`--trace` on the runners (`cli.py`, `server.py`, `sweep.py`), or
`LANGSMITH_TRACING=true` in the environment (LangSmith's own variable).
Redaction for sensitive runs: LangSmith's `LANGSMITH_HIDE_INPUTS` /
`LANGSMITH_HIDE_OUTPUTS` env vars keep the tree shape and timings but drop
payloads.

**One module owns tracing: `tracing.py` (to be created in M17).** Same idea
as `llm.py` owning LLM access — no other module imports `langsmith`.

| Function | Does | When tracing is off / `langsmith` missing |
|---|---|---|
| `enable_tracing(project="skill-gap-agent")` | Resolves `LANGSMITH_API_KEY` via `secrets.get_secret()` (env → OS keyring, same as every key); sets `LANGSMITH_TRACING` / `LANGSMITH_API_KEY` / `LANGSMITH_PROJECT` in `os.environ` so LangGraph picks them up; returns `True` if on | Returns `False`; missing key → one ASCII warning line, run continues untraced. **Tracing never fails a run** |
| `wrap_client(client)` | `langsmith.wrappers.wrap_openai(client)` — every `chat.completions.create` becomes a child run with prompt, response, tokens, latency | Returns `client` unchanged |
| `traced(name)` | Decorator = `langsmith.traceable(name=..., run_type="chain")` — labels a stage function so LLM calls nest under it | No-op decorator |
| `run_config(thread_id, cfg)` | Returns LangGraph `config` extras: `run_name`, `tags` (runner name), `metadata` (provider, model, temperature, thread_id) | Returns `{}` extras |

**Where the hooks go** (the only edits to existing modules):

- S2 `llm.py::_client()` returns `tracing.wrap_client(OpenAI(...))`. One
  line; every caller (S1 extraction, S4 bridge, S5 judge, S6 synthesis + OSS
  filter) is covered at once.
- Stage functions get `@traced`: `judge.judge_target`,
  `synthesis.synthesize_project`, `oss.filter_issues_relevance`,
  `resume.extract_skills_llm`, `vocab_bridge.bridge_vocabulary`. The
  target / gap name is a function argument, so it shows up as the run's
  input — the trace for "AWS" is searchable by name.
- Runners call `enable_tracing()` before building the graph and merge
  `run_config(...)` into the existing `{"configurable": {"thread_id": ...}}`.

What a traced CLI run looks like in the LangSmith UI:

```
skill-gap-run  [cli, deepseek-v4-flash-0731, t=0.2]
├── ingest
├── judge
│   ├── judge_target("AWS")      → ChatOpenAI call (prompt, JSON out, 1.2k tok, 3.1 s)
│   ├── judge_target("Spark")    → ChatOpenAI call
│   └── ...
├── gate      (interrupt → resume shows as two node runs; replay, not a bug — S7)
├── rank
├── synthesize
│   └── synthesize_project("Spark") → ChatOpenAI call
├── oss
│   └── filter_issues_relevance(...) → ChatOpenAI call
└── output
```

**Judge golden set — `evals/judge_golden.jsonl` (to be created in M17).**
One JSON object per line: a target skill, the candidate current skills, and
a **human-agreed confidence band** per candidate (a band, not a point:
two careful humans agree on "0.6–0.9", rarely on "0.75").

```json
{"id": "aws-gcp", "target": "AWS", "candidates": ["GCP", "Cloud SQL", "Excel"],
 "bands": {"GCP": [0.5, 0.8], "Cloud SQL": [0.3, 0.6], "Excel": [0.0, 0.3]},
 "source": "M6 hand analysis", "note": "same cloud concepts, different names"}
```

- **Committed to git**, unlike `data/`: rows are generic skill pairs, no
  resume text or personal data. LangSmith gets a *copy* as a dataset; the
  repo file is the version-controlled truth.
- **Seeded** from evidence the repo already has: the M6 sealed hand analysis
  (e.g. LangGraph ← Google ADK high, AWS ← GCP partial — S5
  `08-gap-measurer.md` §Validation rubric) and the M3/M4 records. Target
  size ~30 rows first, growing to 50–100.
- Bands are labeled by the user/author; each row records its `source`.

**Eval runner — `judge_eval.py` (to be created in M17).**
`python -m skill_gap_agent.judge_eval [--langsmith] [--provider P --model M]`.
For each row it builds a small `SkillGraph` holding exactly the row's
candidates as current skills and calls the real `judge_target()` (never a
re-implementation — the M12 invariant). Two metrics, because a judge miss
has two possible causes:

| Metric | Measures | Computed as |
|---|---|---|
| `in_band` | Judge accuracy | share of (row, candidate) pairs whose returned confidence lies inside the band; a candidate the judge drops (below `min_confidence` 0.3) counts as 0.0 |
| `pruner_recall` | Did `prune_candidates()` even show the judge the right skills? | share of high-band candidates (band low ≥ 0.5) that survive pruning — targets the known M3 pruning-miss issue |

Plus `mean_abs_error` to band midpoint and the confidence distribution
(feeds §Open: judge score calibration). Output: a local report
`output/evals/<run-id>.json` **always** (no LangSmith account needed); with
`--langsmith`, the same rows run as a LangSmith **experiment** via
`langsmith.evaluate()`, so runs with different prompts/models sit side by
side in the UI. `temperature=0` for evals, recorded in the report (same
reason as the M12 sweep row).

**CI (two tiers).** Background: GitHub does **not** give repository secrets
to workflows triggered by pull requests from forks, so an eval that needs
an OpenRouter + LangSmith key cannot run on a contributor's fork PR.
Therefore: (a) **every PR** runs the offline tier — `ruff check .`,
`pytest` (incl. `test_m17.py`) — no secrets, no network; (b) the **live
eval** runs on `workflow_dispatch` and on pushes to `main` that touch
`judge.py` / `llm.py` / `synthesis.py`, using the owner's secrets, and fails
if `in_band` drops more than 5 points below the last recorded baseline.
The repo's only workflow today is `agent-gates.yml` (scope checks, no
tests); M17 adds the first test/eval workflow.

**Gate decisions as LangSmith feedback — analysis signal, NOT judge
labels.** M4's redesign is the reason: the gate asks the user about their
depth in the *source* skill and their intent, never whether the judge's
transfer score is right (the user lacks the target skill by definition). So
a gate answer cannot be used as ground truth for the judge. It is still
useful context: when tracing is on, `judge_target()`'s run id is stored in
`judge_report.json` (`trace_run_id`), and `gate.review_targets()` attaches
`gate_depth` / `gate_intent` as feedback on that run — so the UI can
answer "how often does the gate flip a verdict, and for which targets?"
Silently skipped when tracing is off.

**Explicit non-goals (recorded, not oversights):** self-hosting LangSmith
(Enterprise licence) or Langfuse (ops cost — fallback only, decision row);
LLM-as-judge grading of `plan.md` (needs the golden set to calibrate it
first — candidate for a later milestone); tracing the Chrome extension's
JS (the pipeline it triggers in `server.py` *is* traced); online
production monitoring/alerts (single local user today).

**Done criteria:** (1) `--trace` run of `cli.py` on seed data produces one
LangSmith trace tree with every graph node and every LLM call nested under
its stage function; the same run without `--trace` sends nothing and
behaves exactly as before; missing key → warning, run completes. (2)
`evals/judge_golden.jsonl` has ≥30 labeled rows; `judge_eval.py` prints
`in_band` / `pruner_recall` locally, and with `--langsmith` creates an
experiment. (3) `m17_check.py` verifies offline (stubbed LLM, no network):
tracing no-ops when off, `wrap_client` identity when disabled, golden-set
schema valid, metric math on a fixture. (4) CI offline tier green on a PR.
(5) `ruff check .` and `pytest` clean.

