"""External skill-taxonomy loader with graceful fallback.

v1 supports ESCO (open, EU-commissioned, ~3,000 ICT skills with preferred
labels + alternative labels). If the taxonomy file is absent, the pipeline
falls back to the built-in alias/pattern tables — never fails.

Data file (open item in specs/open-items.md): download the ESCO ICT skills
subset to data/taxonomy/esco_ict.json with shape:
  [{"id": "...", "preferred": "Apache Airflow", "alt": ["Airflow", ...],
    "broader": "orchestration tools", ...}]
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFAULT_TAXONOMY_PATH = Path("data/taxonomy/esco_ict.json")


class SkillTaxonomy:
    """Wrapper over an external skill taxonomy (ESCO by default)."""

    def __init__(self, skills: list[dict[str, Any]], source: str) -> None:
        self.skills = skills
        self.source = source
        # preferred label (lowercase) -> record
        self.by_label: dict[str, dict[str, Any]] = {}
        # alt label (lowercase) -> preferred label
        self.alt_to_pref: dict[str, str] = {}
        for s in skills:
            pref = s.get("preferred", "").strip()
            if not pref:
                continue
            self.by_label[pref.lower()] = s
            for alt in s.get("alt", []):
                self.alt_to_pref[alt.strip().lower()] = pref

    def imply_patterns(self) -> dict[str, list[str]]:
        """Regex patterns per taxonomy skill for implied-skill detection."""
        out: dict[str, list[str]] = {}
        for pref, rec in self.by_label.items():
            pats = [re.escape(pref)]
            for alt in rec.get("alt", []):
                if len(alt) >= 4:
                    pats.append(re.escape(alt))
            out[pref] = pats
        return out

    def resolve(self, surface: str) -> str | None:
        """Map a surface form to the taxonomy's preferred label, or None."""
        low = surface.strip().lower()
        if low in self.by_label:
            return self.by_label[low]["preferred"]
        return self.alt_to_pref.get(low)

    def aliases(self) -> dict[str, str]:
        """alt-label -> preferred-label map (feeds normalize.ALIASES)."""
        return dict(self.alt_to_pref)


def load_taxonomy(path: str | Path = DEFAULT_TAXONOMY_PATH) -> SkillTaxonomy | None:
    """Load the taxonomy file; return None (graceful fallback) if absent/bad."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        skills = data if isinstance(data, list) else data.get("skills", [])
        if not skills:
            return None
        return SkillTaxonomy(skills, source=str(p))
    except (json.JSONDecodeError, KeyError, TypeError):
        return None