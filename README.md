# Oluwasola Oyinloye: portfolio site

One-page site for my geospatial consulting practice in Lagos. Plain HTML and CSS,
no JavaScript, no tracking. A small Python script builds it; GitHub Actions
publishes it to GitHub Pages on every push to `main`.

## Edit

- `content/site.json`: name, contact details, links, project facts. A `null`
  value means "not yet"; preview builds show it as a TODO marker and release
  builds leave it out.
- `content/capabilities.json`: the "What I do" list. Add an item to grow it.
  Icons: `orbit`, `network`, `layers`, `check`, `chart`, `pin`.
- `src/index.html` and `src/style.css`: page copy and styles.

## Build and preview

```bash
python tools/build.py
python -m http.server 8000 --directory dist
```

Then open http://localhost:8000. `python tools/build.py --release` builds the
public version without TODO markers (this is what GitHub Actions runs).

## Before every push

```bash
python tools/check.py
```

It checks for names that must never appear on the site (the list lives in
`private/blocked_terms.txt`, which is never committed), filler words, TODO markers
and page weight.

## Share image and icons

`python tools/make_images.py` redraws `static/og.png` and the icons from
`content/site.json`. Run it after changing the name, flagship line or domain.
It needs Pillow and the Windows system fonts.

## Custom domain

Set `base_url` in `content/site.json`, add a `static/CNAME` file containing the
domain, rerun `tools/make_images.py`, then push.
