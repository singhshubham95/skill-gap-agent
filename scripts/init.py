"""Install the agent-devkit into a project.

Usage: python init.py --target /path/to/project

Copies:
  scripts/*.py              -> <target>/scripts/
  workflows/agent-gates.yml -> <target>/.github/workflows/
  roles/, templates/, config/ -> <target>/.agent-devkit/
and scaffolds board/locks/, board/issues/, docs/ if missing.

Safe to re-run: it overwrites devkit files (review the diff if the devkit
version changed; projects pin their devkit version in devkit.version).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

DEVKIT = Path(__file__).resolve().parent.parent


def copy_dir(src: Path, dst: Path) -> int:
    n = 0
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file():
            shutil.copy2(f, dst / f.name)
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--target", required=True)
    args = ap.parse_args()
    target = Path(args.target).resolve()
    if not target.exists():
        print(f"target does not exist: {target}", file=sys.stderr)
        return 1

    n = copy_dir(DEVKIT / "scripts", target / "scripts")
    (target / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    shutil.copy2(DEVKIT / "workflows" / "agent-gates.yml",
                 target / ".github" / "workflows" / "agent-gates.yml")
    for sub in ("roles", "templates", "config"):
        n += copy_dir(DEVKIT / sub, target / ".agent-devkit" / sub)
    for keep in (target / "board" / "locks", target / "board" / "issues",
                 target / "docs", target / "specs" / "tasks"):
        keep.mkdir(parents=True, exist_ok=True)
        (keep / ".gitkeep").touch()
    print(f"installed {n} devkit files into {target}")
    print("next steps:")
    print("  1. commit the new files")
    print("  2. record the devkit version: git -C", DEVKIT, "rev-parse HEAD")
    print("  3. read .agent-devkit/roles/ before starting a pipeline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
