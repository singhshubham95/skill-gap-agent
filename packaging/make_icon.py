"""Generate packaging/app.ico from the extension icon (build-time asset)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "extension" / "icons" / "icon128.png"
TARGET = REPO / "packaging" / "app.ico"


def main() -> None:
    with Image.open(SOURCE) as image:
        image.convert("RGBA").save(
            TARGET,
            format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128)],
        )
    print(f"wrote {TARGET} ({TARGET.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
