"""Path guard: enforce a task's declared scope on its branch's changed files.

Usage:
  python scripts/path_guard.py --task T-16         # local pre-flight
  python scripts/path_guard.py --base origin/main  # task inferred from branch

Branch naming is the unit-of-work signal:
  req/T-*  -> one end-to-end agent working one functional requirement

In the simplified single-agent model the same agent plans, implements and
reviews, so there are no per-role write rules to enforce. What MUST be
enforced is scope: an agent may only change files its task declared in
"Files to touch" (plus board/, which is the shared append-only channel).
This is the deterministic guarantee that parallel agents on different
functional requirements never touch each other's files.

This is deterministic enforcement — prompt rules alone are not enforcement.
CI runs it on every push/PR via workflows/agent-gates.yml.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from locks_common import repo_root

# Always allowed regardless of scope: the shared coordination channel.
ALWAYS_ALLOWED = ("board/",)

# Task files are the work orders; scope is parsed from their "Files to touch".
TASKS_DIR = Path("specs/tasks")

# Generated / vendored noise never counts as a scope change. These should
# normally be gitignored too; skipping them keeps the guard's signal clean.
IGNORE_PREFIXES = ("__pycache__/", "node_modules/", ".venv/", "venv/",
                   ".git/", ".ruff_cache/", ".pytest_cache/", ".mypy_cache/")
IGNORE_SUFFIXES = (".pyc", ".pyo", ".egg-info")


def infer_task(branch: str) -> str | None:
    if branch.startswith("req/"):
        return branch[len("req/"):]
    return None


def task_file(task: str) -> Path:
    return repo_root() / TASKS_DIR / f"{task}.md"


def parse_scope(task: str) -> list[str] | None:
    """Extract backtick-quoted paths under the 'Files to touch' heading.

    Returns None if the task file or the section cannot be found — the guard
    then fails closed rather than silently allowing everything.
    """
    f = task_file(task)
    if not f.exists():
        return None
    text = f.read_text(encoding="utf-8")
    # Grab the "Files to touch" section up to the next heading.
    m = re.search(
        r"^#+\s*Files to touch.*?$(.*?)(?=^#+\s|\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    if not m:
        return None
    section = m.group(1)
    paths = re.findall(r"`([^`]+)`", section)
    return [p.strip() for p in paths if p.strip()]


def ignored(f: str) -> bool:
    if f.startswith(IGNORE_PREFIXES):
        return True
    return any(f.endswith(s) for s in IGNORE_SUFFIXES)


def changed_files(base: str | None) -> list[str]:
    files: set[str] = set()
    if base:
        out = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            capture_output=True, text=True, check=False)
        files.update(out.stdout.split())
    # --untracked-files=all: without it, git collapses untracked files to
    # their top-level dir ("src/"), which breaks per-file scope matching.
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"],
                         capture_output=True, text=True, check=False)
    for line in out.stdout.splitlines():
        if not line.strip():
            continue
        # Porcelain v1: "XY PATH" or "XY OLD -> NEW" (rename).
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path:
            files.add(path)
    return sorted(f for f in files if not ignored(f))


def in_scope(f: str, scope: list[str]) -> bool:
    for s in scope:
        s = s.rstrip("/")
        if f == s or f.startswith(s + "/"):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", help="task id, e.g. T-16")
    ap.add_argument("--base", help="git ref to diff against (e.g. origin/main)")
    args = ap.parse_args()

    task = args.task
    if not task:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, check=False).stdout.strip()
        task = infer_task(branch)
        if not task:
            # Human territory: task rules bind agents, not the human.
            print(f"no req/ prefix on branch '{branch}' (human) — "
                  "skipping task scope checks")
            return 0

    scope = parse_scope(task)
    if scope is None:
        print(f"SCOPE GUARD ERROR: could not read 'Files to touch' from "
              f"{task_file(task).relative_to(repo_root())} — failing closed")
        return 1

    allowed = list(ALWAYS_ALLOWED) + scope
    violations = []
    for f in changed_files(args.base):
        if f == task_file(task).relative_to(repo_root()).as_posix():
            continue  # the work order itself is always editable
        if f == "docs/changelog.md":
            continue  # the closing changelog line
        if any(f == a or f.startswith(a) for a in ALWAYS_ALLOWED):
            continue
        if not in_scope(f, scope):
            violations.append(f)

    if violations:
        print(f"SCOPE GUARD VIOLATION ({task}): these files are outside the "
              f"task's 'Files to touch':")
        for f in violations:
            print(f"  {f}")
        print(f"declared scope: {', '.join(scope) or '(empty)'}")
        return 1
    print(f"scope guard OK ({task}) — {len(allowed)} allowed path(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
