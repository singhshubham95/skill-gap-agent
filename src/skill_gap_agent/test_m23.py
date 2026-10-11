"""M23 units: the assist-not-act rule for LinkedIn capture
(specs/12-extension.md §Capture). The synthetic click was the strongest
ToS signal in the product — these tests make sure it never returns."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTENT_JS = REPO_ROOT / "extension" / "content.js"


def _source() -> str:
    return CONTENT_JS.read_text(encoding="utf-8")


def test_no_synthetic_click_ever():
    src = _source()
    assert ".click(" not in src, "content.js must never click page controls"
    assert "btn.click" not in src


def test_assist_wiring_present():
    src = _source()
    assert "scrollIntoView" in src, "must scroll the expand control into view"
    assert "focus(" in src, "must focus the expand control"
    assert "#ffd400" in src, "Ctrl+F-style yellow highlight missing"
    assert "outline" in src, "highlight outline missing"
    assert "Click to expand the job description" in src, "tooltip missing"


def test_guiding_error_and_unchanged_extraction():
    src = _source()
    assert "press Capture again" in src, "the error must guide the user"
    # The expanded-description path keeps its exact response shape.
    for needle in ("capturedAt", "location.href", "innerText", "document.title"):
        assert needle in src, f"extraction changed: {needle} missing"
    assert '[id^="JobDetails_AboutTheJob_"]' in src
    assert 'data-testid="expandable-text-button"' in src


def test_capture_scope_stays_single_page():
    src = _source()
    assert re.search(r'chrome\.runtime\.onMessage\.addListener', src)
    assert 'skillgap:capture' in src
