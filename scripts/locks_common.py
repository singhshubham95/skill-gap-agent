"""Shared lock-board helpers for the agent-devkit (copied into each project).

Lock model: board/locks/<sha1-of-normalized-path>/owner.json.
`mkdir` is atomic on all filesystems, so it is the claim primitive.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import time
from pathlib import Path

LOCKS_DIR = Path("board/locks")
BOARD_MD = Path("board/BOARD.md")
EVENTS_LOG = Path("board/lock-events.log")
STALE_MINUTES = 30  # auto-reclaim; matches config/model-chains.yaml


def repo_root() -> Path:
    """Walk up from cwd to the git root (fallback: cwd)."""
    p = Path.cwd()
    for cand in [p, *p.parents]:
        if (cand / ".git").exists():
            return cand
    return p


def normalize(path: str) -> str:
    """Stable, platform-independent identity for a path."""
    return os.path.normpath(path).replace("\\", "/")


def lock_dir(path: str) -> Path:
    h = hashlib.sha1(normalize(path).encode("utf-8")).hexdigest()[:16]
    return repo_root() / LOCKS_DIR / h


def default_agent() -> str:
    return os.environ.get("AGENT_SESSION", f"{socket.gethostname()}-{os.getpid()}")


def read_owner(d: Path) -> dict | None:
    try:
        return json.loads((d / "owner.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_owner(d: Path, owner: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "owner.json").write_text(json.dumps(owner, indent=2), encoding="utf-8")


def is_stale(owner: dict, stale_minutes: int) -> bool:
    try:
        since = float(owner.get("since", 0))
    except (TypeError, ValueError):
        return True
    return (time.time() - since) > stale_minutes * 60


def log_event(message: str) -> None:
    root = repo_root()
    (root / EVENTS_LOG).parent.mkdir(parents=True, exist_ok=True)
    with (root / EVENTS_LOG).open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def regenerate_board() -> None:
    """Rebuild board/BOARD.md (a view, not the source of truth)."""
    root = repo_root()
    locks = root / LOCKS_DIR
    rows = []
    if locks.exists():
        for d in sorted(locks.iterdir()):
            owner = read_owner(d)
            if not owner:
                continue
            age_min = (time.time() - float(owner.get("since", 0))) / 60
            stale = "STALE" if age_min > STALE_MINUTES else ""
            rows.append(
                f"| {owner.get('role', '?')} | {owner.get('task', '?')} "
                f"| {owner.get('path', '?')} | {owner.get('agent', '?')} "
                f"| {age_min:.0f}m | {stale} |"
            )
    lines = [
        "# Lock board (generated view — source of truth is board/locks/)",
        "",
        f"Updated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Role | Task | Path | Agent | Age | Stale |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        "Stale locks (>30 min) are auto-reclaimed on the next claim attempt;",
        "reclaims are logged to board/lock-events.log.",
        "",
    ]
    (root / BOARD_MD).write_text("\n".join(lines), encoding="utf-8")
