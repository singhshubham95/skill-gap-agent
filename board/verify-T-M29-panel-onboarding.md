# Verification report — T-M29-panel-onboarding
Run: 2026-10-26 01:16:17

## PASS — `.venv\Scripts\python.exe -m ruff check .`

```
All checks passed!

```

## PASS — `.venv\Scripts\python.exe -m pytest -q`

```
...................................................................      [100%]
67 passed in 16.81s

```

## PASS — `.venv\Scripts\python.exe -m skill_gap_agent.m13_check`

```
- Python programming experience (0.50)
   0.50    1  partial       Data pipelines            <- Python programming experience (0.50)
   0.50    1  partial       Streaming data            <- Python programming experience (0.50)
Gaps written: C:\Users\singh\AppData\Local\Temp\sg-m13-tpe3804z\gaps.json
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -
[m11] &quot;GET /api/gaps HTTP/1.1&quot; 200 -
gaps OK: 3 ranked (Data governance, Data pipelines, Streaming data)
[m11] &quot;POST /api/run HTTP/1.1&quot; 202 -
[m11] &quot;GET /api/status HTTP/1.1&quot; 200 -

Plan written: C:\Users\singh\AppData\Local\Temp\sg-m13-tpe3804z\plan.md
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
[desktop 2026-10-26 01:16:16] local agent listening on http://127.0.0.1:55347/
[desktop 2026-10-26 01:16:16] local agent stopped
[desktop 2026-10-26 01:16:16] local agent listening on http://127.0.0.1:55349/
[desktop 2026-10-26 01:16:17] local agent stopped

```

## PASS — `node --check extension/sidepanel.js`

```

```

## PASS — `node --check extension/content.js`

```

```
