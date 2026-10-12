"""Session store: every run artifact tied to its skills source (M9).

Generalizes the M14 extraction sidecar to the whole store. A session is
keyed by the SHA-256 of the skills source file (uploaded resume or skills
JSON):

    output/sessions/<sha256>/
    ├── extracted_skills.json + .sha256   # M14 rules, in-session
    ├── profile.json                      # chat product: phrase review,
    │                                     #   implied decisions, depth/intent,
    │                                     #   proficiency grades
    ├── questions.json                    # validation question cache (by skill)
    ├── captured_jds/                     # this session's captured JDs
    ├── graph.json, judge_report.json, gaps.json
    └── plan.md, plan.html, synthesis_report.json, oss_issues.json

Same input re-uploaded -> the same session resumes (stamped caches honored
per the depth rules in judge.py); different input -> a fresh session.
Cross-profile misapplication is structurally impossible.

The legacy global files are RETIRED (decision rows 2026-10-12): no flow
creates or reads output/extracted_approvals.json, output/implied_skills.json,
output/gate_overrides.json, or the global output/extracted_skills.json.
`retire_legacy_files()` deletes them (migration) and m9_check asserts they
stay gone.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

SESSIONS_ROOT = Path("output/sessions")

# The retired global decision files (never created/read again anywhere).
LEGACY_FILES = (
    "extracted_approvals.json",
    "implied_skills.json",
    "gate_overrides.json",
    "extracted_skills.json",
    "extracted_skills.sha256",
    "extracted_skills.reviewed.json",
)


def source_sha(path: str | Path) -> str:
    """SHA-256 of the skills source file — the session key (M14 pattern)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def session_dir(source: str | Path, create: bool = False) -> Path:
    """Session directory for a skills source (keyed by the file's SHA-256)."""
    key = source if isinstance(source, str) and len(source) == 64 and "/" not in source and "\\" not in source else source_sha(source)
    d = SESSIONS_ROOT / key
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def profile_path(source: str | Path) -> Path:
    return session_dir(source) / "profile.json"


def questions_path(source: str | Path) -> Path:
    return session_dir(source) / "questions.json"


def captured_jds_dir(source: str | Path, create: bool = False) -> Path:
    d = session_dir(source) / "captured_jds"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def retire_legacy_files(output_dir: str | Path = "output") -> list[str]:
    """Migration: delete the retired global files. Returns removed names."""
    removed: list[str] = []
    out = Path(output_dir)
    for name in LEGACY_FILES:
        p = out / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return removed


def load_profile(source: str | Path) -> dict | None:
    """Load the session profile (chat product), or None if no chat ran yet."""
    p = profile_path(source)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_profile(source: str | Path, profile: dict) -> Path:
    p = profile_path(source)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return p
