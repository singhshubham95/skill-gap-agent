# Verification report — T-M26
Run: 2026-10-14 00:32:46

## PASS — `.venv\Scripts\python.exe -m ruff check src scripts tools`

```
All checks passed!

```

## PASS — `.venv\Scripts\python.exe -m pytest`

```
============================= test session starts =============================
platform win32 -- Python 3.14.7, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\singh\Documents\personal\learning\projects\skill-gap-agent
configfile: pyproject.toml
plugins: anyio-4.15.1, langsmith-0.12.4
collected 59 items

src\skill_gap_agent\test_m13.py ...                                      [  5%]
src\skill_gap_agent\test_m14.py ....                                     [ 11%]
src\skill_gap_agent\test_m15.py .....                                    [ 20%]
src\skill_gap_agent\test_m16.py .........                                [ 35%]
src\skill_gap_agent\test_m18.py ...                                      [ 40%]
src\skill_gap_agent\test_m19.py ..                                       [ 44%]
src\skill_gap_agent\test_m20.py ....                                     [ 50%]
src\skill_gap_agent\test_m21.py ....                                     [ 57%]
src\skill_gap_agent\test_m22.py ....                                     [ 64%]
src\skill_gap_agent\test_m23.py ....                                     [ 71%]
src\skill_gap_agent\test_m24.py ...                                      [ 76%]
src\skill_gap_agent\test_m26.py .......                                  [ 88%]
src\skill_gap_agent\test_m7.py .                                         [ 89%]
src\skill_gap_agent\test_m9.py ......                                    [100%]

============================= 59 passed in 14.27s =============================

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m7_check`

```
  3  unjudged      LlamaIndex                <- unjudged
   3.00    3  unjudged      Model evaluation          <- unjudged
   2.00    2  unjudged      Apache Airflow            <- unjudged
   2.00    2  unjudged      BigQuery                  <- unjudged
   2.00    2  unjudged      Deep Learning             <- unjudged
   2.00    2  unjudged      FastAPI                   <- unjudged
   2.00    2  unjudged      Kubernetes                <- unjudged
   2.00    2  unjudged      Power BI                  <- unjudged
   2.00    2  unjudged      Tableau                   <- unjudged
   2.00    2  unjudged      Terraform                 <- unjudged
   2.00    2  unjudged      Vertex AI                 <- unjudged
   1.00    1  unjudged      Data visualization        <- unjudged
   1.00    1  unjudged      Multi-agent systems       <- unjudged
   1.00    1  unjudged      Streaming data            <- unjudged
   1.00    1  unjudged      scikit-learn              <- unjudged
   0.00   13  held          Python                    <- Python programming experience (1.00)
Gaps written: output\sessions\90562999bb022e1613ac1c083efb0f99eff5c153a9399b574ffb04b1a69a3a73\gaps.json

Plan written: output\sessions\90562999bb022e1613ac1c083efb0f99eff5c153a9399b574ffb04b1a69a3a73\plan.md
Graph saved: 66 nodes, 272 edges

Interrupts handled: 4
profile.json gate decisions: ['Fine-tuning', 'Spark']
gate_overrides.json exists (must be False): False
Final state next: ()
PASS
Deserializing unregistered type skill_gap_agent.gate.GateDecision from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.gate', 'GateDecision')]
Deserializing unregistered type skill_gap_agent.ranking.Gap from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.ranking', 'Gap')]

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m10_check`

```
queries OK: strict='label:"good first issue" Fine-tuning language:python' broad='label:"good first issue" Fine-tuning'
M10 CHECK PASS: 4 oss_issue projects, 8 CLOSES_GAP edges, cache reuse OK, md+html OK.

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m11_check`

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

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m12_check`

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

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m13_check`

```
ta pipelines            <- Python programming experience (0.50)
   0.50    1  partial       Streaming data            <- Python programming experience (0.50)
Gaps written: output\sessions\e08b73cfb0e5b6e82d7858e1bfa2ed13822b08f99e37e5a15bd3b4f572424fa3\gaps.json
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/gaps HTTP/1.1&quot; 200 -
gaps OK: 3 ranked (Data governance, Data pipelines, Streaming data)
[m11] &quot;POST /api/run HTTP/1.1&quot; 202 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -

Plan written: output\sessions\e08b73cfb0e5b6e82d7858e1bfa2ed13822b08f99e37e5a15bd3b4f572424fa3\plan.md
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

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m14_check`

```
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 415 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 415 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 413 -
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

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m15_check`

