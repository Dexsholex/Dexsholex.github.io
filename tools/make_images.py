#!/usr/bin/env python3
"""Make the social share image and icons in static/.

    python tools/make_images.py

Run it again after changing the name, flagship line, base_url or oil palm figures in
content/site.json, and after tools/media.py (the GeoAID card reuses its map),
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


def wrap_text(d, text, fnt, width):
    lines, line = [], ""
    for w in text.split():
        trial = f"{line} {w}".strip()
        if d.textlength(trial, font=fnt) > width and line:
            lines.append(line)
            line = w
        else:
            line = trial
    return lines + [line]


def base_card(site):
    """Dark card with a fading graticule and the name; shared by every share image."""
    W, H = 1200, 630
    im = Image.new("RGB", (W, H), BG)
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
    im = Image.composite(grid, im, mask).convert("RGBA")
    im.alpha_composite(mark(56), (72, 66))
    d = ImageDraw.Draw(im)
    d.text((146, 94), site["name"], font=font("seguisb.ttf", 34), fill=TEXT, anchor="lm")
    host = site["base_url"].split("//", 1)[-1].rstrip("/")
    d.text((72, 560), host, font=font("consola.ttf", 24), fill=MUTED)
    d.rectangle([0, H - 8, W, H], fill=ACCENT_DEEP)
    return im


def text_block(im, kicker, title, subline, width, size=76):
    d = ImageDraw.Draw(im)
    d.text((72, 214), kicker, font=font("consola.ttf", 24), fill=ACCENT)
    title_font = font("segoeuib.ttf", size)
    y = 262
    for ln in wrap_text(d, title, title_font, width):
        d.text((68, y), ln, font=title_font, fill=WHITE)
        y += round(size * 1.16)
    if subline:
        d.text((72, y + 30), subline, font=font("segoeui.ttf", 28), fill=MUTED)


def survey_target(im):
    over = Image.new("RGBA", im.size, (0, 0, 0, 0))
    o = ImageDraw.Draw(over)
    cx, cy = 975, 270
    col = ACCENT + (190,)
    for r in (140, 62):
        o.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=3)
    for a, b in (((cx, cy - 195), (cx, cy - 78)), ((cx, cy + 78), (cx, cy + 195)),
                 ((cx - 195, cy), (cx - 78, cy)), ((cx + 78, cy), (cx + 195, cy))):
        o.line([a, b], fill=col, width=3)
    o.ellipse([cx - 9, cy - 9, cx + 9, cy + 9], fill=ACCENT + (255,))
    im.alpha_composite(over)
    ImageDraw.Draw(im).text((cx, cy + 230), "6.455° N   3.384° E", font=font("consola.ttf", 22), fill=MUTED, anchor="mm")


def home_image(site):
    im = base_card(site)
    survey_target(im)
    text_block(im, "GEOSPATIAL DATA SCIENCE · GEOSPATIAL AI", site["flagship"],
               "Satellite, drone and aerial imagery  ·  Lagos, Nigeria", 720)
    im.convert("RGB").save(STATIC / "og.png", optimize=True)


def oil_palm_image(site):
    palm = site["projects"]["oil_palm"]
    im = base_card(site)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([760, 150, 1128, 520], radius=28, fill=(20, 36, 30), outline=(40, 70, 58), width=2)
    d.text((944, 250), palm["palms"], font=font("segoeuib.ttf", 72), fill=WHITE, anchor="mm")
    d.text((944, 312), "palms detected", font=font("segoeui.ttf", 28), fill=MUTED, anchor="mm")
    d.line([(800, 370), (1088, 370)], fill=(40, 70, 58), width=2)
    d.text((944, 420), f"{palm['hectares']} ha", font=font("seguisb.ttf", 34), fill=TEXT, anchor="mm")
    d.text((944, 466), f"{palm['blocks']} blocks", font=font("segoeui.ttf", 26), fill=MUTED, anchor="mm")
    text_block(im, "CASE STUDY · GEOSPATIAL AI", "Counting oil palms from aerial imagery",
               "YOLOv8 crown detection, block by block", 640, size=68)
    im.convert("RGB").save(STATIC / "og-oil-palm.png", optimize=True)


def geoaid_image(site):
    im = base_card(site)
    pic = Image.open(STATIC / "img" / "geoaid-flood-800.webp").convert("RGB")
    pic = pic.crop((110, 0, 690, 500)).resize((406, 350), Image.LANCZOS)
    m = Image.new("L", pic.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, pic.width - 1, pic.height - 1], radius=24, fill=255)
    im.paste(pic, (730, 150), m)
    text_block(im, "CASE STUDY · SPATIAL ML", "GeoAID: flood risk mapping in Lagos",
               "Amuwo-Odofin pilot · spatially cross-validated", 600, size=64)
    im.convert("RGB").save(STATIC / "og-geoaid.png", optimize=True)


def main():
    site = json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8"))
    STATIC.mkdir(exist_ok=True)
    (STATIC / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8", newline="\n")
    mark(180, radius=0).convert("RGB").save(STATIC / "apple-touch-icon.png", optimize=True)
    mark(256).save(STATIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    home_image(site)
    oil_palm_image(site)
    geoaid_image(site)
    for p in sorted(STATIC.glob("*.*")):
        print(f"{p.name}: {p.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
