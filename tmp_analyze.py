import json
import re

LOG = r"c:\Users\singh\AppData\Roaming\Code\agentSessionData\5a7b0421-1f58-476d-a577-04666e09670c\attachments\177ac0d3-b45c-4c47-a360-3248b829ea76\Untitled-1.txt"
PROF = r"C:\Users\singh\Documents\personal\learning\projects\skill-gap-agent\output\sessions\c5b8a013f7d8f82c909cf10bfc25d804ed8da46ca27866348ac322b6999d6d60\profile.json"

log = open(LOG, encoding="utf-8", errors="replace").read()
ans = re.findall(r'POST /api/intake/answer HTTP/1\.1" (\d+)', log)
print("answer responses:", len(ans), "->", {c: ans.count(c) for c in set(ans)})
print("sequence:", "".join("F" if c == "400" else "." for c in ans))

p = json.load(open(PROF, encoding="utf-8-sig"))
print("proficiency count:", len(p.get("proficiency", {})))
print("progress keys:", len(p.get("progress", {})))
print("depth count:", len(p.get("depth", {})))
print("implied count:", len(p.get("implied", {})))
print("phrases count:", len(p.get("phrases", {})))
print("updated_at:", p.get("updated_at"))
