"""M8 validation: extraction on the user's resume vs. the seed skills JSON.

The seed skillsdataset.json was derived from the same resume (its meta says
"Resume (2 versions)"), so it is ground truth for what the resume evidences.
Both outputs are canonicalized through normalize.py and compared:
- recall: how many seed canonical skills does extraction recover?
- extraction-only: skills extraction found that the seed curated away
  (candidates for curation-vs-noise review).
"""

from __future__ import annotations

import json
from pathlib import Path

from .normalize import canonical_term
from .resume import _flatten_phrases


def _canonical_set(phrases: list[str]) -> set[str]:
    out: set[str] = set()
    for p in phrases:
        c = canonical_term(p)
        if c:
            out.add(c.lower())
    return out


def main() -> None:
    seed = json.loads(Path("data/skillsdataset.json").read_text(encoding="utf-8"))
    extracted = json.loads(
        Path("output/extracted_skills.json").read_text(encoding="utf-8")
    )

    seed_canon = _canonical_set(_flatten_phrases(seed))
    ext_canon = _canonical_set(_flatten_phrases(extracted))

    recovered = seed_canon & ext_canon
    missed = seed_canon - ext_canon
    extra = ext_canon - seed_canon

    print(f"Seed canonical skills:      {len(seed_canon)}")
    print(f"Extracted canonical skills: {len(ext_canon)}")
    print(f"Recovered from seed:        {len(recovered)}  "
          f"(recall {len(recovered) / len(seed_canon):.0%})")
    print(f"\nSeed skills NOT recovered ({len(missed)}):")
    for s in sorted(missed):
        print(f"  - {s}")
    print(f"\nExtraction-only skills ({len(extra)}) — curation vs. noise review:")
    for s in sorted(extra):
        print(f"  + {s}")


if __name__ == "__main__":
    main()