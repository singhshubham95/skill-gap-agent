"""Generate the extension's placeholder store icons (stdlib only).

Design: an indigo rounded square with three ascending white bars — the
"closing the gap" motif. Rendered at 4x and box-downsampled so the corners
stay clean at every size. Regenerate with:

    python tools/generate_icons.py

Chrome requires 16/48/128 px icons (manifest "icons").
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[1] / "extension" / "icons"
SIZES = (16, 48, 128)
SS = 4  # supersampling factor

BG = (43, 65, 148)      # indigo
FG = (255, 255, 255)    # bars
ACCENT = (129, 163, 255)  # tallest bar (soft blue)


def _pixel(x: int, y: int, size: int) -> tuple[int, int, int]:
    """Color of one supersampled pixel (coords in 0..size*SS, inside the
    rounded rect — corners are filtered by _inside_rounded first)."""
    s = size * SS
    # Bars: three columns, ascending heights, centered horizontally.
    margin = 0.22 * s
    gap = 0.07 * s
    bar_w = (s - 2 * margin - 2 * gap) / 3
    heights = (0.30, 0.46, 0.62)
    base_y = 0.76 * s
    for i, h in enumerate(heights):
        x0 = margin + i * (bar_w + gap)
        x1 = x0 + bar_w
        y1 = base_y
        y0 = y1 - h * s
        if x0 <= x < x1 and y0 <= y < y1:
            return ACCENT if i == 2 else FG
    return BG


def _inside_rounded(x: float, y: float, s: float) -> bool:
    r = 0.18 * s
    nx = min(x, s - 1 - x)
    ny = min(y, s - 1 - y)
    if nx < r and ny < r:
        return (r - nx) ** 2 + (r - ny) ** 2 <= r * r
    return True


def render(size: int) -> bytes:
    """PNG bytes for one icon, RGBA, supersampled."""
    s = size * SS
    rows = []
    for y in range(size):
        row = bytearray([0])  # filter type 0
        for x in range(size):
            acc = [0, 0, 0, 0]
            for sy in range(SS):
                for sx in range(SS):
                    px, py = x * SS + sx, y * SS + sy
                    if not _inside_rounded(px, py, s):
                        continue
                    r, g, b = _pixel(px, py, size)
                    acc[0] += r
                    acc[1] += g
                    acc[2] += b
                    acc[3] += 255
            n = SS * SS
            row += bytes(v // n for v in acc)
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        path = OUT_DIR / f"icon{size}.png"
        path.write_bytes(render(size))
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
