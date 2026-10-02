#!/usr/bin/env python3
"""Pull the health facilities OpenStreetMap holds for Lagos State, for the Access Map teaser.

    python tools/fetch_osm_health.py              pull a fresh snapshot (needs internet)
    python tools/fetch_osm_health.py --recount    recount facilities per LGA from the saved file

Writes static/data/lagos-health-osm.json: simplified LGA outlines plus one point per
facility (amenity=hospital|clinic|doctors|pharmacy, or any healthcare=* tag, the same
tags as the audit script). Re-run it to refresh the snapshot; the date is stored in the
file and shown under the map. Data (c) OpenStreetMap contributors, ODbL.

Needs requests and shapely.
"""
import datetime as dt
import json
import sys
import time
from pathlib import Path

import requests
from shapely.geometry import LineString, Point, mapping
from shapely.ops import polygonize, unary_union

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "data" / "lagos-health-osm.json"
OVERPASS = ["https://overpass-api.de/api/interpreter", "https://overpass.private.coffee/api/interpreter"]
HEADERS = {"User-Agent": "portfolio-site/1.0 (Lagos Access Map teaser; github.com/Dexsholex)"}
AREA = 'area["boundary"="administrative"]["admin_level"="4"]["name"~"^Lagos"]->.lagos;'
CATEGORIES = ["hospital", "clinic", "doctors", "pharmacy", "other"]


def overpass(body):
    """Public Overpass servers are often busy; try each a few times before giving up."""
    query = {"data": f"[out:json][timeout:180];{AREA}{body}"}
    last = None
    for attempt in range(3):
        for url in OVERPASS:
            try:
                r = requests.post(url, data=query, headers=HEADERS, timeout=240)
                r.raise_for_status()
                return r.json()["elements"]
            except (requests.RequestException, ValueError) as e:
                last = e
                print(f"  {url} failed ({e.__class__.__name__}), retrying...")
        time.sleep(20 * (attempt + 1))
    raise SystemExit(f"Overpass unavailable: {last}")


def relation_polygon(rel):
    outer = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
             for m in rel.get("members", []) if m["type"] == "way" and m.get("role") in ("outer", "") and m.get("geometry")]
    inner = [LineString([(p["lon"], p["lat"]) for p in m["geometry"]])
             for m in rel.get("members", []) if m["type"] == "way" and m.get("role") == "inner" and m.get("geometry")]
    shape = unary_union(list(polygonize(unary_union(outer))))
    if inner:
        shape = shape.difference(unary_union(list(polygonize(unary_union(inner)))))
    return shape


def rounded(geom, nd=4):
    def r(c):
        return [round(c[0], nd), round(c[1], nd)]
    g = mapping(geom)
    if g["type"] == "Polygon":
        g["coordinates"] = [[r(c) for c in ring] for ring in g["coordinates"]]
    else:
        g["coordinates"] = [[[r(c) for c in ring] for ring in poly] for poly in g["coordinates"]]
    return g


def assign_counts(polys, points, n_cats):
    """Count facilities per LGA, each facility once (first outline that contains it)."""
    counts = [[0] * n_cats for _ in polys]
    for lon, lat, cat, _ in points:
        pt = Point(lon, lat)
        for i, poly in enumerate(polys):
            if poly.contains(pt):
                counts[i][cat] += 1
                break
    return counts


def recount():
    """Recompute per-LGA counts from the saved snapshot, offline (uses the simplified outlines)."""
    from shapely.geometry import shape as to_shape
    data = json.loads(OUT.read_text(encoding="utf-8"))
    feats = data["lgas"]["features"]
    counts = assign_counts([to_shape(f["geometry"]) for f in feats], data["facilities"], len(data["categories"]))
    for feat, c in zip(feats, counts):
        feat["properties"]["counts"] = c
    data["lgas"]["features"].sort(key=lambda f: f["properties"]["name"])
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    placed = sum(sum(f["properties"]["counts"]) for f in data["lgas"]["features"])
    print(f"Recounted {placed} of {len(data['facilities'])} facilities into {len(data['lgas']['features'])} LGAs")


def main():
    if "--recount" in sys.argv:
        return recount()
    print("Fetching LGA boundaries...")
    shapes = []
    for rel in overpass('rel["boundary"="administrative"]["admin_level"="6"](area.lagos);out geom;'):
        shape = relation_polygon(rel)
        if not shape.is_empty:
            shapes.append((rel["tags"].get("name", ""), shape))
    print(f"  {len(shapes)} LGAs")

    print("Fetching health facilities...")
    body = ('(nwr["amenity"~"^(hospital|clinic|doctors|pharmacy)$"](area.lagos);'
            'nwr["healthcare"](area.lagos););out center tags;')
    seen, points = set(), []
    for el in overpass(body):
        lat = el.get("lat", el.get("center", {}).get("lat"))
        lon = el.get("lon", el.get("center", {}).get("lon"))
        if lat is None or (el["type"], el["id"]) in seen:
            continue
        seen.add((el["type"], el["id"]))
        tags = el.get("tags", {})
        kind = tags.get("amenity") if tags.get("amenity") in CATEGORIES else tags.get("healthcare")
        cat = CATEGORIES.index(kind) if kind in CATEGORIES else CATEGORIES.index("other")
        points.append([round(lon, 5), round(lat, 5), cat, tags.get("name", "")])
    print(f"  {len(points)} facilities")

    # Count per LGA on the full-detail outlines, then simplify them for the web
    lgas = []
    all_counts = assign_counts([s for _, s in shapes], points, len(CATEGORIES))
    for (name, shape), counts in zip(shapes, all_counts):
        simple = shape.simplify(0.0012, preserve_topology=True)
        lgas.append({"type": "Feature", "properties": {"name": name, "counts": counts}, "geometry": rounded(simple)})
    lgas.sort(key=lambda f: f["properties"]["name"])

    OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "pulled": dt.date.today().isoformat(),
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "categories": CATEGORIES,
        "lgas": {"type": "FeatureCollection", "features": lgas},
        "facilities": points,
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
