# Verification report — T-M16
Run: 2026-10-06 09:24:32

## PASS — `ruff check .`

```
All checks passed!

```

## PASS — `pytest`

```
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\singh\Documents\personal\learning\projects\skill-gap-agent-worktrees\impl-T-M16
configfile: pyproject.toml
plugins: anyio-4.15.1, langsmith-0.14.4
collected 19 items

src\skill_gap_agent\test_m13.py ...                                      [ 15%]
src\skill_gap_agent\test_m14.py ....                                     [ 36%]
src\skill_gap_agent\test_m15.py .....                                    [ 63%]
src\skill_gap_agent\test_m16.py .......                                  [100%]

============================= 19 passed in 9.10s ==============================

```

## PASS — `node --check extension/sidepanel.js`

```

```

## PASS — `python -m skill_gap_agent.m16_check`

```
[m11] &quot;GET /api/oauth/pending?state=abc HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/oauth/state HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/oauth/callback?code=one-time-code&amp;state=abc HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/oauth/pending?state=abc HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/oauth/callback?code=evil-code&amp;state=unknown HTTP/1.1&quot; 400 -
[m11] &quot;GET /api/oauth/pending?state=unknown HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/oauth/callback?code=evil-code HTTP/1.1&quot; 400 -
[m11] &quot;POST /api/oauth/exchange HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/oauth/pending?state=abc HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/oauth/exchange HTTP/1.1&quot; 409 -
[m11] &quot;POST /api/oauth/state HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/oauth/exchange HTTP/1.1&quot; 409 -
[m11] &quot;POST /api/oauth/state HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/oauth/callback?code=boom-code&amp;state=abc HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/oauth/exchange HTTP/1.1&quot; 502 -
oauth connect OK: state-validated callback -> pending -> exchange {code_verifier, state} -> keyring slot
[m11] &quot;POST /api/run HTTP/1.1&quot; 409 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
consent gate OK: 409 without ack, verbatim disclaimer, versioned flag
retry classification OK: transient retries + Retry-After, non-transient fails first attempt
bounded attempts OK: 3 API attempts for max_retries=3
free bounded attempts OK: 5 API attempts per logical judge() call in free mode
model fallback OK: :free rotation on 404 + 429/5xx exhaustion, 5-attempt free cap
llm_model OK: last_model() reports the answering :free ID
M16 CHECK PASS: OAuth connect, consent gate, retry classification, bounded attempts (free + paid), model fallback, llm_model status OK.

```

## PASS — `python -m skill_gap_agent.m10_check`

```
queries OK: strict='label:"good first issue" Fine-tuning language:python' broad='label:"good first issue" Fine-tuning'
M10 CHECK PASS: 4 oss_issue projects, 8 CLOSES_GAP edges, cache reuse OK, md+html OK.

```

## PASS — `python -m skill_gap_agent.m11_check`

```
jds OK: 16 files (e.g. 'Machine_Learning_Engineer_4_Adobe.txt')
[m11] &quot;GET / HTTP/1.1&quot; 200 -
index OK: Generate button + poll + plan link present
[m11] &quot;GET /api/jds HTTP/1.1&quot; 200 -
api/jds OK: 16 names match data/jds/
[m11] &quot;POST /api/run HTTP/1.1&quot; 202 -
[m11] &quot;POST /api/run HTTP/1.1&quot; 409 -
api/run OK: 202 start + 409 single-run guard
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
api/status OK: running (+stage) -> done
[m11] &quot;GET /plan.html HTTP/1.1&quot; 200 -
plan.html OK: served after run
[m11] &quot;GET /jds/Machine_Learning_Engineer_4_Adobe.txt HTTP/1.1&quot; 200 -
[m11] &quot;GET /jds/../cli.py HTTP/1.1&quot; 400 -
jd viewer OK: /jds/'Machine_Learning_Engineer_4_Adobe.txt' served, traversal blocked
verdict links OK: linked with jd_files, plain without
(note: output/plan.html currently holds stub content from this check)
M11 CHECK PASS: 16 JDs listed, run+guard+stage+plan+jds OK.

```

## PASS — `python -m skill_gap_agent.m12_check`

```
sampling OK: 9 subsets (near-identical=['j0.txt', 'j1.txt', 'j2.txt'])
[s01] contrastive:near-identical: 3 JD(s) -> 3 target skill(s)
[s01] top gaps: Streaming data (1.0), Data governance (0.5), Data pipelines (0.5)
[s02] contrastive:diverse: 3 JD(s) -> 3 target skill(s)
[s02] top gaps: Data governance (0.5), Graph databases (0.5), Streaming data (0.5)
[s03] contrastive:all: 4 JD(s) -> 4 target skill(s)
[s03] top gaps: Streaming data (1.0), Data governance (0.5), Data pipelines (0.5)
[s04] random: 3 JD(s) -> 3 target skill(s)
[s04] top gaps: Streaming data (1.0), Data pipelines (0.5), Graph databases (0.5)
[s05] random: 3 JD(s) -> 4 target skill(s)
[s05] top gaps: Data governance (0.5), Data pipelines (0.5), Graph databases (0.5)
[s06] singleton: 1 JD(s) -> 2 target skill(s)
[s06] top gaps: Data pipelines (0.5), Streaming data (0.5)
[s07] singleton: 1 JD(s) -> 1 target skill(s)
[s07] top gaps: Data governance (0.5)
run/cache OK: 7 subsets, judge calls 4 new + 16 cached
metrics OK: jaccard 0.6, appearance, churn 3->5, violation + grounding flagged
M12 CHECK PASS: sampling deterministic, outputs isolated, judge cache shared, manifest+index complete, metrics verified.

```

