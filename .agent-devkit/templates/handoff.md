# Handoff contract (session-chaining)

Each pipeline stage ends by spawning the next session. The spawn call must
carry, in the prompt, exactly this information (adapt role/model per
`.agent-devkit/config/model-chains.yaml`):

## Planner → implementer

```text
ROLE: implementer. Read .agent-devkit/roles/implementer.md and follow it.
TASK: specs/tasks/T-<id>.md  (work order — scope, files, acceptance)
SPEC: the component spec sections linked in the task file (the HOW)
BRANCH: impl/T-<id>   WORKTREE: <path or "same repo">
LOCKS: claim the task's files before editing:
       python scripts/claim.py --role implementer --task T-<id> <files>
VERIFY: python scripts/verify.py --task T-<id>   (must pass before handoff)
ISSUES: ambiguity -> board/issues/ + message the planner session <URI>
END BY: spawning the reviewer with the reviewer handoff below.
```

## Implementer → reviewer

```text
ROLE: reviewer. Read .agent-devkit/roles/reviewer.md and follow it.
TASK: specs/tasks/T-<id>.md
DIFF: branch impl/T-<id>  (compare against the task's spec sections)
CHECK: acceptance criteria met, spec-compliant, listed tests present and
       passing (board/verify-T-<id>.md), no out-of-scope changes.
OUTPUT: review note in board/ (approve | violations with file/line refs).
ON APPROVAL: message the planner session <URI> to write the changelog line.
SPEC DEFECT: board/issues/ + message the planner session; do not reject.
```

## Reviewer / implementer → planner (issue or approval)

```text
TO: planner session <URI recorded in the task file>
MESSAGE: task T-<id> — <approved | issue board/issues/I-<id>.md>.
Resume the same planner session; do not spawn a new one (it holds the
design context). If that session is gone, spawn a fresh planner with the
task file + issue file paths and the planner role file.
```

Rules: the spawn call sets the **model explicitly** (never inherits); every
message that changes state also leaves a durable file record in `board/`
(the message is the doorbell, the file is the record).
