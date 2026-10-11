"""M23 offline check — assist-not-act LinkedIn capture (no synthetic
click; scroll + focus + highlight instead) and the capture-scoping
guardrails (specs/12-extension.md §Capture).

Run: python -m skill_gap_agent.m23_check
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_JS = REPO_ROOT / "extension" / "content.js"
EXTENSION_DIR = REPO_ROOT / "extension"


def check_no_click() -> None:
    src = CONTENT_JS.read_text(encoding="utf-8")
    assert ".click(" not in src, "content.js must never click page controls"
    assert "guideExpandButton" in src, "assist path missing"
    assert "scrollIntoView" in src and "focus(" in src, "assist wiring missing"
    assert "#ffd400" in src and "outline" in src, "highlight missing"
    assert "Click to expand the job description" in src, "tooltip missing"
    print("no-click OK: assist wiring (scroll + focus + yellow highlight) present")


def check_guidance_surfaces() -> None:
    src = CONTENT_JS.read_text(encoding="utf-8")
    assert "press Capture again" in src, "guiding error missing"
    # The panel surfaces capture errors through its status line unchanged.
    js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")
    assert re.search(r'resp\.error', js), "panel must surface capture errors"
    readme = (REPO_ROOT / "extension" / "README.md").read_text(encoding="utf-8")
    assert "see more" in readme, "capture docs must mention the expand step"
    print("guidance OK: error message + panel status + docs mention expand")


def check_extraction_unchanged() -> None:
    src = CONTENT_JS.read_text(encoding="utf-8")
    for needle in (
        '[id^="JobDetails_AboutTheJob_"]',
        'data-testid="expandable-text-button"',
        "capturedAt", "location.href", "innerText", "document.title",
        "skillgap:capture",
    ):
        assert needle in src, f"extraction changed: {needle} missing"
    print("extraction OK: selectors + response shape + message contract unchanged")


def main() -> None:
    check_no_click()
    check_guidance_surfaces()
    check_extraction_unchanged()
    print("m23_check: PASS")


if __name__ == "__main__":
    main()
