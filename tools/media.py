#!/usr/bin/env python3
"""Make the site's photos and project images in static/img/.

    python tools/media.py

- Photos in assets/photos/ are cropped, resized to a few widths and saved as WebP
  with all metadata (camera, GPS) stripped.
- The GeoAID flood-probability raster (assets/geoaid/, from the public GeoAID repo)
  is rendered in the site's style.
- The Where to Build Next map is drawn from assets/wtbn/ (run tools/import_wtbn.py first):
  what each square kilometre of Nigeria needs, and the first 100 sites chosen poorest first.
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
    # Field photos (stripped masters from tools/import_media.py)
    "palm-drone-pad": ("field/palm-drone-pad.jpg", (0, 0, 1, 1), (480, 800, 1200, 1600)),
    "palm-estate-road": ("field/palm-estate-road.jpg", (0, 0, 1, 1), (480, 800, 1200)),
    "palm-gnss": ("field/palm-gnss.jpg", (0, 0, 1, 1), (480, 800, 1200)),
    "palm-crown": ("field/palm-crown.jpg", (0, 0, 1, 1), (480, 800, 1200)),
    "palm-pilot": ("field/palm-pilot.jpg", (0, 0.04, 1, 0.96), (360, 540, 900)),
}
# Single-hue sequential ramp (red), near-white for low values so they recede into the light map panel;
# lightness carries the order, so it stays readable with colour-vision deficiency
FLOOD_RAMP = ["#fee5d9", "#fcbba1", "#fc9272", "#fb6a4a", "#de2d26", "#a50f15"]
MAP_PAPER = "#faf8f3"
CATEGORY_COLOURS = ["#3987e5", "#d95926", "#199e70", "#8a918d"]  # hospital, clinic/doctors, pharmacy, other
# Where to Build Next need classes: served, slow signal, town to measure, rural gap. The project's own palette,
# checked with the dataviz validator on a light surface; the page legend uses the same colours (style.css).
WTBN_COLOURS = ["#1b9e77", "#d98b1f", "#4a78d0", "#a6266e"]
WTBN_CRS = "+proj=aea +lat_1=4 +lat_2=13 +lat_0=9 +lon_0=8 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"
WTBN_CITIES = [("Lagos", 3.39, 6.46), ("Abuja", 7.49, 9.06), ("Kano", 8.52, 12.00), ("Port Harcourt", 7.03, 4.82),
               ("Maiduguri", 13.16, 11.85), ("Sokoto", 5.24, 13.06), ("Enugu", 7.51, 6.45)]


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

    fig = plt.figure(figsize=(16, 10), dpi=100, facecolor=MAP_PAPER)
    ax = fig.add_axes([0.03, 0.04, 0.94, 0.92])
    ax.set_facecolor(MAP_PAPER)
    cmap = LinearSegmentedColormap.from_list("flood", FLOOD_RAMP)
    ax.imshow(band, cmap=cmap, vmin=0, vmax=1, extent=(b.left, b.right, b.bottom, b.top), interpolation="nearest")
    boundary.boundary.plot(ax=ax, color="#2b3631", linewidth=1.4, alpha=0.55)
    ax.set_aspect("equal")
    ax.set_axis_off()
    im = figure_to_image(fig)
    plt.close(fig)
    return save_webp(im, "geoaid-flood", (480, 640, 800, 1200, 1600), quality=82)


def wtbn():
    """Drawn at exactly 2 px per 1 km cell with no smoothing, so the class colours stay pure and the
    large sizes compress well as lossless WebP (a smoothed version is several times larger)."""
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.patheffects as pe
    import matplotlib.pyplot as plt
    import pandas as pd
    from matplotlib.colors import ListedColormap
    from pyproj import Transformer

    z = np.load(ASSETS / "wtbn" / "triage.npz")
    cls, x0, y1, cell = z["cls"], float(z["x0"]), float(z["y1"]), float(z["cell"])
    nrow, ncol = cls.shape
    extent = (x0, x0 + ncol * cell, y1 - nrow * cell, y1)
    country = gpd.read_file(ASSETS / "wtbn" / "country.geojson").to_crs(WTBN_CRS)
    states = gpd.read_file(ASSETS / "wtbn" / "states.geojson").to_crs(WTBN_CRS)
    sites = pd.read_csv(ASSETS / "wtbn" / "sites_poorest_first_100.csv")
    to_ea = Transformer.from_crs("EPSG:4326", WTBN_CRS, always_xy=True)
    sx, sy = to_ea.transform(sites["lon"].to_numpy(), sites["lat"].to_numpy())

    px, pad = 2, 40                                   # pixels per cell, margin in pixels
    W, H = ncol * px + 2 * pad, nrow * px + 2 * pad
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100, facecolor=MAP_PAPER)
    ax = fig.add_axes([pad / W, pad / H, ncol * px / W, nrow * px / H])
    ax.set_facecolor(MAP_PAPER)
    ax.imshow(np.ma.masked_less(cls, 0), cmap=ListedColormap(WTBN_COLOURS), vmin=0, vmax=3, extent=extent,
              interpolation="nearest", interpolation_stage="data", zorder=1)
    # Borders without anti-aliasing: pure pixels keep the lossless files small
    states.boundary.plot(ax=ax, color="#8c8c8c", linewidth=1.0, antialiased=False, zorder=2)
    country.boundary.plot(ax=ax, color="#2b3631", linewidth=2.4, antialiased=False, zorder=3)
    for host, marker, size in (("clinic", "o", 190), ("school", "s", 170)):
        pick = (sites["host"] == host).to_numpy()
        ax.scatter(sx[pick], sy[pick], s=size, marker=marker, facecolor="white", edgecolor="#111111",
                   linewidth=2.4, zorder=5)
    halo = [pe.withStroke(linewidth=7, foreground=MAP_PAPER)]
    for name, lon, lat in WTBN_CITIES:
        x, y = to_ea.transform(lon, lat)
        ax.scatter([x], [y], s=70, color="#111111", zorder=6)
        ax.annotate(name, (x, y), xytext=(11, 8), textcoords="offset points", fontsize=29, fontweight="bold",
                    color="#111111", zorder=7, path_effects=halo)
    bx, by = extent[0] + 40_000, extent[2] + 60_000
    ax.plot([bx, bx + 200_000], [by, by], color="#2b3631", lw=8, solid_capstyle="butt", zorder=7)
    ax.annotate("200 km", (bx + 100_000, by), xytext=(0, 14), textcoords="offset points", ha="center",
                fontsize=27, color="#2b3631", zorder=7)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_axis_off()
    big = figure_to_image(fig)
    plt.close(fig)

    out = []
    sizes = [(480, None), (800, None), (big.width // 2, big.reduce(2)), (big.width, big)]
    for w, im in sizes:
        lossless = im is not None                 # exact 2x and 1x renders keep pure colours: lossless
        if im is None:
            im = big.resize((w, round(big.height * w / big.width)), Image.LANCZOS)
        im.save(OUT / f"wtbn-map-{w}.webp", "WEBP", method=6, **({"lossless": True} if lossless else {"quality": 80}))
        out.append({"w": im.width, "h": im.height, "src": f"/img/wtbn-map-{w}.webp"})
    return out


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
    manifest["wtbn-map"] = wtbn()
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    for name, sizes in manifest.items():
        kb = sum((OUT / Path(s["src"]).name).stat().st_size for s in sizes) / 1024
        print(f"{name}: {', '.join(str(s['w']) for s in sizes)} px wide, {kb:.0f} KB total")


if __name__ == "__main__":
    main()
