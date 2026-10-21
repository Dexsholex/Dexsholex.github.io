# Oluwasola Oyinloye: portfolio site

Site for my geospatial data science and geospatial AI work in Lagos, in English, French,
Portuguese, Spanish and Arabic. Static HTML and CSS with a little progressive-enhancement
JavaScript, built with Python and Jinja2, tested on every push and published to GitHub
Pages by GitHub Actions. No cookies, analytics or tracking.

## Layout

```
content/site.json            structure: contacts, links, languages, tools, project figures (null = not yet)
content/services.json        services: slug, icon, sectors, related case studies
content/products.json        open products: status (live, building, planned) and links
content/i18n/<lang>/         everything a reader sees, one folder per language:
    ui.json                  interface text and the site's own wording
    services.json            service titles, summaries and full service pages
    products.json            product summaries
src/pages/<lang>/            one Jinja template per page; work/x.html becomes /<lang>/work/x/
src/templates/               base layout, header, footer, service page, shared macros
src/style.css, src/js/       styles and the small enhancement script
assets/                      photos (metadata stripped), GeoAID and Where to Build Next data, inputs to tools/media.py
static/                      copied to the site as-is (icons, share cards, PDFs, img/, data/, vendor/)
tests/                       checks on the built site
tools/                       build, release, image, data and check scripts
```

Service icons: `detect`, `drone`, `orbit`, `forest`, `pin`, `wave`, `layers`, `webmap`, `chart`, `people`.

## Languages

English is served at `/`; French, Portuguese, Spanish and Arabic at `/fr/`, `/pt/`,
`/es/` and `/ar/`. Arabic pages are laid out right to left. A page and its translations
share a path, so the build links them with `hreflang` tags and lists them together in the
sitemap. Visitors pick a language from the menu in the header and the choice is remembered
in their browser. When nothing has been chosen and the browser prefers another language
the site offers, a small note suggests that version. The site never guesses from location.

Every file in `content/i18n/<lang>/` must have exactly the same keys as the English one.
The build stops and lists any differences. To add a language, copy `content/i18n/en/`
and `src/pages/en/` (leaving out `404.html` and the methods log), translate them, and add
the language to `languages` in `content/site.json` and to `FORMATS` in `tools/build.py`.

Translations other than English need review by a native speaker before launch.

## Build and preview

```bash
pip install -r requirements.txt
python tools/build.py
python -m http.server 8000 --directory dist
```

Open http://localhost:8000. Preview builds show missing content as yellow TODO markers.
`python tools/build.py --release` leaves those items out; that is what GitHub Actions publishes.

## Tests

```bash
python -m unittest discover -s tests -v
```

Builds the release site and checks every page: one `h1`, title and description lengths,
canonical URLs, `hreflang` pairs that point both ways, structured data, the content
security policy (inline code must match its hashes), no inline styles, image sizes and
alt text, internal links and anchors, the sitemap, and translation coverage.

## Release

```bash
python tools/release.py
```

Runs the tests, then `tools/check.py` (names that must never appear, read from
`private/blocked_terms.txt`, which is never committed; filler words; page weight).
Add `--audit` for the full audit below and `--push` to push `main` once everything passes.
GitHub Actions then runs the tests and Lighthouse again before it deploys.

## Full audit

Needs Node.js and Chrome. Once: `npm install`. Then:

```bash
python tools/build.py --release
npm run audit
```

Checks every page at 360, 768 and 1440 px for horizontal overflow and script errors, and
checks every link. Lighthouse (mobile and desktop) and screenshots in light and dark run on
a sample of pages in every language; `AUDIT_ALL=1 npm run audit` covers all of them.
Results go to `reports/` (not committed).

## Images, PDFs and data

| Command | Makes | Run it after |
|---|---|---|
| `python tools/media.py` | photos, GeoAID map, Where to Build Next map and Access Map preview in `static/img/` | changing photos or crops |
| `npm run og` | share cards for every language in `static/` | changing the flagship line, card text, domain or figures |
| `npm run pdf` | one-page capability statement PDF per language in `static/` (fails if any runs past a page) | changing services, figures or the statement; build first, then build again |
| `python tools/make_images.py` | favicon and touch icon in `static/` | changing the brand mark |
| `python tools/fetch_osm_health.py` | OpenStreetMap snapshot in `static/data/` | wanting fresher map data |
| `python tools/import_media.py` | metadata-free photo masters in `assets/field/`, video clips in `static/media/` | adding field photos or video (edit the list at the top) |
| `python tools/import_wtbn.py` | Where to Build Next map inputs in `assets/wtbn/` and its numbers in `content/site.json`, from the local project folder | rebuilding that project; then run `media.py` |
| `python tools/import_methods_log.py` | the GeoAID methods log page (English), copied from GitHub | the log changes in the GeoAID repo |

The content tools need `pip install -r requirements-tools.txt`.
`fetch_osm_health.py --recount` recomputes the per-LGA counts offline.
Map data © OpenStreetMap contributors (ODbL). Leaflet is self-hosted in
`static/vendor/leaflet/` under its BSD-2-Clause licence.

## Adding a product

Add an entry to `content/products.json` and its text to `content/i18n/<lang>/products.json`
in every language. For a full page, add `src/pages/<lang>/products/<name>.html` in each
language (copy a case study page as a starting point); it is published at `/products/<name>/`.

## Custom domain

Set `base_url` in `content/site.json`, add `static/CNAME` containing the domain,
run `npm run og` and `npm run pdf`, then release.
