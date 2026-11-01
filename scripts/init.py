"""Install agent-devkit-simplified into a project.

Usage: python init.py --target /path/to/project

Copies:
  scripts/*.py              -> <target>/scripts/
  workflows/agent-gates.yml -> <target>/.github/workflows/
  roles/, templates/, config/ -> <target>/.agent-devkit/
Scaffolds:
  board/locks/, board/issues/, board/maintenance/, docs/, specs/tasks/,
  maintenance/
Seeds:
  docs/overview.md, docs/changelog.md, maintenance/README.md (only if missing)
Writes:
  devkit.version from the source checkout's git describe

Safe to re-run: kit files are overwritten; project-owned files are not.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
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


def kit_version() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(DEVKIT), "describe", "--tags", "--always", "--dirty"],
            capture_output=True, text=True, check=False,
        )
    except OSError:
        return "unversioned"
    version = out.stdout.strip()
    return version if out.returncode == 0 and version else "unversioned"


def write_version(target: Path, version: str) -> str:
    dst = target / "devkit.version"
    old = dst.read_text(encoding="utf-8").strip() if dst.exists() else "(none)"
    if version == "unversioned" and dst.exists():
        return f"{old} (source unversioned; kept existing pin)"
    dst.write_text(f"agent-devkit-simplified@{version}\n", encoding="utf-8")
    return f"{old} -> agent-devkit-simplified@{version}"


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
                 target / "board" / "maintenance", target / "docs",
                 target / "specs" / "tasks"):
        keep.mkdir(parents=True, exist_ok=True)
        (keep / ".gitkeep").touch()
    (target / "maintenance").mkdir(parents=True, exist_ok=True)
    # Seed project-owned files from templates only when missing.
    for doc in ("overview.md", "changelog.md"):
        dst = target / "docs" / doc
        if not dst.exists():
            shutil.copy2(DEVKIT / "templates" / doc, dst)
    charter = target / "maintenance" / "README.md"
    if not charter.exists():
        shutil.copy2(DEVKIT / "templates" / "maintenance.md", charter)

    version = kit_version()
    version_line = write_version(target, version)

    print(f"installed {n} devkit files into {target}")
    print(f"devkit.version: {version_line}")
    if version.endswith("-dirty"):
        print("warning: the devkit source has uncommitted changes; "
              "devkit.version is marked -dirty")
    print("next steps:")
    print("  1. commit the new files")
    print("  2. read .agent-devkit/roles/agent.md before starting a task")
    print("  3. review maintenance/README.md and set the maintenance cadence")
    return 0


if __name__ == "__main__":
    sys.exit(main())
