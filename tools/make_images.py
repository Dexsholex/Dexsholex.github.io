#!/usr/bin/env python3
"""Make the social share image and icons in static/.

    python tools/make_images.py

Run it again after changing the name, flagship line or base_url in content/site.json,
then commit the new files. Needs Pillow (pip install pillow). Fonts are read from
C:/Windows/Fonts, so run it on Windows or point FONT_DIR at a folder holding
segoeuib.ttf, seguisb.ttf, segoeui.ttf and consola.ttf.
"""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
FONT_DIR = Path("C:/Windows/Fonts")

BG = (15, 22, 19)
ACCENT = (92, 201, 154)
ACCENT_DEEP = (11, 107, 75)
TEXT = (231, 237, 233)
MUTED = (166, 179, 172)
WHITE = (255, 255, 255)

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="8" fill="#0b6b4b"/><g fill="#fff" stroke="#fff"><circle cx="16" cy="16" r="7.5" fill="none" stroke-width="2"/><path d="M16 4.5v5.5M16 22v5.5M4.5 16H10M22 16h5.5" stroke-width="2" stroke-linecap="round"/><circle cx="16" cy="16" r="2.2" stroke="none"/></g></svg>
"""


def font(name, size):
    return ImageFont.truetype(str(FONT_DIR / name), size)


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


def share_image(site):
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), BG)

    # Graticule, fading out from the top right
    grid = Image.new("RGB", (W, H), BG)
    g = ImageDraw.Draw(grid)
    for x in range(0, W, 60):
        g.line([(x, 0), (x, H)], fill=(30, 52, 42), width=1)
    for y in range(0, H, 60):
        g.line([(0, y), (W, y)], fill=(30, 52, 42), width=1)
    fade = Image.radial_gradient("L").resize((1900, 1500))
    fade = Image.eval(fade, lambda v: max(0, 255 - int(v * 1.25)))
    mask = Image.new("L", (W, H), 0)
    mask.paste(fade, (1000 - 950, 120 - 750))
    im = Image.composite(grid, im, mask)

    # Survey target on the right
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    o = ImageDraw.Draw(over)
    cx, cy = 975, 270
    col = ACCENT + (190,)
    for r in (140, 62):
        o.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=3)
    for a, b in (((cx, cy - 195), (cx, cy - 78)), ((cx, cy + 78), (cx, cy + 195)),
                 ((cx - 195, cy), (cx - 78, cy)), ((cx + 78, cy), (cx + 195, cy))):
        o.line([a, b], fill=col, width=3)
    o.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=ACCENT + (255,))
    im = Image.alpha_composite(im.convert("RGBA"), over)

    d = ImageDraw.Draw(im)
    mono = font("consola.ttf", 22)
    d.text((cx, cy + 230), "6.455° N   3.384° E", font=mono, fill=MUTED, anchor="mm")

    # Name with the brand mark
    im.alpha_composite(mark(56), (72, 66))
    d.text((146, 94), site["name"], font=font("seguisb.ttf", 34), fill=TEXT, anchor="lm")

    # Kicker and flagship line
    d.text((72, 214), "GEOSPATIAL DATA SCIENCE · LAGOS, NIGERIA", font=font("consola.ttf", 24), fill=ACCENT)
    title_font = font("segoeuib.ttf", 76)
    words, lines, line = site["flagship"].split(), [], ""
    for w in words:
        trial = f"{line} {w}".strip()
        if d.textlength(trial, font=title_font) > 720 and line:
            lines.append(line)
            line = w
        else:
            line = trial
    lines.append(line)
    y = 262
    for ln in lines:
        d.text((68, y), ln, font=title_font, fill=WHITE)
        y += 88

    d.text((72, y + 34), "Satellite imagery  ·  Spatial machine learning  ·  GIS", font=font("segoeui.ttf", 28), fill=MUTED)
    host = site["base_url"].split("//", 1)[-1].rstrip("/")
    d.text((72, 560), host, font=font("consola.ttf", 24), fill=MUTED)
    d.rectangle([0, H - 8, W, H], fill=ACCENT_DEEP)

    im.convert("RGB").save(STATIC / "og.png", optimize=True)


def main():
    site = json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8"))
    STATIC.mkdir(exist_ok=True)
    (STATIC / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8", newline="\n")
    mark(180, radius=0).convert("RGB").save(STATIC / "apple-touch-icon.png", optimize=True)
    mark(256).save(STATIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    share_image(site)
    for p in sorted(STATIC.iterdir()):
        print(f"{p.name}: {p.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
