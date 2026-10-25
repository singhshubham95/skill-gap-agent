# Verification report — T-M29-desktop-launcher
Run: 2026-10-26 00:36:54

## PASS — `.venv\Scripts\python.exe -m ruff check .`

```
All checks passed!

```

## PASS — `.venv\Scripts\python.exe -m pytest -q`

```
...................................................................      [100%]
67 passed in 16.13s

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m29_check`

```
version OK: 0.1.0; release URL set; store URL gated
paths OK: frozen LocalAppData, dev output/, env override + mkdir
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
[desktop 2026-10-26 00:36:48] local agent listening on http://127.0.0.1:57893/
[desktop 2026-10-26 00:36:49] local agent stopped
[desktop 2026-10-26 00:36:49] local agent listening on http://127.0.0.1:57895/
[desktop 2026-10-26 00:36:49] local agent stopped

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m13_check`

```
- Python programming experience (0.50)
   0.50    1  partial       Data pipelines            <- Python programming experience (0.50)
   0.50    1  partial       Streaming data            <- Python programming experience (0.50)
Gaps written: C:\Users\singh\AppData\Local\Temp\sg-m13-juxwic1y\gaps.json
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/gaps HTTP/1.1&quot; 200 -
gaps OK: 3 ranked (Data governance, Data pipelines, Streaming data)
[m11] &quot;POST /api/run HTTP/1.1&quot; 202 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -

Plan written: C:\Users\singh\AppData\Local\Temp\sg-m13-juxwic1y\plan.md
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

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m26_check`

```
M call failed (non-transient, not retried): Error 400
info 00:36:53 [-] req: POST /api/run received
info 00:36:53 [server-1792955213246848900] run: start phase=full mode=paid llm=False provider=openrouter free_tier=False model=- options={top_n=3,use_llm=False}
info 00:36:53 [server-1792955213246848900] req: POST /api/run -> 202 in 0.6ms
info 00:36:53 [server-1792955213246848900] req: GET /api/status received
info 00:36:53 [server-1792955213246848900] req: GET /api/status -> 200 in 0.2ms
info 00:36:53 [server-m26-check] stage: ingest enter
info 00:36:53 [server-m26-check] stage: ingest exit in 87.8ms out=[stats={5 keys}]
info 00:36:53 [server-m26-check] stage: judge enter
info 00:36:53 [server-m26-check] stage: judge exit in 3.0ms out=[judged=False unjudged=21]
info 00:36:53 [server-m26-check] stage: gate enter
info 00:36:53 [server-m26-check] gate: overrides=22
info 00:36:53 [server-m26-check] stage: gate exit in 1.0ms out=[gate_decisions=0]
info 00:36:53 [server-m26-check] stage: rank enter
info 00:36:53 [server-m26-check] stage: rank exit in 3.8ms out=[gaps=22]
info 00:36:53 [server-m26-check] stage: pause enter
info 00:36:53 [server-m26-check] stage: pause interrupt in 0.0ms
Deserializing unregistered type skill_gap_agent.ranking.Gap from checkpoint. This will be blocked in a future version. Set LANGGRAPH_STRICT_MSGPACK=true to block now, or add to allowed_msgpack_modules to allow explicitly: [('skill_gap_agent.ranking', 'Gap')]
info 00:36:53 [server-m26-check] stage: pause enter
info 00:36:53 [server-m26-check] stage: pause exit in 0.0ms out=[phase_resumed=True]
info 00:36:53 [server-m26-check] stage: synthesize enter
info 00:36:53 [server-m26-check] stage: synthesize exit in 0.0ms out=[projects=0]
info 00:36:53 [server-m26-check] stage: oss enter
info 00:36:53 [server-m26-check] stage: oss exit in 0.7ms out=[oss_by_gap={} degraded_reasons=0]
info 00:36:53 [server-m26-check] stage: output enter
info 00:36:54 [server-m26-check] stage: output exit in 8.6ms out=[]

```
