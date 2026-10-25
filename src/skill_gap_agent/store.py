"""Central artifact store: one workspace, no per-input session folders.

The extension is a single-user surface, so the product keeps exactly one
current session on disk:

    output/                      <- THE current session; every stage reads
    ├── current.json               and writes here (no source-keyed dirs)
    ├── extracted_skills.json + .sha256
    ├── profile.json               # chat product: phrase review, implied,
    ├── questions.json             #   depth/intent, proficiency grades
    ├── graph.json, judge_report.json, gaps.json
    ├── plan.md, plan.html, synthesis_report.json, oss_issues.json
    ├── uploads/                   # the current resume (replaced on upload)
    └── captured_jds/              # the current JD set

Saved sessions are explicit user snapshots under output/saved_sessions/<name>/
— the only other directory any code touches, and only via save/load/list.

Two invariants replace the old SHA-keyed directory scheme:

1. **One location.** `current_dir()` is the sole artifact root; stages never
   take a destination argument.
2. **The resume identity still guards reuse.** A profile/extraction cache is
   reusable only when its recorded `source_sha256` matches the current
   resume (see `intake.load_or_create_profile` and
   `resume.load_extracted`). Flattening the folder must NOT flatten that
   check — reuse across different resumes would feed one person's depth
   answers into another's judge prompt.

`SKILL_GAP_DATA_DIR` redirects the store at a scratch directory so
validation runs never touch real data (the incident behind the old
`SKILL_GAP_SESSIONS_DIR`).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path

OUTPUT_ROOT = Path("output")
DATA_DIR_ENV = "SKILL_GAP_DATA_DIR"
SAVED_DIR_NAME = "saved_sessions"

# Retired global decision files (pre-M9). Migration deletes them; no flow
# creates or reads them again.
LEGACY_FILES = (
    "extracted_approvals.json",
    "implied_skills.json",
    "gate_overrides.json",
)

# The LLM judgment caches: what lets a re-run skip LLM work.
JUDGMENT_CACHE_FILES = ("graph.json", "judge_report.json", "questions.json")

# Everything that belongs to the analysis, i.e. what "delete everything"
# removes and what a saved session captures. `logs/`, `sweeps/` and
# `saved_sessions/` are deliberately absent — they are not session state.
ARTIFACT_FILES = (
    "current.json",
    "profile.json",
    "questions.json",
    "extracted_skills.json",
    "extracted_skills.sha256",
    "extracted_skills.reviewed.json",
    "graph.json",
    "judge_report.json",
    "gaps.json",
    "synthesis_report.json",
    "oss_issues.json",
    "plan.md",
    "plan.html",
)
ARTIFACT_DIRS = ("captured_jds", "uploads")


def data_root() -> Path:
    """Effective store root: env override (validation isolation) first."""
    override = os.environ.get(DATA_DIR_ENV)
    return Path(override) if override else OUTPUT_ROOT


def current_dir(create: bool = False) -> Path:
    """The current session directory — the only artifact root."""
    d = data_root()
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def captured_jds_dir(create: bool = False) -> Path:
    d = current_dir() / "captured_jds"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def uploads_dir(create: bool = False) -> Path:
    d = current_dir() / "uploads"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def source_sha(path: str | Path) -> str:
    """SHA-256 of a skills source file — the resume identity (reuse guard)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Manifest — which resume the current workspace belongs to
# ---------------------------------------------------------------------------


def _manifest_path() -> Path:
    return current_dir() / "current.json"


def read_manifest() -> dict:
    """The current-session manifest, or {} when the workspace is empty."""
    p = _manifest_path()
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def write_manifest(**fields) -> dict:
    """Merge fields into the manifest (survives a server restart)."""
    data = read_manifest()
    data.update(fields)
    data["updated_at"] = datetime.now(UTC).isoformat()
    current_dir(create=True)
    _manifest_path().write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return data


def current_resume() -> dict:
    """{filename, sha256, mode, provider} for the manifest's resume, or {}."""
    resume = read_manifest().get("resume")
    return resume if isinstance(resume, dict) else {}


def clear_manifest() -> None:
    p = _manifest_path()
    if p.exists():
        p.unlink()