```
uot; 200 -
llm labels OK: fresh 'LLM', cache-reuse 'LLM (cached)'
LLM extraction unavailable (m15: simulated LLM outage); falling back to regex scan.
Extraction artifact saved: C:\Users\singh\AppData\Local\Temp\m15-resume-7be_k6wb\extracted_skills.json (source: regex)
Resume -> skills JSON: 4 phrases (source: regex)
LLM extraction unavailable (m15: simulated LLM outage); falling back to regex scan.
Extraction artifact saved: C:\Users\singh\AppData\Local\Temp\m15-resume-7be_k6wb\extracted_skills.json (source: regex)
Resume -> skills JSON: 4 phrases (source: regex)
Extraction artifact saved: C:\Users\singh\AppData\Local\Temp\m15-resume-7be_k6wb\extracted_skills.json (source: regex)
Resume -> skills JSON: 4 phrases (source: regex)
Reusing extraction artifact: C:\Users\singh\AppData\Local\Temp\m15-resume-7be_k6wb\extracted_skills.json
Resume -> skills JSON: 4 phrases (source: artifact)
Reusing extraction artifact: C:\Users\singh\AppData\Local\Temp\m15-resume-7be_k6wb\extracted_skills.json
Resume -> skills JSON: 4 phrases (source: artifact)
extraction provenance OK: sidecar line 2 labels cache hits
M15 CHECK PASS: LLM presence policy — refusal, loud degradation, labels OK.
Deserializing unregistered type skill_gap_agent.ranking.Gap from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.ranking', 'Gap')]
Deserializing unregistered type skill_gap_agent.oss.OssIssue from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.oss', 'OssIssue')]
Deserializing unregistered type skill_gap_agent.synthesis.SynthesizedProject from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.synthesis', 'SynthesizedProject')]

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m16_check`

```
 200 -
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
retry classification OK: transient retries + Retry-After, non-transient fails first attempt (paid + free, chat + judge)
bounded attempts OK: 3 API attempts for max_retries=3
free bounded attempts OK: 5 API attempts per logical judge() call in free mode
model fallback OK: :free rotation on 404 + 429/5xx exhaustion, 5-attempt free cap
llm_model OK: last_model() reports the answering :free ID
extraction timeout OK: 30-minute budget on every path, caller provider/free_tier preserved
quota reason OK: free-mode 429 exhaustion surfaces the spec's loud-degradation message; paid mode keeps diagnostics
M16 CHECK PASS: OAuth connect, consent gate, retry classification, bounded attempts (free + paid), model fallback (chat + judge), llm_model status, extraction timeout, quota reason OK.

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m18_check`

```
[m11] &quot;GET /api/key/status?provider=openrouter HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/key/status?provider=openrouter HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/key/status?provider=openrouter HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/key HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/key/status?provider=openrouter HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/key/status?provider=openrouter HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/key/status?provider=nope HTTP/1.1&quot; 400 -
[m11] &quot;GET /api/key/status HTTP/1.1&quot; 200 -
key-status endpoint OK: presence, validation stub, TTL cache, invalidation, allowlist payload
mode mapping OK: state rendering off key_set + free/paid/rule -> run-contract fields
panel surface OK: default view, states, captions, gate, key-info validation, no key in storage
M18 CHECK PASS: state-driven panel + key validation + mode mapping OK.

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m19_check`

```
[m11] &quot;GET /plan.html HTTP/1.1&quot; 200 -
[m11] &quot;GET /plan.html?theme=dark HTTP/1.1&quot; 200 -
[m11] &quot;GET /plan.html?theme=light HTTP/1.1&quot; 200 -
[m11] &quot;GET /plan.html?theme=evil HTTP/1.1&quot; 200 -
[m11] &quot;GET /plan.html?theme=dark%27%3E HTTP/1.1&quot; 200 -
[m11] &quot;GET /plan.html?theme=../../x HTTP/1.1&quot; 200 -
[m11] &quot;GET /plan.html?theme= HTTP/1.1&quot; 200 -
plan theming OK: stylesheet palettes, JS-free, ?theme= injection, invalid values ignored, disk untouched
panel theming OK: button, palettes, persistence, plan link
M19 CHECK PASS: system theme + override + plan follows panel OK.

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m20_check`

```
[m11] &quot;GET /api/status HTTP/1.1&quot; 403 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 403 -
[m11] &quot;POST /api/oauth/state HTTP/1.1&quot; 403 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/oauth/state HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/oauth/state HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/oauth/state HTTP/1.1&quot; 200 -
origin gate OK: foreign/null refused, extension/self/headerless pass
[m11] &quot;POST /api/run HTTP/1.1&quot; 415 -
[m11] &quot;POST /api/run HTTP/1.1&quot; 415 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 415 -
content-type OK: text/plain POST + wrong resume type refused
[m11] &quot;POST /api/run HTTP/1.1&quot; 400 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/run HTTP/1.1&quot; 400 -
skills_path containment OK: outside-repo and non-json refused
panel transport rule OK: normalizeServer + loadState validation
m20_check: PASS

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m21_check`

