#!/usr/bin/env python3
"""Make the favicon and touch icon in static/.

    python tools/make_images.py

The social share cards are drawn by tools/make_og.mjs (npm run og), because a browser
lays out every script, Arabic included. Needs Pillow (pip install pillow).
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

ACCENT_DEEP = (11, 107, 75)
WHITE = (255, 255, 255)

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#0b6b4b"/><g fill="#fff" stroke="#fff"><circle cx="16" cy="16" r="7.5" fill="none" stroke-width="2"/><path d="M16 4.5v5.5M16 22v5.5M4.5 16H10M22 16h5.5" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="16" r="2.2" stroke="none"/></g></svg>
"""


def round_line(d, a, b, width, fill):
    d.line([a, b], fill=fill, width=width)
    r = width / 2
    for x, y in (a, b):
        d.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def mark(size, bg=ACCENT_DEEP, fg=WHITE, radius=8):
    """The brand mark (a survey target) drawn on a 32-unit grid, supersampled for smooth edges."""
    s = size * 8
    u = s / 32
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius * u, fill=bg)
    c = 16 * u
    d.ellipse([c - 7.5 * u - u, c - 7.5 * u - u, c + 7.5 * u + u, c + 7.5 * u + u], outline=fg, width=round(2 * u))
    for a, b in (((16, 4.5), (16, 10)), ((16, 22), (16, 27.5)), ((4.5, 16), (10, 16)), ((22, 16), (27.5, 16))):
        round_line(d, (a[0] * u, a[1] * u), (b[0] * u, b[1] * u), round(2 * u), fg)
    d.ellipse([c - 2.2 * u, c - 2.2 * u, c + 2.2 * u, c + 2.2 * u], fill=fg)
    return im.resize((size, size), Image.LANCZOS)


def main():
    STATIC.mkdir(exist_ok=True)
    (STATIC / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8", newline="\n")
    mark(180, radius=0).convert("RGB").save(STATIC / "apple-touch-icon.png", optimize=True)
    mark(256).save(STATIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    for p in sorted(STATIC.glob("*.*")):
        print(f"{p.name}: {p.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
