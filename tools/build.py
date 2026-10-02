#!/usr/bin/env python3
"""Build the site into dist/.

    python tools/build.py            preview build: missing values show as TODO markers
    python tools/build.py --release  public build: missing values are left out quietly

Edit content/site.json (contacts, links, project facts) and
content/capabilities.json (the "What I do" list). The page itself is
src/index.html; {{ tokens }} in it are filled from those files. Standard
library only, so it runs anywhere Python 3.9+ does, including GitHub Actions.
"""
import argparse
import datetime as dt
import gzip
import html
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, CONTENT, STATIC, DIST = (ROOT / d for d in ("src", "content", "static", "dist"))
TOKEN = re.compile(r"\{\{\s*(\w+)\s*\}\}")
OUT_ICON = '<svg aria-hidden="true" focusable="false"><use href="#i-out"/></svg>'


def esc(s):
    return html.escape(str(s), quote=True)


class Missing:
    """Collects gaps. Preview builds show a TODO marker; release builds show the fallback."""

    def __init__(self, release):
        self.release = release
        self.items = []

    def mark(self, label, fallback=""):
        self.items.append(label)
        return fallback if self.release else f'<span class="todo">TODO: {esc(label)}</span>'


def ext_link(url, text):
    return f'<a href="{esc(url)}">{esc(text)}{OUT_ICON}</a>'


def fragments(site, caps, gaps):
    links, proj = site["links"], site["projects"]
    f = {}

    wa_text = urllib.parse.quote(site["call_message"])
    f["whatsapp_url"] = esc(f"https://wa.me/{site['whatsapp']}?text={wa_text}")
    f["mailto_url"] = esc(f"mailto:{site['email']}?subject={urllib.parse.quote('20-minute call')}")

    rg = links.get("researchgate")
    if rg:
        f["publications_label"] = f'<a href="{esc(rg)}" rel="me">publications on ResearchGate</a>'
        f["researchgate_item"] = f'<li><span class="k">ResearchGate</span><a href="{esc(rg)}" rel="me">Publications</a></li>'
    else:
        m = gaps.mark("ResearchGate URL")
        f["publications_label"] = "publications on ResearchGate" + (f" {m}" if m else "")
        f["researchgate_item"] = f'<li><span class="k">ResearchGate</span>{m}</li>' if m else ""

    rows = []
    for key, label, todo in (("oil_palm_scale", "Scale", "client-approved scale numbers"),
                             ("oil_palm_accuracy", "Accuracy", "validated accuracy figure")):
        if proj.get(key):
            rows.append(f"<div><dt>{label}</dt><dd>{esc(proj[key])}</dd></div>")
        else:
            m = gaps.mark(todo)
            if m:
                rows.append(f"<div><dt>{label}</dt><dd>{m}</dd></div>")
    f["oil_palm_rows"] = "\n            ".join(rows)

    if proj.get("access_map_build"):
        f["access_map_link"] = ext_link(proj["access_map_build"], "Follow the build")
    else:
        f["access_map_link"] = gaps.mark('"Follow the build" link')

    geo = []
    if proj.get("geoaid_dashboard"):
        geo.append(ext_link(proj["geoaid_dashboard"], "Open the live dashboard"))
    else:
        geo.append(gaps.mark("GeoAID dashboard URL"))
    if proj.get("geoaid_repo"):
        geo.append(ext_link(proj["geoaid_repo"], "Read the code"))
    else:
        geo.append(gaps.mark("GeoAID repo URL"))
    f["geoaid_links"] = "".join(geo)

    shot = site.get("headshot")
    if shot:
        f["about_class"] = " has-photo"
        f["about_photo"] = (
            f'<div class="about-photo"><img src="{esc(shot["src"])}" width="{shot["width"]}" '
            f'height="{shot["height"]}" alt="{esc(shot["alt"])}" loading="lazy" decoding="async"></div>')
    else:
        m = gaps.mark("headshot (or decide: no photo)")
        f["about_class"] = " has-photo" if m else ""
        f["about_photo"] = f'<div class="about-photo"><div class="photo-todo">{m}</div></div>' if m else ""

    items = []
    for c in caps:
        items.append(
            '        <li>\n'
            f'          <span class="icon"><svg aria-hidden="true" focusable="false"><use href="#i-{esc(c["icon"])}"/></svg></span>\n'
            f'          <h3>{esc(c["title"])}</h3>\n'
            f'          <p>{esc(c["text"])}</p>\n'
            '        </li>')
    f["capabilities"] = "\n".join(items)

    meta = []
    sc = site.get("search_console") or {}
    if sc.get("google"):
        meta.append(f'<meta name="google-site-verification" content="{esc(sc["google"])}">')
    if sc.get("bing"):
        meta.append(f'<meta name="msvalidate.01" content="{esc(sc["bing"])}">')
    f["verification_meta"] = "\n".join(meta)
    return f


