"""Run verification commands and write a pass/fail report to board/.

Usage: python scripts/verify.py --task T-16 [--checks "ruff check .,pytest"]

The test suite is the real gate of the pipeline: reviewers check spec
compliance, this script checks mechanical correctness. Exit code is
non-zero if any check fails.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time

from locks_common import repo_root


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--task", required=True)
    ap.add_argument("--checks", default="ruff check .,pytest")
    args = ap.parse_args()

    root = repo_root()
    checks = [c.strip() for c in args.checks.split(",") if c.strip()]
    results = []
    for check in checks:
        print(f"running: {check}")
        proc = subprocess.run(check, shell=True, cwd=root,
                              capture_output=True, text=True, check=False)
        tail = (proc.stdout + proc.stderr)[-2000:]
        ok = proc.returncode == 0
        results.append((check, ok, tail))
        print(f"  {'PASS' if ok else 'FAIL'}")

    lines = [
        f"# Verification report — {args.task}",
        f"Run: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for check, ok, tail in results:
        lines += [f"## {'PASS' if ok else 'FAIL'} — `{check}`", "", "```", tail, "```", ""]
    report = root / "board" / f"verify-{args.task}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")

    failed = [c for c, ok, _ in results if not ok]
    print(f"report: {report.relative_to(root)}")
    if failed:
        print("FAILED: " + ", ".join(failed))
        return 1
    print("ALL CHECKS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