```
[m11] &quot;POST /api/resume HTTP/1.1&quot; 409 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 415 -
resume ack gate OK: 409 without X-Disclosure-Ack, gate passes with it
disclosure copy OK: claim ban, named destinations, GitHub note
panel wiring OK: versioned consent gates upload + analyze, ack header
m21_check: PASS

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m22_check`

```
icons OK: 3 sizes, valid PNGs, manifest + action wired
policy OK: Limited Use statement, named destinations, landing link
register OK: every manifest permission/host justified, disclaimers present
links OK: no stale references in the derived registers
m22_check: PASS

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m23_check`

```
no-click OK: assist wiring (scroll + focus + yellow highlight) present
guidance OK: error message + panel status + docs mention expand
extraction OK: selectors + response shape + message contract unchanged
m23_check: PASS

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m24_check`

```
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 409 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 400 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 400 -
[m11] &quot;POST /api/resume HTTP/1.1&quot; 409 -
upload contract OK: rule-only upload (no LLM), mode/provider stashed for analyze, free consent enforced, defaults preserved, bad input rejected
Extraction artifact saved: C:\Users\singh\AppData\Local\Temp\tmpxa8od706\ex.json (source: llm)
Resume -> skills JSON: 1 phrases (source: llm)
Reusing extraction artifact: C:\Users\singh\AppData\Local\Temp\tmpxa8od706\ex.json
Resume -> skills JSON: 1 phrases (source: artifact)
Extraction artifact saved: C:\Users\singh\AppData\Local\Temp\tmpxa8od706\ex.json (source: regex)
Resume -> skills JSON: 2 phrases (source: regex)
Extraction artifact saved: C:\Users\singh\AppData\Local\Temp\tmpxa8od706\ex.json (source: llm)
Resume -> skills JSON: 1 phrases (source: llm)
LLM extraction unavailable (provider down); falling back to regex scan.
Extraction artifact saved: C:\Users\singh\AppData\Local\Temp\tmpxa8od706\ex.json (source: regex)
Resume -> skills JSON: 2 phrases (source: regex)
Extraction artifact saved: C:\Users\singh\AppData\Local\Temp\tmpxa8od706\ex.json (source: llm)
Resume -> skills JSON: 1 phrases (source: llm)
Reusing extraction artifact: C:\Users\singh\AppData\Local\Temp\tmpxa8od706\ex.json
Resume -> skills JSON: 1 phrases (source: artifact)
mode-scoped cache OK: classes never cross, fallbacks retried, llm hits preserved, legacy sidecars read as llm
panel surface OK: setup order, consent placement, copy contract, upload headers, mode summary
M24 CHECK PASS: mode governs ingestion + setup order + mode-aware cache OK.

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m26_check`

```
M call failed (non-transient, not retried): Error 400
info 00:32:45 [-] req: POST /api/run received
info 00:32:45 [server-1791918165712671400] run: start phase=full mode=paid llm=False provider=openrouter free_tier=False model=- options={top_n=3,use_llm=False}
info 00:32:45 [server-1791918165712671400] req: POST /api/run -> 202 in 0.5ms
info 00:32:45 [server-1791918165712671400] req: GET /api/status received
info 00:32:45 [server-1791918165712671400] req: GET /api/status -> 200 in 0.7ms
info 00:32:46 [server-m26-check] stage: ingest enter
info 00:32:46 [server-m26-check] stage: ingest exit in 82.9ms out=[stats={5 keys}]
info 00:32:46 [server-m26-check] stage: judge enter
info 00:32:46 [server-m26-check] stage: judge exit in 3.5ms out=[judged=False unjudged=21]
info 00:32:46 [server-m26-check] stage: gate enter
info 00:32:46 [server-m26-check] gate: overrides=22
info 00:32:46 [server-m26-check] stage: gate exit in 1.0ms out=[gate_decisions=0]
info 00:32:46 [server-m26-check] stage: rank enter
info 00:32:46 [server-m26-check] stage: rank exit in 3.7ms out=[gaps=22]
info 00:32:46 [server-m26-check] stage: pause enter
info 00:32:46 [server-m26-check] stage: pause interrupt in 0.0ms
Deserializing unregistered type skill_gap_agent.ranking.Gap from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.ranking', 'Gap')]
info 00:32:46 [server-m26-check] stage: pause enter
info 00:32:46 [server-m26-check] stage: pause exit in 0.0ms out=[phase_resumed=True]
info 00:32:46 [server-m26-check] stage: synthesize enter
info 00:32:46 [server-m26-check] stage: synthesize exit in 0.0ms out=[projects=0]
info 00:32:46 [server-m26-check] stage: oss enter
info 00:32:46 [server-m26-check] stage: oss exit in 0.0ms out=[oss_by_gap={} degraded_reasons=0]
info 00:32:46 [server-m26-check] stage: output enter
info 00:32:46 [server-m26-check] stage: output exit in 7.3ms out=[]

```
