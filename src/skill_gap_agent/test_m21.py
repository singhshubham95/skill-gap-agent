"""M21 units: data-disclosure copy consistency across user-facing surfaces
(specs/12-extension.md §Data disclosure). The S2 finding was a copy bug —
these tests lock the accurate claim in place."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"

SURFACES = (
    EXTENSION_DIR / "sidepanel.html",
    EXTENSION_DIR / "README.md",
    REPO_ROOT / "README.md",
)


def test_misleading_claim_is_gone():
    for path in SURFACES:
        text = path.read_text(encoding="utf-8")
        assert "stays on your machine" not in text, f"banned claim in {path.name}"


def test_accurate_disclosure_present():
    html = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    assert "sent over HTTPS" in html
    assert "extension's developer" in html
    for name in ("OpenRouter", "GLM", "OpenAI"):
        assert name in html, f"destination {name} not named in the panel"
    assert "skill-gap terms" in html, "GitHub search flow not disclosed"


def test_consent_checkbox_never_prechecked():
    html = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    assert re.search(r'id="disclosureack"', html)
    assert not re.search(r'id="disclosureack"[^>]*checked', html)


def test_server_enforces_ack():
    source = (REPO_ROOT / "src" / "skill_gap_agent" / "server.py").read_text(
        encoding="utf-8"
    )
    assert 'X-Disclosure-Ack' in source, "server-side gate missing"
