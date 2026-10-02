# Oluwasola Oyinloye: portfolio site

Site for my geospatial data science and geospatial AI practice in Lagos. Static HTML
and CSS with a little progressive-enhancement JavaScript, built by a small Python
script and published to GitHub Pages by GitHub Actions on every push to `main`.
No cookies, analytics or tracking.

## Layout

```
content/site.json          contacts, links, tools, project figures (null = not yet)
content/capabilities.json  the "What I do" list; add an item to grow it
src/pages/                 one file per page; work/x.html becomes /work/x/
src/partials/              shared layout, header and footer
src/style.css, src/js/     styles and the small enhancement script
assets/                    source photos and GeoAID data (inputs to tools/media.py)
static/                    copied to the site as-is (icons, share images, img/, data/, vendor/)
tools/                     build, image, data and check scripts
```

Icons for `capabilities.json`: `detect`, `drone`, `orbit`, `scatter`, `wave`, `layers`, `check`, `chart`.

## Build and preview

```bash
python tools/build.py
python -m http.server 8000 --directory dist
```

Open http://localhost:8000. Preview builds show missing content as yellow TODO
markers. `python tools/build.py --release` leaves those items out; that is what
GitHub Actions publishes.

## Before every push

```bash
python tools/check.py
```

Checks for names that must never appear (from `private/blocked_terms.txt`, which is
never committed), filler words, TODO markers and page weight.

## Full audit

Needs Node.js and Chrome. Once: `npm install`. Then:

```bash
python tools/build.py --release
npm run audit
```

Runs Lighthouse (mobile and desktop) on every page, takes screenshots at 360, 768
and 1440 px in light and dark mode, checks for horizontal overflow and script
errors, and checks every link. Results go to `reports/` (not committed).

## Images and data

| Command | Makes | Run it after |
|---|---|---|
| `python tools/media.py` | photos, GeoAID map and Access Map preview in `static/img/` | changing photos or crops |
| `python tools/make_images.py` | share images and icons in `static/` | changing name, flagship line, domain or figures |
| `python tools/fetch_osm_health.py` | OpenStreetMap snapshot in `static/data/` | wanting fresher map data |

`fetch_osm_health.py --recount` recomputes the per-LGA counts offline.
Map data © OpenStreetMap contributors (ODbL). Leaflet is self-hosted in
`static/vendor/leaflet/` under its BSD-2-Clause licence.

## Custom domain

Set `base_url` in `content/site.json`, add `static/CNAME` containing the domain,
run `tools/make_images.py`, then push.
