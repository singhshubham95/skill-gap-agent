"""Claim file locks for a task. Atomic, deadlock-free, blocking-with-timeout.

Usage: python scripts/claim.py --role planner --task T-16 path [path...]

- Paths are claimed in sorted hash order (prevents deadlock between agents).
- Re-claiming a path already owned by the SAME task is idempotent.
- Locks older than --stale-min (default 30) are auto-reclaimed and logged.
- On timeout or failure, anything acquired in this call is released.
"""
from __future__ import annotations

import argparse
import sys
import time

from locks_common import (
    default_agent,
    is_stale,
    lock_dir,
    log_event,
    normalize,
    read_owner,
    regenerate_board,
    write_owner,
)


def claim_one(path: str, role: str, task: str, agent: str,
              stale_min: int, timeout: float, poll: float = 5.0) -> bool:
    d = lock_dir(path)
    deadline = time.time() + timeout
    while True:
        try:
            d.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            owner = read_owner(d) or {}
            if owner.get("task") == task and owner.get("role") == role:
                return True  # idempotent re-claim
            if is_stale(owner, stale_min):
                log_event(f"RECLAIM stale lock on {path} "
                          f"(was {owner.get('role')}/{owner.get('task')}) "
                          f"-> {role}/{task}")
                write_owner(d, {
                    "role": role, "task": task, "path": normalize(path),
                    "agent": agent, "since": time.time(),
                })
                return True
            if time.time() > deadline:
                return False
            time.sleep(poll)
        else:
            write_owner(d, {
                "role": role, "task": task, "path": normalize(path),
                "agent": agent, "since": time.time(),
            })
            log_event(f"CLAIM {role}/{task} -> {path}")
            return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--role", required=True)
    ap.add_argument("--task", required=True)
    ap.add_argument("--agent", default=default_agent())
    ap.add_argument("--stale-min", type=int, default=30)
    ap.add_argument("--timeout", type=float, default=3600.0,
                    help="seconds to block before giving up (default 3600)")
    ap.add_argument("paths", nargs="+")
    args = ap.parse_args()

    acquired: list[str] = []
    for path in sorted(args.paths, key=normalize):  # consistent order
        if claim_one(path, args.role, args.task, args.agent,
                     args.stale_min, args.timeout):
            acquired.append(path)
        else:
            for p in acquired:  # release everything taken in this call
                d = lock_dir(p)
                owner = read_owner(d)
                if owner and owner.get("task") == args.task:
                    for f in d.iterdir():
                        f.unlink()
                    d.rmdir()
            regenerate_board()
            print(f"TIMEOUT waiting for lock on {path} "
                  f"(claimed by another task); released {len(acquired)} "
                  f"lock(s) from this call", file=sys.stderr)
            return 1
    regenerate_board()
    print(f"claimed {len(acquired)} file(s) for {args.role}/{args.task}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
