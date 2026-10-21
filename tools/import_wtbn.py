#!/usr/bin/env python3
"""Bring the Where to Build Next results into the site.

    python tools/import_wtbn.py

Reads the project folder (the public repository github.com/Dexsholex/where-to-build-next,
checked out locally) and writes:

- assets/wtbn/: the 1 km need classes, state borders and the first 100 sites chosen
  poorest first, which tools/media.py draws into the case study map;
- content/site.json projects.where_to_build: the numbers the pages print, copied from the
  project's own outputs/tables, so the site and the project can never disagree.

Run it again whenever the project is rebuilt, then run tools/media.py and tools/build.py.
The classes are derived from Speedtest by Ookla data, so they stay under CC BY-NC-SA 4.0.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROJECT = Path(r"C:\Users\LENOVO\Documents\EM\DSN Bootcamp\Where to Build Next")
OUT = ROOT / "assets" / "wtbn"
SITE = ROOT / "content" / "site.json"
CRS_EQUAL_AREA = "+proj=aea +lat_1=4 +lat_2=13 +lat_0=9 +lon_0=8 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs"


def assets():
    import geopandas as gpd

    OUT.mkdir(parents=True, exist_ok=True)
    g = np.load(PROJECT / "data" / "processed" / "grid.npz")
    cls = np.load(PROJECT / "data" / "processed" / "triage.npz")["cls"]
    np.savez_compressed(OUT / "triage.npz", cls=cls, x0=g["x0"], y1=g["y1"], cell=g["cell"])
    # Country outline and state borders, simplified to 200 m in the grid's equal-area projection (a
    # quarter of a map pixel), saved in longitude and latitude because GeoJSON has no other coordinate system
    for src, name in (("nigeria_admin0.gpkg", "country"), ("nigeria_admin1.gpkg", "states")):
        shapes = gpd.read_file(PROJECT / "data" / "input" / src).to_crs(CRS_EQUAL_AREA)
        shapes["geometry"] = shapes.geometry.simplify(200)
        shapes[["geometry"]].to_crs("EPSG:4326").to_file(OUT / f"{name}.geojson", driver="GeoJSON",
                                                          COORDINATE_PRECISION=5)
    states = shapes
    sites = pd.read_csv(PROJECT / "outputs" / "tables" / "sites_equity.csv").head(100)
    sites[["rank", "host", "lon", "lat"]].to_csv(OUT / "sites_poorest_first_100.csv", index=False)
    print(f"assets/wtbn: classes {cls.shape}, {len(states)} states, {len(sites)} sites")


def numbers():
    tables = PROJECT / "outputs" / "tables"
    h = json.loads((tables / "headline.json").read_text(encoding="utf-8"))
    checks = pd.read_csv(tables / "integrity_check.csv")
    b100 = next(b for b in h["budgets"] if b["sites"] == 100)
    clinics = next(r for r in h["by_host_100"] if r["hosts"] == "clinics" and r["objective"] == "efficiency")
    sens = {s["setting"]: s for s in h["sensitivity"]}
    k = h["people_by_class_m"]
    return {
        "population_m": h["population_m"],
        "served_m": k["served"], "capacity_m": k["capacity"], "measure_m": k["measure"], "coverage_m": k["coverage"],
        "gap_poorer_pct": h["coverage_gap_poorer_pct"],
        "allyear_untested_pct": h["allyear_gap_untested_pct"],
        "ocid_gap_pct": h["ocid_gap_no_cell5_pct"], "ocid_served_pct": h["ocid_served_no_cell5_pct"],
        "ocid_gsm_pct": h["ocid_gsm_pct"],
        "tiles": h["tiles"], "tests": h["tests"], "tiles_rural": h["tiles_rural"],
        "down_urban": h["down_mbps_urban"], "down_rural": h["down_mbps_rural"],
        "lgas_no_tile": h["lgas_with_no_tile"], "lgas": h["lgas_total"],
        "candidates": h["candidate_cells"]["both"], "clinics": h["facilities"], "schools": h["schools"],
        "reach100_m": round(b100["eff_people"] / 1e6, 2), "reach100_poorer_m": round(b100["eff_poorer"] / 1e6, 2),
        "equity100_m": round(b100["eq_people"] / 1e6, 2), "equity100_poorer_m": round(b100["eq_poorer"] / 1e6, 2),
        "equity_gain": round(b100["poorer_gained_by_equity"], -3), "equity_cost": round(b100["people_given_up_for_equity"], -3),
        "schools100": b100["sites_at_schools"],
        "clinics_only100_m": round(clinics["people"] / 1e6, 2),
        "reach3km_m": sens["site reach 3 km"]["reached_100_m"], "reach10km_m": sens["site reach 10 km"]["reached_100_m"],
        "priority_lgas": [p["lga"] for p in h["priority_lgas"]],
        "checks_passed": int((checks["status"] == "PASS").sum()),
        "checks": int(checks["status"].isin(["PASS", "FAIL"]).sum()),  # NOTE rows are information, not checks
        "quarter": "Q4 2024",
    }


def main():
    assets()
    site = json.loads(SITE.read_text(encoding="utf-8"))
    old = site["projects"].get("where_to_build", {})
    site["projects"]["where_to_build"] = {
        **numbers(),
        "tool": "https://dexsholex.github.io/where-to-build-next/",
        "repo": "https://github.com/Dexsholex/where-to-build-next",
        "summary_pdf": "https://github.com/Dexsholex/where-to-build-next/blob/master/submission/"
                       "DSN_Geospatial_WhereToBuildNext_OluwasolaOyinloye.pdf",
        "as_of": old.get("as_of", "2026-10"),
    }
    SITE.write_text(json.dumps(site, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("content/site.json: projects.where_to_build updated")


if __name__ == "__main__":
    main()