# ---------------------------------------------------------------------------
# Profile + judgment caches
# ---------------------------------------------------------------------------


def profile_path() -> Path:
    return current_dir() / "profile.json"


def questions_path() -> Path:
    return current_dir() / "questions.json"


def load_profile() -> dict | None:
    """Load the chat profile, or None if no chat ran yet."""
    p = profile_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_profile(profile: dict) -> Path:
    p = profile_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return p


def clear_judgment_cache() -> list[str]:
    """Delete the LLM judgment caches; return the removed names.

    Clears exactly what lets a re-run skip or replay LLM work: `graph.json`
    (judge TRANSFERS_TO edges), `judge_report.json` (merged judge rows) and
    `questions.json` (validation question cache). Chat answers, captured JDs
    and extraction artifacts survive — clearing is not a reset.
    """
    removed: list[str] = []
    for name in JUDGMENT_CACHE_FILES:
        p = current_dir() / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return removed


def invalidate_on_resume_change() -> list[str]:
    """Drop everything derived from the *previous* resume.

    Called when an upload changes the current resume. Chat answers, the
    extraction artifact, the judgment caches and the rendered analysis all
    cite the old resume, so keeping any of them would either apply one
    profile's depth/decisions to another or serve a plan that describes a
    resume the user no longer has. Captured JDs are the user's JD list, not
    resume-derived, so they stay. `oss_issues.json` also stays: it caches
    GitHub issues keyed by gap target, which is resume-independent.
    """
    removed: list[str] = []
    for name in (
        "profile.json",
        "questions.json",
        "extracted_skills.json",
        "extracted_skills.sha256",
        "extracted_skills.reviewed.json",
        *JUDGMENT_CACHE_FILES,
        "gaps.json",
        "plan.md",
        "plan.html",
        "synthesis_report.json",
    ):
        p = current_dir() / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return removed


def clear_uploads(keep: str | None = None) -> list[str]:
    """Delete uploaded resumes, optionally keeping one file name.

    The workspace holds exactly one current resume, so a replacement must
    remove the previous file — otherwise the folder accumulates every resume
    the user ever uploaded and "delete everything" cannot honour its promise.
    """
    d = uploads_dir()
    removed: list[str] = []
    if not d.exists():
        return removed
    for f in sorted(d.iterdir()):
        if f.is_file() and f.name != keep:
            f.unlink()
            removed.append(f.name)
    return removed


def ensure_resume_identity(source: str | Path, **manifest_fields) -> dict:
    """Bind the workspace to `source`, invalidating a previous resume's state.

    The single chokepoint that replaces per-SHA session folders: whenever a
    run starts, the workspace either already belongs to this resume (caches
    honored) or is cleared of resume-derived artifacts first. Without this
    step, flattening the store would feed one resume's depth answers and
    judge scores into another's run.

    Returns {"changed": bool, "removed": [names]}.
    """
    path = Path(source)
    try:
        sha = source_sha(path)
    except OSError:
        # Unreadable/missing source: nothing to bind, leave state alone.
        return {"changed": False, "removed": []}
    previous = current_resume().get("sha256")
    changed = bool(previous) and previous != sha
    removed = invalidate_on_resume_change() if changed else []
    write_manifest(
        resume={
            "filename": path.name,
            "path": str(path),
            "sha256": sha,
            **{k: v for k, v in manifest_fields.items() if v is not None},
        },
        schema=1,
    )
    return {"changed": changed, "removed": removed}


# ---------------------------------------------------------------------------
# Clearing
# ---------------------------------------------------------------------------


def clear_captured_jds() -> list[str]:
    """Delete the current JD set. Returns the removed file names."""
    d = captured_jds_dir()
    removed: list[str] = []
    if not d.exists():
        return removed
    for f in sorted(d.iterdir()):
        if f.is_file():
            f.unlink()
            removed.append(f.name)
    return removed


