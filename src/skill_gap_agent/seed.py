"""Seed-data loading: skills JSON + JD text files into the SkillGraph.

Milestone 1: hand-loading for the schema smoke test. The automated
ingestion/target-ingestion nodes replace this in milestone 2.
"""

from __future__ import annotations

import json
from pathlib import Path

from .graph import JD, Skill, SkillGraph, SkillSource


def load_skills_json(sg: SkillGraph, path: str | Path) -> int:
    """Load a skills dump into Skill nodes + HAS_SKILL edges.

    Schema-flexible: accepts either a flat list of skill names, or a
    hierarchical dict/list where nested groupings are treated as categories.
    Returns the number of skills loaded.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    skills: list[tuple[str, str]] = []  # (name, category)

    def walk(obj, category: str = "uncategorized") -> None:
        if isinstance(obj, str):
            skills.append((obj, category))
        elif isinstance(obj, dict):
            for key, value in obj.items():
                walk(value, category=key)
        elif isinstance(obj, list):
            for item in obj:
                walk(item, category)

    walk(data)
    for name, category in skills:
        sg.add_skill(Skill(name=name, category=category, source=SkillSource.CURRENT))
        sg.add_has_skill(name)
    return len(skills)


def load_jds(sg: SkillGraph, jd_dir: str | Path) -> int:
    """Load JD text files (*.txt/*.md) from a directory as JD nodes.

    Skill extraction from JD text is milestone 2 (target-ingestion node);
    here we only register the JD nodes so the schema is exercised.
    Returns the number of JDs loaded.
    """
    jd_dir = Path(jd_dir)
    count = 0
    for f in sorted(jd_dir.iterdir()):
        if f.suffix.lower() in (".txt", ".md"):
            sg.add_jd(JD(title=f.stem, company="", raw_text_ref=str(f)))
            count += 1
    return count