def jsonld(site, caps):
    base = site["base_url"]
    person_id, service_id = base + "#person", base + "#service"
    same_as = [u for u in site["links"].values() if u]
    address = {"@type": "PostalAddress", "addressLocality": site["locality"], "addressCountry": site["country_code"]}
    skills = [c["title"] for c in caps]
    ilorin = {"@type": "CollegeOrUniversity", "name": "University of Ilorin"}
    miva = {"@type": "CollegeOrUniversity", "name": "Miva Open University"}
    person = {
        "@type": "Person",
        "@id": person_id,
        "name": site["name"],
        "jobTitle": site["job_title"],
        "url": base,
        "email": "mailto:" + site["email"],
        "telephone": "+" + site["whatsapp"],
        "address": address,
        "alumniOf": [ilorin, miva],
        "hasCredential": [
            {"@type": "EducationalOccupationalCredential", "credentialCategory": "degree",
             "name": "BSc Surveying and Geoinformatics", "recognizedBy": ilorin},
            {"@type": "EducationalOccupationalCredential", "credentialCategory": "degree",
             "name": "Master of Information Technology (MIT), AI specialisation", "recognizedBy": miva},
        ],
        "knowsAbout": skills,
        "sameAs": same_as,
    }
    if site.get("headshot"):
        person["image"] = base + site["headshot"]["src"]
    graph = [
        person,
        {
            "@type": "ProfessionalService",
            "@id": service_id,
            "name": site["name"],
            "description": site["description"],
            "url": base,
            "image": base + "og.png",
            "email": "mailto:" + site["email"],
            "telephone": "+" + site["whatsapp"],
            "address": address,
            "areaServed": {"@type": "Country", "name": site["country"]},
            "founder": {"@id": person_id},
            "knowsAbout": skills,
            "sameAs": same_as,
        },
        {
            "@type": "WebSite",
            "@id": base + "#website",
            "url": base,
            "name": site["name"],
            "inLanguage": "en",
            "publisher": {"@id": person_id},
        },
        {
            "@type": "WebPage",
            "@id": base + "#webpage",
            "url": base,
            "name": site["title"],
            "description": site["description"],
            "isPartOf": {"@id": base + "#website"},
            "about": {"@id": person_id},
            "mainEntity": {"@id": service_id},
            "primaryImageOfPage": {"@type": "ImageObject", "url": base + "og.png", "width": 1200, "height": 630},
            "inLanguage": "en",
        },
    ]
    text = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)
    return text.replace("</", "<\\/")


def minify_css(css):
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,>])\s*", r"\1", css)
    css = re.sub(r":\s+", ":", css)  # safe here: no pseudo-selectors follow a space in this file
    return css.replace(";}", "}").strip()


def render(template, values):
    def sub(m):
        key = m.group(1)
        if key not in values:
            sys.exit(f"build: no value for token '{{{{ {key} }}}}'")
        return str(values[key])
    return TOKEN.sub(sub, template)


def last_modified():
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs"], cwd=ROOT, capture_output=True, text=True, check=True)
        if out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        pass
    return dt.date.today().isoformat()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", action="store_true", help="leave out missing items instead of showing TODO markers")
    args = ap.parse_args()

    site = json.loads((CONTENT / "site.json").read_text(encoding="utf-8"))
    caps = json.loads((CONTENT / "capabilities.json").read_text(encoding="utf-8"))
    if not site["base_url"].endswith("/"):
        sys.exit("build: base_url must end with '/'")

    gaps = Missing(args.release)
    css = minify_css((SRC / "style.css").read_text(encoding="utf-8"))
    values = {
        "title": esc(site["title"]),
        "description": esc(site["description"]),
        "og_title": esc(f'{site["name"]}: {site["flagship"]}'),
        "og_image_alt": esc(f'{site["name"]}, geospatial data scientist in Lagos, Nigeria. "{site["flagship"]}"'),
        "base_url": esc(site["base_url"]),
        "name": esc(site["name"]),
        "flagship": esc(site["flagship"]),
        "email": esc(site["email"]),
        "whatsapp_display": esc(site["whatsapp_display"]),
        "linkedin": esc(site["links"]["linkedin"]),
        "github": esc(site["links"]["github"]),
        "medium": esc(site["links"]["medium"]),
        "year": dt.date.today().year,
        "css": css,
        "jsonld": jsonld(site, caps),
    }
    values.update(fragments(site, caps, gaps))

    # Empty dist/ rather than deleting it: on Windows a folder that a shell or
    # the preview server has open cannot be removed.
    DIST.mkdir(exist_ok=True)
    for p in DIST.iterdir():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    shutil.copytree(STATIC, DIST, dirs_exist_ok=True)

    page = render((SRC / "index.html").read_text(encoding="utf-8"), values)
    (DIST / "index.html").write_text(page, encoding="utf-8", newline="\n")
    (DIST / "404.html").write_text(render((SRC / "404.html").read_text(encoding="utf-8"), values),
                                   encoding="utf-8", newline="\n")

    base = site["base_url"]
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base}sitemap.xml\n", encoding="utf-8", newline="\n")
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url>\n    <loc>{esc(base)}</loc>\n    <lastmod>{last_modified()}</lastmod>\n  </url>\n"
        "</urlset>\n", encoding="utf-8", newline="\n")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    raw = len(page.encode("utf-8"))
    total = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"Built {'release' if args.release else 'preview'} -> {DIST}")
    print(f"  index.html: {raw / 1024:.1f} KB raw, {len(gzip.compress(page.encode('utf-8'))) / 1024:.1f} KB gzipped")
    print(f"  dist total: {total / 1024:.1f} KB (includes share image and icons, which the page itself does not load)")
    if gaps.items:
        verb = "left out" if args.release else "shown as TODO"
        print(f"  {len(gaps.items)} missing item(s) {verb}:")
        for g in gaps.items:
            print(f"    - {g}")


if __name__ == "__main__":
    main()
