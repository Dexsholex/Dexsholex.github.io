#!/usr/bin/env python3
"""Make the site's photos and project images in static/img/.

    python tools/media.py

- Photos in assets/photos/ are cropped, resized to a few widths and saved as WebP
  with all metadata (camera, GPS) stripped.
- The GeoAID flood-probability raster (assets/geoaid/, from the public GeoAID repo)
  is rendered in the site's style.
- The Access Map preview is drawn from static/data/lagos-health-osm.json
  (run tools/fetch_osm_health.py first). It shows before the interactive map loads,
  and is all that visitors without JavaScript see.

Writes static/img/manifest.json, which tools/build.py reads for widths and heights.
Needs Pillow, numpy, matplotlib, rasterio and geopandas.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
OUT = ROOT / "static" / "img"
PANEL = "#0d1714"  # shared background of every map panel, both themes

# name: (source, crop box as fractions (left, top, right, bottom), output widths)
PHOTOS = {
    "portrait": ("photos/portrait.jpg", (0, 0.03, 1, 0.863), (360, 540, 720)),
    "about": ("photos/about.jpg", (0, 0.04, 1, 0.873), (360, 540, 720)),
    "contact": ("photos/contact.jpg", (0.253, 0.204, 0.753, 0.537), (96, 192)),
    "avatar": ("photos/portrait.jpg", (0.221, 0.130, 0.749, 0.481), (64, 128)),
}
# Single-hue sequential ramp (blue), dark for low values so they recede into the panel
FLOOD_RAMP = ["#104281", "#1c5cab", "#2a78d6", "#5598e7", "#86b6ef", "#cde2fb"]
CATEGORY_COLOURS = ["#3987e5", "#d95926", "#199e70", "#8a918d"]  # hospital, clinic/doctors, pharmacy, other


def save_webp(im, name, widths, quality=80):
    out = []
    for w in widths:
        h = round(im.height * w / im.width)
        im.resize((w, h), Image.LANCZOS).save(OUT / f"{name}-{w}.webp", "WEBP", quality=quality, method=6)
        out.append({"w": w, "h": h, "src": f"/img/{name}-{w}.webp"})
    return out


def photos():
    entries = {}
    for name, (src, (l, t, r, b), widths) in PHOTOS.items():
        im = ImageOps.exif_transpose(Image.open(ASSETS / src)).convert("RGB")
        W, H = im.size
        im = im.crop((round(l * W), round(t * H), round(r * W), round(b * H)))
        clean = Image.new("RGB", im.size)
        clean.paste(im)  # a fresh image carries no EXIF or other metadata
        entries[name] = save_webp(clean, name, widths)
    return entries


def figure_to_image(fig):
    fig.canvas.draw()
    return Image.fromarray(np.asarray(fig.canvas.buffer_rgba())).convert("RGB")


def geoaid():
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import rasterio
    from matplotlib.colors import LinearSegmentedColormap

    with rasterio.open(ASSETS / "geoaid" / "flood_probability_map.tif") as src:
        band = src.read(1, masked=True).astype(float)
        b = src.bounds
        crs = src.crs
    boundary = gpd.read_file(ASSETS / "geoaid" / "amuwo_odofin_boundary.geojson").to_crs(crs)

    fig = plt.figure(figsize=(16, 10), dpi=100, facecolor=PANEL)
    ax = fig.add_axes([0.03, 0.04, 0.94, 0.92])
    ax.set_facecolor(PANEL)
    cmap = LinearSegmentedColormap.from_list("flood", FLOOD_RAMP)
    ax.imshow(band, cmap=cmap, vmin=0, vmax=1, extent=(b.left, b.right, b.bottom, b.top), interpolation="nearest")
    boundary.boundary.plot(ax=ax, color="#e7ede9", linewidth=1.4, alpha=0.6)
    ax.set_aspect("equal")
    ax.set_axis_off()
    im = figure_to_image(fig)
    plt.close(fig)
    return save_webp(im, "geoaid-flood", (480, 640, 800, 1200, 1600), quality=82)


def access_map_preview():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely.geometry import shape

    data = json.loads((ROOT / "static" / "data" / "lagos-health-osm.json").read_text(encoding="utf-8"))
    fig = plt.figure(figsize=(16, 7), dpi=100, facecolor=PANEL)  # Lagos State is wide and short
    ax = fig.add_axes([0.015, 0.03, 0.97, 0.94])
    ax.set_facecolor(PANEL)
    for f in data["lgas"]["features"]:
        g = shape(f["geometry"])
        for poly in getattr(g, "geoms", [g]):
            x, y = poly.exterior.xy
            ax.fill(x, y, color="#ffffff", alpha=0.03, linewidth=0)
            ax.plot(x, y, color="#e7ede9", alpha=0.35, linewidth=1.1)
    slot = [0, 1, 1, 2, 3]  # hospital, clinic, doctors, pharmacy, other -> colour slot
    cats = np.array([slot[p[2]] for p in data["facilities"]])
    xs = np.array([p[0] for p in data["facilities"]])
    ys = np.array([p[1] for p in data["facilities"]])
    order = np.argsort([-(cats == c).sum() for c in cats], kind="stable")  # big groups first, small on top
    ax.scatter(xs[order], ys[order], s=34, c=[CATEGORY_COLOURS[c] for c in cats[order]],
               edgecolors=PANEL, linewidths=1.2)
    ax.set_aspect(1 / np.cos(np.radians(6.5)))
    ax.set_axis_off()
    im = figure_to_image(fig)
    plt.close(fig)
    return save_webp(im, "access-map-preview", (480, 800, 1200, 1600), quality=80)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {}
    manifest.update(photos())
    manifest["geoaid-flood"] = geoaid()
    manifest["access-map-preview"] = access_map_preview()
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    for name, sizes in manifest.items():
        kb = sum((OUT / Path(s["src"]).name).stat().st_size for s in sizes) / 1024
        print(f"{name}: {', '.join(str(s['w']) for s in sizes)} px wide, {kb:.0f} KB total")


if __name__ == "__main__":
    main()