## PASS — `python -m skill_gap_agent.m13_check`

```
 target <- top transfer
   0.50    1  partial       Data governance           <- Python programming experience (0.50)
   0.50    1  partial       Data pipelines            <- Python programming experience (0.50)
   0.50    1  partial       Streaming data            <- Python programming experience (0.50)
Gaps written: output\gaps.json
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/gaps HTTP/1.1&quot; 200 -
gaps OK: 3 ranked (Data governance, Data pipelines, Streaming data)
[m11] &quot;POST /api/run HTTP/1.1&quot; 202 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -

Plan written: output\plan.md
Graph saved: 9 nodes, 9 edges
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /plan.html HTTP/1.1&quot; 200 -
link policy OK: 5 links target new tabs
[m11] &quot;GET /jds/Governance_Analyst.txt HTTP/1.1&quot; 200 -
[m11] &quot;GET /jds/no_such_jd.txt HTTP/1.1&quot; 404 -
jd viewer OK: captured JDs served from output/captured_jds/
plan OK: projects + Good-First-Issues rendered
[m11] &quot;POST /api/run HTTP/1.1&quot; 409 -
guard OK: second phase 'plan' rejected with 409
M13 CHECK PASS: cli wiring + manifest + two-phase gaps/plan flow OK.
Deserializing unregistered type skill_gap_agent.ranking.Gap from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.ranking', 'Gap')]
Deserializing unregistered type skill_gap_agent.synthesis.SynthesizedProject from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.synthesis', 'SynthesizedProject')]
Deserializing unregistered type skill_gap_agent.oss.OssIssue from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.oss', 'OssIssue')]

```

## PASS — `python -m skill_gap_agent.m14_check`

```
LLM extraction unavailable (m14_check: LLM extraction disabled); falling back to regex scan.
Extraction artifact saved: output\extracted_skills.json (source: regex)
Resume -> skills JSON: 4 phrases (source: regex)
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
Reusing extraction artifact: output\extracted_skills.json
Resume -> skills JSON: 4 phrases (source: artifact)
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
LLM extraction unavailable (m14_check: LLM extraction disabled); falling back to regex scan.
Extraction artifact saved: output\extracted_skills.json (source: regex)
Resume -> skills JSON: 2 phrases (source: regex)
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 415 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 415 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 413 -
LLM extraction unavailable (m14_check: LLM extraction disabled); falling back to regex scan.
Extraction artifact saved: output\extracted_skills.json (source: regex)
Resume -> skills JSON: 4 phrases (source: regex)
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
resume endpoint OK: upload + cache hit + re-extract + validation + sanitized names
[m11] &quot;POST /api/key HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/providers HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/key HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/providers HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/key HTTP/1.1&quot; 400 -
[m11] &quot;POST /api/key HTTP/1.1&quot; 400 -
key endpoint OK: keyring/session modes, validation, no key leakage
resolution OK: skills precedence + provider validation
panel + launcher OK: resume input, key form, no key in storage, bat
M14 CHECK PASS: resume upload + key entry + resolution + panel/launcher OK.

```

## PASS — `python -m skill_gap_agent.m15_check`

```
0 -
[m11] &quot;GET /api/gaps HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/run HTTP/1.1&quot; 202 -
  [1] Data governance (score 0.4)...
      -> M15 stub project
  [2] Streaming data (score 0.4)...
      -> M15 stub project
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -

Plan written: output\plan.md
Graph saved: 13 nodes, 20 edges
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /plan.html HTTP/1.1&quot; 200 -
llm labels OK: fresh 'LLM', cache-reuse 'LLM (cached)'
LLM extraction unavailable (m15: simulated LLM outage); falling back to regex scan.
Extraction artifact saved: C:\Users\singh\AppData\Local\Temp\m15-resume-9_gdvdwh\extracted_skills.json (source: regex)
Resume -> skills JSON: 4 phrases (source: regex)
Reusing extraction artifact: C:\Users\singh\AppData\Local\Temp\m15-resume-9_gdvdwh\extracted_skills.json
Resume -> skills JSON: 4 phrases (source: artifact)
Reusing extraction artifact: C:\Users\singh\AppData\Local\Temp\m15-resume-9_gdvdwh\extracted_skills.json
Resume -> skills JSON: 4 phrases (source: artifact)
extraction provenance OK: sidecar line 2 labels cache hits
M15 CHECK PASS: LLM presence policy — refusal, loud degradation, labels OK.
Deserializing unregistered type skill_gap_agent.ranking.Gap from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.ranking', 'Gap')]
Deserializing unregistered type skill_gap_agent.oss.OssIssue from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.oss', 'OssIssue')]
Deserializing unregistered type skill_gap_agent.synthesis.SynthesizedProject from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.synthesis', 'SynthesizedProject')]

```
