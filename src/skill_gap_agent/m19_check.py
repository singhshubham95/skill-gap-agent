"""M19 verification: light/dark theme checks (offline — no network beyond
localhost).

Checks:
1. Plan theming: render_plan_html emits the first stylesheet — CSS
   variables, color-scheme, prefers-color-scheme media block and both
   data-theme override palettes — and stays self-contained + JS-free.
   GET /plan.html?theme=dark|light injects data-theme at serve time; no
   param or an invalid value injects nothing; the on-disk file is never
   modified.
2. Panel theming: header override button (Auto/Light/Dark cycle),
   themePref persistence, data-theme attribute switching, plan iframe URL
   gains ?theme= only while overridden; CSS carries the same palette
   system (media block + both forced palettes) as the plan.

Run: python -m skill_gap_agent.m19_check
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from . import output as output_mod
from . import server

REPO_ROOT = Path(__file__).resolve().parents[2]
EXTENSION_DIR = REPO_ROOT / "extension"
OUTPUT_DIR = REPO_ROOT / "output"


# --- http helpers (same shape as m14/m18 checks) ---------------------------


def _get(base: str, path: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(base + path, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _start_server() -> tuple[ThreadingHTTPServer, str]:
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


class _Preserve:
    """Save/restore output/plan.html around the serve-time checks."""

    def __enter__(self):
        self._target = OUTPUT_DIR / "plan.html"
        self._saved = self._target.read_bytes() if self._target.exists() else None
        return self

    def __exit__(self, *exc):
        if self._saved is None:
            if self._target.exists():
                self._target.unlink()
        else:
            self._target.write_bytes(self._saved)
        return False


# --- checks ----------------------------------------------------------------


def check_plan_theming() -> None:
    html = output_mod.render_plan_html([], [], {"canonical": 0, "implied": 0, "jds": 0})

    # The first stylesheet: variables, system path, both forced palettes.
    assert "<style>" in html and "</style>" in html, "plan stylesheet missing"
    assert "color-scheme: light dark" in html, "plan must declare color-scheme"
    assert "prefers-color-scheme" in html, "plan must follow the system theme"
    assert "[data-theme='dark']" in html and "[data-theme='light']" in html, (
        "plan must carry both forced palettes"
    )
    # Still self-contained + JS-free (locked M10/M13 property).
    assert "<script" not in html, "plan.html must stay JS-free"
    assert "<html>" in html, "literal <html> tag needed for serve-time injection"

    with _Preserve():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "plan.html").write_text(html, encoding="utf-8")
        before = (OUTPUT_DIR / "plan.html").read_bytes()
        httpd, base = _start_server()
        try:
            code, body = _get(base, "/plan.html")
            assert code == 200 and b"data-theme" not in body.split(b"<html>")[1][:30], (
                "plain serve must not inject a theme"
            )
            code, body = _get(base, "/plan.html?theme=dark")
            text = body.decode("utf-8")
            assert code == 200 and "<html data-theme='dark'>" in text, text[:200]
            code, body = _get(base, "/plan.html?theme=light")
            text = body.decode("utf-8")
            assert code == 200 and "<html data-theme='light'>" in text, text[:200]
            # Invalid values are ignored — no injection surface.
            for bad in ("evil", "dark'>", "../../x", ""):
                code, body = _get(base, "/plan.html?theme=" + urllib.parse.quote(bad))
                assert code == 200, (bad, code)
                assert b"data-theme" not in body.split(b"<html>")[1][:30], (
                    f"invalid theme value injected an attribute: {bad!r}"
                )
            # The on-disk file is never modified by serving.
            assert (OUTPUT_DIR / "plan.html").read_bytes() == before
        finally:
            httpd.shutdown()
    print("plan theming OK: stylesheet palettes, JS-free, ?theme= injection, "
          "invalid values ignored, disk untouched")


def check_panel_theming() -> None:
    html = (EXTENSION_DIR / "sidepanel.html").read_text(encoding="utf-8")
    css = (EXTENSION_DIR / "sidepanel.css").read_text(encoding="utf-8")
    js = (EXTENSION_DIR / "sidepanel.js").read_text(encoding="utf-8")

    # Override button: minimal, one control, three states.
    assert 'id="themebtn"' in html, "theme override button missing"
    assert "Theme: Auto" in html, "button must show the current state"

    # System path + forced palettes mirror the plan's.
    assert "color-scheme: light dark" in css, "panel must declare color-scheme"
    assert "prefers-color-scheme" in css, "panel must follow the system theme"
    assert '[data-theme="dark"]' in css and '[data-theme="light"]' in css, (
        "panel must carry both forced palettes"
    )
    assert ":root" in css and "--bg:" in css and "--fg:" in css, (
      "panel palette must be CSS variables"
    )

    # Wiring: cycle order, persistence (preference flag only), switching.
    assert '"auto", "light", "dark"' in js, "cycle must be Auto -> Light -> Dark"
    assert "themePref" in js, "theme preference missing"
    assert 'chrome.storage.local.set({ themePref })' in js, "preference must persist"
    assert 'document.documentElement.setAttribute("data-theme"' in js, (
        "override must set data-theme on the panel root"
    )
    assert 'document.documentElement.removeAttribute("data-theme")' in js, (
        "Auto must return control to the system theme"
    )
    # Plan follows the panel; ?theme= only while overridden.
    assert '?theme=" + themePref' in js, "plan URL must carry the override"
    assert 'themePref === "auto"' in js, "Auto must send no theme parameter"
    print("panel theming OK: button, palettes, persistence, plan link")


def main() -> None:
    check_plan_theming()
    check_panel_theming()
    print("M19 CHECK PASS: system theme + override + plan follows panel OK.")


if __name__ == "__main__":
    main()
