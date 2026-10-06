"""Release file locks held by a task.

Usage:
  python scripts/release.py --task T-16              # release all of T-16
  python scripts/release.py --task T-16 path [path]  # release specific paths

A task may only release its own locks. Always release on every exit path.
"""
from __future__ import annotations

import argparse
import sys

from locks_common import (
    lock_dir,
    log_event,
    normalize,
    read_owner,
    regenerate_board,
)


def release_one(path: str, task: str) -> str:
    d = lock_dir(path)
    owner = read_owner(d)
    if not owner:
        return f"skip (not locked): {path}"
    if owner.get("task") != task:
        return f"DENIED (owned by {owner.get('task')}): {path}"
    for f in d.iterdir():
        f.unlink()
    d.rmdir()
    log_event(f"RELEASE {task} -> {path}")
    return f"released: {path}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", required=True)
    ap.add_argument("paths", nargs="*",
                    help="paths to release; omit to release all of this task")
    args = ap.parse_args()

    paths = args.paths
    if not paths:
        # Find every lock owned by this task.
        from locks_common import LOCKS_DIR, repo_root
        locks = repo_root() / LOCKS_DIR
        paths = []
        if locks.exists():
            for d in locks.iterdir():
                owner = read_owner(d)
                if owner and owner.get("task") == args.task:
                    paths.append(owner.get("path", ""))

    denied = False
    for path in sorted(paths, key=normalize):
        msg = release_one(path, args.task)
        print(msg)
        denied = denied or msg.startswith("DENIED")
    regenerate_board()
    return 1 if denied else 0


if __name__ == "__main__":
    sys.exit(main())
