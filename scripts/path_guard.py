"""Path guard: enforce per-role write rules on a branch's changed files.

Usage:
  python scripts/path_guard.py --role planner        # local pre-flight
  python scripts/path_guard.py --base origin/main    # role inferred from branch

Branch naming is the role signal:
  plan/T-*  -> may change only specs/, docs/, board/, .github/copilot-instructions.md
  impl/T-*  -> may change anything EXCEPT specs/ and docs/ (board/ allowed for issues)
  review/T-* -> may change only board/

This is the deterministic permission enforcement (prompt rules alone are
not enforcement). CI runs it on every push/PR via workflows/agent-gates.yml.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

RULES = {
    "planner": {
        "allow": ["specs/", "docs/", "board/", ".github/copilot-instructions.md"],
        "deny": [],
    },
    "implementer": {
        "allow": [],  # everything...
        "deny": ["specs/", "docs/"],  # ...except these
    },
    "reviewer": {
        "allow": ["board/"],
        "deny": [],
    },
}


def infer_role(branch: str) -> str | None:
    for prefix, role in [("plan/", "planner"), ("impl/", "implementer"),
                         ("review/", "reviewer")]:
        if branch.startswith(prefix):
            return role
    return None


def changed_files(base: str | None) -> list[str]:
    files: set[str] = set()
    if base:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True, text=True, check=False)
        files.update(out.stdout.split())
    out = subprocess.run(["git", "status", "--porcelain"],
                         capture_output=True, text=True, check=False)
    for line in out.stdout.splitlines():
        if line.strip():
            files.add(line[3:].strip().strip('"'))
    return sorted(files)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--role", choices=RULES)
    ap.add_argument("--base", help="git ref to diff against (e.g. origin/main)")
    args = ap.parse_args()

    role = args.role
    if not role:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=False).stdout.strip()
        role = infer_role(branch)
        if not role:
            # Human territory: role rules bind agents, not the human.
            print(f"no role prefix on branch '{branch}' (human) — "
                  "skipping role checks")
            return 0

    rules = RULES[role]
    violations = []
    for f in changed_files(args.base):
        denied = any(f == d or f.startswith(d) for d in rules["deny"])
        allowed = any(f == a or f.startswith(a) for a in rules["allow"])
        if denied or (rules["allow"] and not allowed):
            violations.append(f)

    if violations:
        print(f"PATH GUARD VIOLATION ({role}):")
        for f in violations:
            print(f"  {f}")
        return 1
    print(f"path guard OK ({role})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