def clear_all() -> list[str]:
    """Delete every artifact of the current session; return removed names.

    Keeps the directory itself, and never touches `logs/`, `sweeps/` or
    `saved_sessions/` — those are not session artifacts.
    """
    removed: list[str] = []
    root = current_dir()
    for name in ARTIFACT_FILES:
        p = root / name
        if p.exists():
            p.unlink()
            removed.append(name)
    for name in ARTIFACT_DIRS:
        d = root / name
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.is_file():
                    f.unlink()
                    removed.append(f"{name}/{f.name}")
    return removed


def retire_legacy_files() -> list[str]:
    """Migration: delete the pre-M9 retired global files."""
    removed: list[str] = []
    root = current_dir()
    for name in LEGACY_FILES:
        p = root / name
        if p.exists():
            p.unlink()
            removed.append(name)
    return removed


# ---------------------------------------------------------------------------
# Saved sessions (explicit user snapshots)
# ---------------------------------------------------------------------------

_NAME_RE = re.compile(r"[^A-Za-z0-9._ -]+")


def saved_root() -> Path:
    return data_root() / SAVED_DIR_NAME


def safe_session_name(name: str) -> str:
    """Sanitize a user-chosen session name into a directory-safe stem.

    The name becomes a directory name, so separators, traversal and hidden
    names are stripped before any filesystem call.
    """
    cleaned = _NAME_RE.sub("_", Path(str(name).replace("\\", "/")).name).strip(" .")
    return cleaned[:80]


def saved_session_dir(name: str) -> Path:
    """Path of a saved session (validates the name; never escapes the root)."""
    cleaned = safe_session_name(name)
    if not cleaned or cleaned in (".", ".."):
        raise ValueError("invalid session name")
    return saved_root() / cleaned


def list_saved() -> list[dict]:
    """Saved sessions, newest first: [{name, saved_at, has_resume, jds}]."""
    root = saved_root()
    if not root.exists():
        return []
    out: list[dict] = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        manifest: dict = {}
        try:
            manifest = json.loads((d / "current.json").read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            manifest = {}
        jd_dir = d / "captured_jds"
        out.append({
            "name": d.name,
            "saved_at": manifest.get("saved_at") or manifest.get("updated_at"),
            "has_resume": bool(manifest.get("resume")),
            "jds": len([f for f in jd_dir.iterdir() if f.is_file()])
            if jd_dir.exists() else 0,
        })
    return sorted(out, key=lambda s: s.get("saved_at") or "", reverse=True)


def save_session(name: str) -> dict:
    """Snapshot the current session under a user-chosen name.

    Copies artifacts + the resume + the captured JDs (a restorable snapshot).
    Re-saving the same name replaces it.
    """
    dest = saved_session_dir(name)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    root = current_dir()
    for filename in ARTIFACT_FILES:
        src = root / filename
        if src.is_file():
            shutil.copy2(src, dest / filename)
    for dirname in ARTIFACT_DIRS:
        src = root / dirname
        if src.is_dir():
            shutil.copytree(src, dest / dirname)
    manifest = json.loads((dest / "current.json").read_text(encoding="utf-8")) \
        if (dest / "current.json").exists() else {}
    manifest["saved_at"] = datetime.now(UTC).isoformat()
    manifest["name"] = dest.name
    (dest / "current.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"name": dest.name, "saved_at": manifest["saved_at"]}


def load_session(name: str) -> dict:
    """Replace the current session with a saved snapshot.

    Clears the current artifacts first, then copies the snapshot in, so no
    file from the workspace it replaces can survive into the loaded session.
    """
    src = saved_session_dir(name)
    if not src.is_dir():
        raise FileNotFoundError(f"no saved session named {name!r}")
    root = current_dir(create=True)
    clear_all()
    copied = 0
    for filename in ARTIFACT_FILES:
        s = src / filename
        if s.is_file():
            shutil.copy2(s, root / filename)
            copied += 1
    for dirname in ARTIFACT_DIRS:
        s = src / dirname
        if s.is_dir():
            shutil.copytree(s, root / dirname, dirs_exist_ok=True)
            copied += 1
    return {"name": src.name, "loaded": copied}


def delete_saved(name: str) -> bool:
    """Delete a saved snapshot. Returns True when something was removed."""
    d = saved_session_dir(name)
    if not d.is_dir():
        return False
    shutil.rmtree(d)
    return True
