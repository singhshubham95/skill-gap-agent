# Verification report — T-M29-installer-ci
Run: 2026-10-31 23:39:48

## PASS — `.venv\Scripts\python.exe -m ruff check .`

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
collected 69 items

src\skill_gap_agent\test_m13.py ...                                      [  4%]
src\skill_gap_agent\test_m14.py ....                                     [ 10%]
src\skill_gap_agent\test_m15.py .....                                    [ 17%]
src\skill_gap_agent\test_m16.py .........                                [ 30%]
src\skill_gap_agent\test_m18.py ...                                      [ 34%]
src\skill_gap_agent\test_m19.py ..                                       [ 37%]
src\skill_gap_agent\test_m20.py ....                                     [ 43%]
src\skill_gap_agent\test_m21.py ....                                     [ 49%]
src\skill_gap_agent\test_m22.py ....                                     [ 55%]
src\skill_gap_agent\test_m23.py ....                                     [ 60%]
src\skill_gap_agent\test_m24.py ...                                      [ 65%]
src\skill_gap_agent\test_m26.py .......                                  [ 75%]
src\skill_gap_agent\test_m29.py ...........                              [ 91%]
src\skill_gap_agent\test_m9.py ......                                    [100%]

============================= 69 passed in 14.89s =============================

```

## PASS — `node --check extension/sidepanel.js`

```

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m29_check`

```
version OK: 0.1.0; release URL set; store URL gated
paths OK: frozen LocalAppData, dev output/, env override + mkdir
resource defaults OK: dataset + JDs exist, _MEIPASS wins when frozen, spec bundles data/
frozen workdir OK: runs from the data root, not the install dir
imports OK: no top-level tray/GUI imports
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
status OK: /api/status carries app_version without changing state
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
backend OK: start -> status -> restart -> stop
port error OK: OSError propagates and no server is left running
single instance OK: second acquire refused, release frees the name
startup toggle OK: write/read/remove under a throwaway HKCU key
output redirect OK: windowed-build prints land in desktop.log
M29 launcher checks OK
[desktop 2026-10-31 23:39:40] local agent listening on http://127.0.0.1:62250/
[desktop 2026-10-31 23:39:40] local agent stopped
[desktop 2026-10-31 23:39:40] local agent listening on http://127.0.0.1:62252/
[desktop 2026-10-31 23:39:41] local agent stopped

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m13_check`

```
- Python programming experience (0.50)
   0.50    1  partial       Data pipelines            <- Python programming experience (0.50)
   0.50    1  partial       Streaming data            <- Python programming experience (0.50)
Gaps written: C:\Users\singh\AppData\Local\Temp\sg-m13-dqqr7zxf\gaps.json
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/gaps HTTP/1.1&quot; 200 -
gaps OK: 3 ranked (Data governance, Data pipelines, Streaming data)
[m11] &quot;POST /api/run HTTP/1.1&quot; 202 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -

Plan written: C:\Users\singh\AppData\Local\Temp\sg-m13-dqqr7zxf\plan.md
Graph saved: 9 nodes, 9 edges
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /plan.html HTTP/1.1&quot; 200 -
link policy OK: 5 links target new tabs
[m11] &quot;GET /jds/Governance_Analyst.txt HTTP/1.1&quot; 200 -
[m11] &quot;GET /jds/no_such_jd.txt HTTP/1.1&quot; 404 -
jd viewer OK: captured JDs served from the workspace
plan OK: projects + Good-First-Issues rendered
[m11] &quot;POST /api/run HTTP/1.1&quot; 409 -
guard OK: second phase 'plan' rejected with 409
M13 CHECK PASS: cli wiring + manifest + two-phase gaps/plan flow OK.
Deserializing unregistered type skill_gap_agent.ranking.Gap from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.ranking', 'Gap')]
Deserializing unregistered type skill_gap_agent.synthesis.SynthesizedProject from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.synthesis', 'SynthesizedProject')]
Deserializing unregistered type skill_gap_agent.oss.OssIssue from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.oss', 'OssIssue')]

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

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m20_check`

```
[m11] &quot;GET /api/status HTTP/1.1&quot; 403 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 403 -
[m11] &quot;POST /api/oauth/state HTTP/1.1&quot; 403 -
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
[m11] &quot;POST /api/resume HTTP/1.1&quot; 415 -
content-type OK: text/plain POST + wrong resume type refused
[m11] &quot;POST /api/run HTTP/1.1&quot; 400 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;POST /api/run HTTP/1.1&quot; 400 -
skills_path containment OK: outside-repo and non-json refused
panel transport rule OK: normalizeServer + loadState validation
m20_check: PASS

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m22_check`

```
icons OK: 3 sizes, valid PNGs, manifest + action wired
policy OK: Limited Use statement, named destinations, landing link
register OK: every manifest permission/host justified, disclaimers present
links OK: no stale references in the derived registers
m22_check: PASS

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m26_check`

```
M call failed (non-transient, not retried): Error 400
info 23:39:47 [-] req: POST /api/run received
info 23:39:47 [server-1793470187544752500] run: start phase=full mode=paid llm=False provider=openrouter free_tier=False model=- options={top_n=3,use_llm=False}
info 23:39:47 [server-1793470187544752500] req: POST /api/run -> 202 in 0.5ms
info 23:39:47 [server-1793470187544752500] req: GET /api/status received
info 23:39:47 [server-1793470187544752500] req: GET /api/status -> 200 in 0.3ms
info 23:39:48 [server-m26-check] stage: ingest enter
info 23:39:48 [server-m26-check] stage: ingest exit in 76.0ms out=[stats={5 keys}]
info 23:39:48 [server-m26-check] stage: judge enter
info 23:39:48 [server-m26-check] stage: judge exit in 2.2ms out=[judged=False unjudged=21]
info 23:39:48 [server-m26-check] stage: gate enter
info 23:39:48 [server-m26-check] gate: overrides=22
info 23:39:48 [server-m26-check] stage: gate exit in 1.6ms out=[gate_decisions=0]
info 23:39:48 [server-m26-check] stage: rank enter
info 23:39:48 [server-m26-check] stage: rank exit in 5.0ms out=[gaps=22]
info 23:39:48 [server-m26-check] stage: pause enter
info 23:39:48 [server-m26-check] stage: pause interrupt in 0.0ms
Deserializing unregistered type skill_gap_agent.ranking.Gap from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.ranking', 'Gap')]
info 23:39:48 [server-m26-check] stage: pause enter
info 23:39:48 [server-m26-check] stage: pause exit in 0.0ms out=[phase_resumed=True]
info 23:39:48 [server-m26-check] stage: synthesize enter
info 23:39:48 [server-m26-check] stage: synthesize exit in 0.0ms out=[projects=0]
info 23:39:48 [server-m26-check] stage: oss enter
info 23:39:48 [server-m26-check] stage: oss exit in 0.4ms out=[oss_by_gap={} degraded_reasons=0]
info 23:39:48 [server-m26-check] stage: output enter
info 23:39:48 [server-m26-check] stage: output exit in 8.2ms out=[]

```
