#!/usr/bin/env python3
"""Build the site into dist/.

    python tools/build.py            preview build: missing values show as TODO markers
    python tools/build.py --release  public build: missing values are left out quietly

Content lives in content/site.json and content/capabilities.json. Pages are
src/pages/**/*.html; each starts with a JSON front-matter comment and is wrapped in
src/partials/layout.html. {{ tokens }} are filled from the content files, from the
page's own front matter and from the fragments built below. pages/index.html becomes
/, pages/work/x.html becomes /work/x/. Standard library only, so it runs anywhere
Python 3.9+ does, including GitHub Actions.
"""
import argparse
import datetime as dt
import gzip
import hashlib
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
FRONT = re.compile(r"\A<!--page\s*(\{.*?\})\s*-->\s*", re.S)
BLANK_GIF = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
CATEGORY_LABELS = ["Hospital", "Clinic or doctor", "Clinic or doctor", "Pharmacy", "Other"]
CATEGORY_SLOT = [0, 1, 1, 2, 3]  # hospital, clinic, doctors, pharmacy, other -> legend slot


def esc(s):
    return html.escape(str(s), quote=True)


def icon(name, cls=""):
    c = f' class="{cls}"' if cls else ""
    return f'<svg{c} aria-hidden="true" focusable="false"><use href="#i-{name}"/></svg>'


class Missing:
    """Collects gaps. Preview builds show a TODO marker; release builds show the fallback."""

    def __init__(self, release):
        self.release = release
        self.items = []

    def mark(self, label, fallback=""):
        if label not in self.items:
            self.items.append(label)
        return fallback if self.release else f'<span class="todo">TODO: {esc(label)}</span>'


# ---------- images ----------
def picture(manifest, name, alt, sizes, cls="", eager=False, hide_below=None):
    variants = manifest[name]
    big = variants[-1]
    default = variants[min(1, len(variants) - 1)]["src"]
    srcset = ", ".join(f'{v["src"]} {v["w"]}w' for v in variants)
    load = ' fetchpriority="high"' if eager else ' loading="lazy"'
    c = f' class="{cls}"' if cls else ""
    img = (f'<img{c} src="{default}" srcset="{srcset}" sizes="{sizes}" width="{big["w"]}" height="{big["h"]}" '
           f'alt="{esc(alt)}"{load} decoding="async">')
    if hide_below:  # small screens get a 1px gif instead of downloading a photo they never show
        return f'<picture><source media="(max-width: {hide_below - 1}px)" srcset="{BLANK_GIF}">{img}</picture>'
    return img


def fixed_img(manifest, name, alt, cls="", size=None):
    v = manifest[name]
    one, two = v[0], v[-1]
    s = size or one["w"]
    return (f'<img class="{cls}" src="{one["src"]}" srcset="{two["src"]} 2x" width="{s}" height="{s}" '
            f'alt="{esc(alt)}" loading="lazy" decoding="async">')


# ---------- fragments ----------
def phone_display(number):
    """+234 909 000 0000 for Nigerian numbers, otherwise +<digits>."""
    d = "".join(ch for ch in str(number) if ch.isdigit())
    if d.startswith("234") and len(d) == 13:
        return f"+234 {d[3:6]} {d[6:9]} {d[9:]}"
    return "+" + d


def service_cards(services, exclude=None):
    items = []
    for c in services["services"]:
        if c["slug"] == exclude:
            continue
        items.append(
            f'<li data-reveal data-sectors="{" ".join(c["sectors"])}"><a class="service-link" href="/services/{c["slug"]}/">'
            f'<span class="icon">{icon(esc(c["icon"]))}</span><h3>{esc(c["title"])}</h3><p>{esc(c["short"])}</p>'
            f'<span class="service-more">How it works{icon("arrow")}</span></a></li>')
    return "\n".join(items)


def service_fragments(services):
    chips = ['<button type="button" aria-pressed="true" data-sector="all">All sectors</button>']
    chips += [f'<button type="button" aria-pressed="false" data-sector="{k}">{esc(v)}</button>'
              for k, v in services["sectors"].items()]
    return {
        "capabilities": service_cards(services),
        "sector_filter": ('<div class="sector-filter" role="group" aria-label="Show services for a sector" '
                          f'data-sector-filter hidden>{"".join(chips)}</div>'
                          '<p class="visually-hidden" aria-live="polite" data-sector-status></p>'),
        "sectors_list": "".join(f"<li>{esc(v)}</li>" for v in services["sectors"].values()),
        "services_also": esc(services["also"]),
        "footer_services": "\n".join(f'        <li><a href="/services/{c["slug"]}/">{esc(c["title"])}</a></li>'
                                     for c in services["services"]),
        "brief_builder": brief_html(services),
        "cap_services": "\n".join(f'        <li><strong>{esc(c["title"])}.</strong> {esc(c["short"])}</li>'
                                  for c in services["services"]),
    }


def testimonials_html(items, gaps):
    if not items:
        m = gaps.mark("client testimonial (anonymised, with the client's permission)")
        if not m:
            return ""
        return ('<section class="section testimonials" aria-labelledby="t-title"><div class="wrap">'
                '<header class="section-head"><p class="eyebrow">Clients</p><h2 id="t-title">What clients say</h2></header>'
                f'<p>{m}</p></div></section>')
    quotes = []
    for t in items:
        link = f' · <a href="{esc(t["link"])}">{esc(t.get("link_label", "Case study"))}</a>' if t.get("link") else ""
        quotes.append(f'<li data-reveal><figure><blockquote><p>{esc(t["quote"])}</p></blockquote>'
                      f'<figcaption><strong>{esc(t["role"])}</strong><span>{esc(t["org"])}{link}</span></figcaption>'
                      '</figure></li>')
    return ('<section class="section testimonials" aria-labelledby="t-title"><div class="wrap">'
            '<header class="section-head"><p class="eyebrow">Clients</p><h2 id="t-title">What clients say</h2></header>'
            f'<ul class="quotes">{"".join(quotes)}</ul></div></section>')


def brief_html(services):
    """Request builder. It only composes an email in the visitor's own mail app; the site sends and stores nothing."""
    svc = "".join(f'<label class="pick"><input type="checkbox" name="service" value="{esc(c["title"])}">'
                  f'<span>{esc(c["title"])}</span></label>' for c in services["services"])
    svc += '<label class="pick"><input type="checkbox" name="service" value="Something else"><span>Something else</span></label>'

    def radios(name, options):
        return "".join(f'<label class="pick"><input type="radio" name="{name}" value="{esc(o)}"><span>{esc(o)}</span></label>'
                       for o in options)

    def checks(name, options):
        return "".join(f'<label class="pick"><input type="checkbox" name="{name}" value="{esc(o)}"><span>{esc(o)}</span></label>'
                       for o in options)

    return f"""<form class="brief" data-brief data-email="__EMAIL__" hidden aria-labelledby="brief-title">
      <div class="brief-head">
        <h3 id="brief-title">Prefer to write it down first?</h3>
        <p>Tick what applies and your email app opens with a short brief, ready to send. Nothing is sent or stored by this site.</p>
      </div>
      <fieldset><legend>What do you need?</legend><div class="picks">{svc}</div></fieldset>
      <fieldset><legend>Where is the site?</legend><div class="picks">{radios("where", ["Nigeria", "Elsewhere in Africa", "Outside Africa"])}</div>
        <label class="brief-text">Place (optional)<input type="text" name="place" autocomplete="off" placeholder="City, state or country"></label></fieldset>
      <fieldset><legend>When?</legend><div class="picks">{radios("when", ["As soon as possible", "Within 3 months", "Just exploring"])}</div></fieldset>
      <fieldset><legend>Data you already have</legend><div class="picks">{checks("data", ["Drone or aerial imagery", "Satellite imagery", "GIS files or maps", "Spreadsheets with locations", "Nothing yet"])}</div></fieldset>
      <label class="brief-text">What do you need to decide? (optional)<textarea name="decide" rows="3" placeholder="One or two sentences"></textarea></label>
      <div class="brief-actions">
        <button class="btn" type="submit">{icon("mail")}Open in my email app</button>
        <button class="btn btn-ghost" type="button" data-brief-copy>{icon("copy")}Copy the brief</button>
        <span class="brief-status" aria-live="polite"></span>
      </div>
    </form>"""


def faq_html(faq):
    return "\n".join(f'<details class="faq"><summary>{esc(item["q"])}</summary><p>{esc(item["a"])}</p></details>'
                     for item in faq)


def gallery_item(manifest, name, alt, caption, shape="wide"):
    full = manifest[name][-1]["src"]
    sizes = "(min-width: 1024px) 380px, (min-width: 600px) 46vw, 92vw"
    return (f'<figure class="g-{shape}"><a class="zoomable" href="{full}" data-lightbox>'
            f'{picture(manifest, name, alt, sizes)}</a><figcaption>{esc(caption)}</figcaption></figure>')


def gallery_video(name, label, caption):
    return (f'<figure class="g-tall"><video controls preload="none" playsinline width="720" height="1280" '
            f'poster="/media/{name}-poster.webp" aria-label="{esc(label)}">'
            f'<source src="/media/{name}.mp4" type="video/mp4"></video><figcaption>{esc(caption)}</figcaption></figure>')


STATUS = {"live": "Live", "building": "In development", "planned": "Planned"}
NEXT_PRODUCT = (
    '<li class="product product-next" data-reveal><span class="status status-planned">Next</span>'
    "<h3>Your question, as a public tool?</h3>"
    "<p>I build open products where good data can help many people at once. If you hold data, fund public-good "
    "work or have a question worth answering in the open, let's talk.</p>"
    '<p class="case-links"><a href="#contact">Get in touch{arrow}</a></p></li>')


def products_html(products):
    cards = []
    for p in products:
        links = "".join(
            f'<a href="{esc(l["url"])}">{esc(l["label"])}{icon("out" if l.get("external") else "arrow")}</a>'
            for l in p["links"])
        tags = "".join(f'<li class="tag tag-quiet">{esc(t)}</li>' for t in p["tags"])
        cards.append(
            f'<li class="product" data-reveal><div class="product-top"><span class="status status-{esc(p["status"])}">'
            f'{STATUS[p["status"]]}</span><ul class="tags" aria-label="Topics">{tags}</ul></div>'
            f'<h3>{esc(p["name"])}</h3><p>{esc(p["summary"])}</p>'
            f'<p class="product-for"><span>For</span>{esc(p["for"])}</p><p class="case-links">{links}</p></li>')
    cards.append(NEXT_PRODUCT.format(arrow=icon("arrow")))
    return "\n".join(cards)


def fragments(site, caps, osm, manifest, gaps, products):
    links, proj, palm = site["links"], site["projects"], site["projects"]["oil_palm"]
    f = {}

    # WhatsApp appears only when a (business) number is set in site.json; "whatsapp": null hides it everywhere
    wa_number = site.get("whatsapp")
    if wa_number:
        greeting = f"Hello {site['name'].split()[0]}, I'd like to book a 20-minute call."
        wa = esc(f"https://wa.me/{wa_number}?text={urllib.parse.quote(greeting)}")
        f["whatsapp_button"] = f'<a class="btn btn-ghost" href="{wa}">{icon("chat")}WhatsApp</a>'
        f["whatsapp_item"] = (f'<li><span class="k">WhatsApp</span><span class="v">'
                              f'<a href="{wa}">{esc(phone_display(wa_number))}</a></span></li>')
        f["whatsapp_footer"] = f'<li><a href="{wa}">WhatsApp {esc(phone_display(wa_number))}</a></li>'
        f["privacy_services"] = "WhatsApp, LinkedIn, GitHub, Medium and the GeoAID dashboard on Streamlit"
    else:
        f["whatsapp_button"] = f["whatsapp_item"] = f["whatsapp_footer"] = ""
        f["privacy_services"] = "LinkedIn, GitHub, Medium and the GeoAID dashboard on Streamlit"
    # Email works for clients anywhere; the body prompts for what a first call needs, time zone included
    body = site["call_body"].replace("\n", "\r\n")
    book = f"mailto:{site['email']}?subject={urllib.parse.quote(site['call_subject'])}&body={urllib.parse.quote(body)}"
    f["call_url"] = esc(site.get("booking_url") or book)
    f["email_book_url"] = esc(book)
    f["mailto_url"] = esc(f"mailto:{site['email']}")
    # With a booking link (Cal.com, Calendly) the main button picks a time and email becomes the alternative
    if site.get("booking_url"):
        f["contact_actions"] = (f'<a class="btn" href="{esc(site["booking_url"])}">{icon("chat")}Pick a time</a>'
                                f'<a class="btn btn-ghost" href="{f["email_book_url"]}">{icon("mail")}Email me</a>'
                                + f["whatsapp_button"])
    else:
        f["contact_actions"] = f'<a class="btn" href="{f["email_book_url"]}">{icon("mail")}Book by email</a>' + f["whatsapp_button"]
    f["roles_line"] = esc(" · ".join(site["roles"]))
    f["roles_br"] = "<br>".join(esc(r) for r in site["roles"])
    f["roles_sentence"] = esc(" and ".join(r[0].lower() + r[1:] for r in site["roles"]))

    rg = links.get("researchgate")
    if rg:
        f["publications_label"] = f'<a href="{esc(rg)}" rel="me">publications on ResearchGate</a>'
        f["researchgate_item"] = (f'<li><span class="k">ResearchGate</span><span class="v">'
                                  f'<a href="{esc(rg)}" rel="me">Publications</a></span></li>')
        f["researchgate_footer"] = f'<li><a href="{esc(rg)}" rel="me">ResearchGate</a></li>'
    else:
        m = gaps.mark("ResearchGate URL")
        f["publications_label"] = "publications on ResearchGate" + (f" {m}" if m else "")
        f["researchgate_item"] = f'<li><span class="k">ResearchGate</span><span class="v">{m}</span></li>' if m else ""
        f["researchgate_footer"] = ""

    # Oil palm
    for k, v in palm.items():
        if isinstance(v, str):
            f[f"palm_{k}"] = esc(v)
    f["palm_repo_link"] = f'<a href="{esc(palm["repo"])}">Read the code{icon("out")}</a>'
    if palm.get("accuracy"):
        f["palm_accuracy_row"] = f'<div><dt>Counting accuracy</dt><dd>{esc(palm["accuracy"])}</dd></div>'
    else:
        m = gaps.mark("validated counting accuracy figure")
        f["palm_accuracy_row"] = f"<div><dt>Counting accuracy</dt><dd>{m}</dd></div>" if m else ""
    chip = (f'<span class="media-chip"><b>{esc(palm["palms"])}</b> palms<i></i><b>{esc(palm["hectares"])}</b> ha'
            f'<i></i><b>{esc(palm["blocks"])}</b> blocks</span>')
    pad_alt = "A survey drone on its landing pad at the edge of an oil palm estate, with mature palms behind it"
    f["palm_media"] = picture(manifest, "palm-drone-pad", pad_alt, "(min-width: 900px) 560px, 92vw") + chip
    f["palm_hero"] = picture(manifest, "palm-drone-pad", pad_alt, "(min-width: 1200px) 1152px, 96vw", eager=True)
    f["palm_hero_full"] = manifest["palm-drone-pad"][-1]["src"]
    f["palm_gallery"] = "\n".join([
        gallery_item(manifest, "palm-pilot",
                     "Oluwasola Oyinloye checking the flight plan on a drone controller in the field",
                     "Planning the flight on site", "tall"),
        gallery_video("palm-takeoff", "The survey drone taking off from its case and climbing over the palms",
                      "Take-off for a mapping flight (14 s, no sound)"),
        gallery_item(manifest, "palm-gnss", "A GNSS receiver on a tripod in low vegetation on the estate",
                     "A GNSS receiver set up on the estate"),
        gallery_item(manifest, "palm-estate-road",
                     "A straight laterite road running through the plantation to the horizon",
                     "The scale of the estate"),
        gallery_item(manifest, "palm-crown", "A mature oil palm with a full crown of fronds",
                     "A mature crown: what the model learns to find"),
    ])

    # Access Map
    if proj.get("access_map_build"):
        f["access_map_link"] = f'<a href="{esc(proj["access_map_build"])}">Follow the build{icon("out")}</a>'
    else:
        f["access_map_link"] = gaps.mark('"Follow the build" link')
    pulled = dt.date.fromisoformat(osm["pulled"])
    f["osm_pulled"] = f"{pulled.day} {pulled.strftime('%B %Y')}"
    f["osm_count"] = f'{len(osm["facilities"]):,}'
    f["osm_table"] = osm_table(osm)

    # GeoAID
    f["geoaid_dashboard"] = esc(proj["geoaid_dashboard"])
    f["geoaid_repo"] = esc(proj["geoaid_repo"])
    f["geoaid_methods"] = esc(proj["geoaid_methods"])
    f["geoaid_docs_repo"] = esc(proj["geoaid_docs_repo"])

    # Images
    f["img_portrait"] = picture(manifest, "portrait", f"Portrait of {site['name']}",
                                "(min-width: 1200px) 400px, (min-width: 880px) 34vw, 1px", eager=True, hide_below=880)
    f["img_avatar"] = fixed_img(manifest, "avatar", "", "avatar", 56)
    f["img_about"] = picture(manifest, "about", f"{site['name']} seated, smiling, in a white shirt",
                             "(min-width: 880px) 340px, (min-width: 600px) 45vw, 92vw")
    f["img_contact"] = fixed_img(manifest, "contact", f"{site['name']}", "contact-avatar", 64)
    f["img_geoaid"] = picture(manifest, "geoaid-flood",
                              "Map of modelled flood probability across Amuwo-Odofin, from dark blue (lower) "
                              "to light blue (higher), inside the LGA boundary.",
                              "(min-width: 1100px) 560px, (min-width: 720px) 50vw, 92vw")
    f["img_geoaid_large"] = picture(manifest, "geoaid-flood",
                                    "Map of modelled flood probability across Amuwo-Odofin, from dark blue (lower) "
                                    "to light blue (higher), inside the LGA boundary.",
                                    "(min-width: 1100px) 1000px, 92vw", eager=True)
    f["geoaid_full"] = manifest["geoaid-flood"][-1]["src"]
    f["img_access_preview"] = picture(manifest, "access-map-preview",
                                      "Static map of Lagos State's 20 LGAs with dots for each health facility "
                                      "tagged in OpenStreetMap; most dots sit in the western and central LGAs.",
                                      "(min-width: 1100px) 1100px, 96vw", cls="map-preview")

    # Tools
    f["cap_tools"] = " ".join(f"<b>{esc(g)}:</b> {esc(', '.join(items))}." for g, items in site["tools"].items())
    f["site_host"] = esc(site["base_url"].split("//", 1)[-1].rstrip("/"))
    f["today_month"] = dt.date.today().strftime("%B %Y")
    f["tools"] = "\n".join(
        f'<div class="tool-group"><h4>{esc(group)}</h4><ul class="chips">'
        + "".join(f"<li>{esc(t)}</li>" for t in items) + "</ul></div>"
        for group, items in site["tools"].items())
    f["products"] = products_html(products)

    meta = []
    sc = site.get("search_console") or {}
    if sc.get("google"):
        meta.append(f'<meta name="google-site-verification" content="{esc(sc["google"])}">')
    if sc.get("bing"):
        meta.append(f'<meta name="msvalidate.01" content="{esc(sc["bing"])}">')
    f["verification_meta"] = "\n".join(meta)
    return f


def osm_table(osm):
    rows = []
    for feat in osm["lgas"]["features"]:
        p = feat["properties"]
        c = p.get("counts")
        if not c:
            continue
        slots = [0, 0, 0, 0]
        for i, n in enumerate(c):
            slots[CATEGORY_SLOT[i]] += n
        rows.append((p["name"], slots))
    rows.sort(key=lambda r: -sum(r[1]))
    body = "".join(f"<tr><th scope=row>{esc(n)}</th>" + "".join(f"<td>{v}</td>" for v in s) +
                   f"<td>{sum(s)}</td></tr>" for n, s in rows)
    head = "".join(f"<th scope=col>{h}</th>" for h in ("LGA", "Hospital", "Clinic or doctor", "Pharmacy", "Other", "Total"))
    return (f"<div class=\"table-scroll\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
            if rows else "")


# ---------- structured data ----------
def person_and_service(site, caps, manifest):
    """Person and ProfessionalService nodes shared by every page's structured data."""
    base = site["base_url"]
    same_as = [u for u in site["links"].values() if u]
    address = {"@type": "PostalAddress", "addressLocality": site["locality"], "addressCountry": site["country_code"]}
    skills = [c["title"] for c in caps]
    ilorin = {"@type": "CollegeOrUniversity", "name": "University of Ilorin"}
    miva = {"@type": "CollegeOrUniversity", "name": "Miva Open University"}
    person = {
        "@type": "Person", "@id": base + "#person", "name": site["name"], "jobTitle": site["roles"],
        "url": base, "image": base.rstrip("/") + manifest["portrait"][-1]["src"],
        "email": "mailto:" + site["email"], "address": address,
        "alumniOf": [ilorin, miva],
        "hasCredential": [
            {"@type": "EducationalOccupationalCredential", "credentialCategory": "degree",
             "name": "BSc Surveying and Geoinformatics", "recognizedBy": ilorin},
            {"@type": "EducationalOccupationalCredential", "credentialCategory": "degree",
             "name": "Master of Information Technology (MIT), AI specialisation", "recognizedBy": miva},
        ],
        "knowsAbout": skills + [t for group in site["tools"].values() for t in group], "knowsLanguage": "en",
        "sameAs": same_as,
    }
    if site.get("whatsapp"):
        person["telephone"] = "+" + str(site["whatsapp"])
    service = {
        "@type": "ProfessionalService", "@id": base + "#service", "name": site["name"],
        "description": site["description"], "url": base, "image": base + "og.png",
        "email": "mailto:" + site["email"], "address": address,
        "areaServed": [{"@type": "Country", "name": "Nigeria"}, {"@type": "Continent", "name": "Africa"},
                       {"@type": "Place", "name": "Worldwide"}],
        "availableLanguage": "en", "founder": {"@id": base + "#person"},
        "knowsAbout": skills, "sameAs": same_as,
        "hasOfferCatalog": {
            "@type": "OfferCatalog", "name": "GIS and geospatial services",
            "itemListElement": [{"@type": "Offer", "itemOffered": {
                "@type": "Service", "name": c["title"], "description": c["short"],
                "url": base + "services/" + c["slug"] + "/"}} for c in caps]},
    }
    if site.get("whatsapp"):
        service["telephone"] = person["telephone"]
    return person, service


def jsonld(page, site, caps, manifest):
    base = site["base_url"]
    url = base.rstrip("/") + page["path"]
    person, service = person_and_service(site, caps, manifest)
    website = {"@type": "WebSite", "@id": base + "#website", "url": base, "name": site["name"],
               "inLanguage": "en", "publisher": {"@id": base + "#person"}}
    if page["kind"] == "home":
        graph = [person, service, website, {
            "@type": "WebPage", "@id": url + "#webpage", "url": url, "name": page["title"],
            "description": page["description"], "isPartOf": {"@id": base + "#website"},
            "about": {"@id": base + "#person"}, "mainEntity": {"@id": base + "#service"},
            "primaryImageOfPage": {"@type": "ImageObject", "url": base + page["og_image"], "width": 1200, "height": 630},
            "inLanguage": "en"}]
    elif page["kind"] == "case":
        graph = [person, website, {
            "@type": "Article", "@id": url + "#article", "url": url, "headline": page["headline"],
            "description": page["description"], "image": base + page["og_image"],
            "author": {"@id": base + "#person"}, "publisher": {"@id": base + "#person"},
            "datePublished": page["published"], "dateModified": page.get("modified", page["published"]),
            "isPartOf": {"@id": base + "#website"}, "inLanguage": "en", "keywords": page.get("keywords", [])},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": base},
                {"@type": "ListItem", "position": 2, "name": "Case studies", "item": base + "#work"},
                {"@type": "ListItem", "position": 3, "name": page["crumb"], "item": url}]}]
    elif page["kind"] == "service":
        area = [{"@type": "Country", "name": "Nigeria"}, {"@type": "Continent", "name": "Africa"},
                {"@type": "Place", "name": "Worldwide"}]
        graph = [person, service, website, {
            "@type": "Service", "@id": url + "#service", "url": url, "name": page["headline"],
            "serviceType": page["headline"], "description": page["description"],
            "provider": {"@id": base + "#service"}, "areaServed": area, "availableLanguage": "en"},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": base},
                {"@type": "ListItem", "position": 2, "name": "Services", "item": base + "services/"},
                {"@type": "ListItem", "position": 3, "name": page["crumb"], "item": url}]}]
        if page.get("faq"):
            graph.append({"@type": "FAQPage", "@id": url + "#faq", "mainEntity": [
                {"@type": "Question", "name": item["q"], "acceptedAnswer": {"@type": "Answer", "text": item["a"]}}
                for item in page["faq"]]})
    elif page["kind"] == "hub":
        graph = [person, service, website, {
            "@type": "CollectionPage", "@id": url + "#webpage", "url": url, "name": page["title"],
            "description": page["description"], "isPartOf": {"@id": base + "#website"},
            "about": {"@id": base + "#service"}, "inLanguage": "en"},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": base},
                {"@type": "ListItem", "position": 2, "name": "Services", "item": url}]}]
    elif page["kind"] == "doc":
        parent = page["parent"]
        graph = [person, website, {
            "@type": "TechArticle", "@id": url + "#article", "url": url, "headline": page["headline"],
            "description": page["description"], "author": {"@id": base + "#person"},
            "datePublished": page["published"], "isBasedOn": page["source"], "inLanguage": "en",
            "isPartOf": {"@id": base + "#website"}},
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "Home", "item": base},
                {"@type": "ListItem", "position": 2, "name": parent["name"], "item": base.rstrip("/") + parent["path"]},
                {"@type": "ListItem", "position": 3, "name": page["crumb"], "item": url}]}]
    else:
        return ""
    text = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)
    return '<script type="application/ld+json">' + text.replace("</", "<\\/") + "</script>"


# ---------- css / js ----------
def build_css():
    css = (SRC / "style.css").read_text(encoding="utf-8")
    m = re.search(r':root\[data-theme="dark"\]\s*\{(.*?)\}', css, re.S)
    if not m:
        sys.exit('build: style.css needs a :root[data-theme="dark"] { ... } token block')
    # The same dark tokens apply when the OS asks for dark and the visitor has not picked light
    css = css.replace(m.group(0), m.group(0) +
                      '\n@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {' + m.group(1) + "} }", 1)
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{};,>])\s*", r"\1", css)
    css = re.sub(r"([{;])\s*([\w-]+)\s*:\s+", r"\1\2:", css)  # tidy "prop: value" only, never selectors
    return css.replace(";}", "}").strip()


def build_js():
    js = (SRC / "js" / "main.js").read_text(encoding="utf-8")
    js = re.sub(r"^\s*//.*$", "", js, flags=re.M)  # whole-line comments only; keeps strings and URLs intact
    js = re.sub(r"\n\s*\n+", "\n", js)
    return js.strip() + "\n"


# ---------- rendering ----------
def render(template, values, where):
    def sub(m):
        key = m.group(1)
        if key not in values:
            sys.exit(f"build: no value for '{{{{ {key} }}}}' in {where}")
        return str(values[key])
    return TOKEN.sub(sub, template)


def load_pages():
    pages = []
    for p in sorted((SRC / "pages").rglob("*.html")):
        text = p.read_text(encoding="utf-8")
        m = FRONT.match(text)
        if not m:
            sys.exit(f"build: {p} must start with a <!--page {{...}} --> front-matter comment")
        meta = json.loads(m.group(1))
        rel = p.relative_to(SRC / "pages").with_suffix("")
        if rel.name == "index":
            path, out = "/", Path("index.html")
        elif rel.name == "404":
            path, out = "/404.html", Path("404.html")
        else:
            path, out = f"/{rel.as_posix()}/", rel / "index.html"
        meta.update(path=path, out=out, body=text[m.end():], src=p)
        pages.append(meta)
    return pages


def last_modified(paths):
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%cs", "--", *map(str, paths)], cwd=ROOT,
                             capture_output=True, text=True, check=True)
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
    services = json.loads((CONTENT / "services.json").read_text(encoding="utf-8"))
    caps = services["services"]
    osm = json.loads((STATIC / "data" / "lagos-health-osm.json").read_text(encoding="utf-8"))
    manifest = json.loads((STATIC / "img" / "manifest.json").read_text(encoding="utf-8"))
    products = json.loads((CONTENT / "products.json").read_text(encoding="utf-8"))
    testimonials = json.loads((CONTENT / "testimonials.json").read_text(encoding="utf-8"))
    if not site["base_url"].endswith("/"):
        sys.exit("build: base_url must end with '/'")

    # Empty dist/ rather than deleting it: on Windows a folder that a shell or
    # the preview server has open cannot be removed.
    DIST.mkdir(exist_ok=True)
    for p in DIST.iterdir():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    shutil.copytree(STATIC, DIST, dirs_exist_ok=True)
    (DIST / "img" / "manifest.json").unlink(missing_ok=True)

    js = build_js()
    (DIST / "assets").mkdir(exist_ok=True)
    (DIST / "assets" / "main.js").write_text(js, encoding="utf-8", newline="\n")

    gaps = Missing(args.release)
    shared = {
        "base_url": esc(site["base_url"]),
        "name": esc(site["name"]),
        "flagship": esc(site["flagship"]),
        "email": esc(site["email"]),
        "timezone": esc(site["timezone"]),
        "linkedin": esc(site["links"]["linkedin"]),
        "github": esc(site["links"]["github"]),
        "medium": esc(site["links"]["medium"]),
        "year": dt.date.today().year,
        "css": build_css(),
        "js_version": hashlib.sha1(js.encode()).hexdigest()[:8],
    }
    shared.update(fragments(site, caps, osm, manifest, gaps, products))
    shared.update(service_fragments(services))
    shared["testimonials"] = testimonials_html(testimonials, gaps)
    shared["brief_builder"] = shared["brief_builder"].replace("__EMAIL__", esc(site["email"]))
    shared["email"] = esc(site["email"])
    partials = {p.stem: p.read_text(encoding="utf-8") for p in (SRC / "partials").glob("*.html")}

    pages = load_pages()
    sitemap = []
    for page in pages:
        title = page.get("title") or site["title"]
        description = page.get("description") or site["description"]
        page.setdefault("title", title)
        page["title"], page["description"] = title, description
        page.setdefault("og_image", "og.png")
        canonical = site["base_url"].rstrip("/") + page["path"]
        values = dict(shared)
        values.update({
            "page_title": esc(title),
            "page_description": esc(description),
            "canonical": esc(canonical),
            "og_title": esc(page.get("og_title") or title),
            "og_image": esc(site["base_url"] + page["og_image"]),
            "og_image_alt": esc(page.get("og_image_alt") or f'{site["name"]}: {site["flagship"]}'),
            "og_type": "article" if page["kind"] in ("case", "doc") else "website",
            "robots": "noindex" if page.get("noindex") else "index, follow, max-image-preview:large",
            "body_class": "page-" + page["kind"],
            "nav_prefix": "" if page["kind"] == "home" else "/",
            "jsonld": jsonld(page, site, caps, manifest),
        })
        if page["kind"] == "service":
            values["service_faq"] = faq_html(page.get("faq", []))
            values["other_services"] = service_cards(services, exclude=page["service"])
        values["content"] = render(page["body"], values, page["src"].name)
        for name in ("header", "footer"):
            values[name] = render(partials[name], values, f"partials/{name}.html")
        layout = page.get("layout", "layout")
        out = render(partials[layout], values, f"partials/{layout}.html")
        target = DIST / page["out"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(out, encoding="utf-8", newline="\n")
        if not page.get("noindex"):
            sitemap.append((canonical, last_modified([page["src"], CONTENT])))
        page["bytes"] = len(out.encode("utf-8"))
        page["gz"] = len(gzip.compress(out.encode("utf-8")))

    base = site["base_url"]
    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base}sitemap.xml\n", encoding="utf-8", newline="\n")
    urls = "".join(f"  <url>\n    <loc>{esc(u)}</loc>\n    <lastmod>{d}</lastmod>\n  </url>\n" for u, d in sitemap)
    (DIST / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                      '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                      f"{urls}</urlset>\n", encoding="utf-8", newline="\n")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Built {'release' if args.release else 'preview'} -> {DIST}")
    for page in pages:
        print(f"  {page['path']:<40} {page['bytes'] / 1024:5.1f} KB raw, {page['gz'] / 1024:4.1f} KB gzipped")
    print(f"  /assets/main.js {len(js.encode()) / 1024:.1f} KB")
    if gaps.items:
        verb = "left out" if args.release else "shown as TODO"
        print(f"  {len(gaps.items)} missing item(s) {verb}:")
        for g in gaps.items:
            print(f"    - {g}")


if __name__ == "__main__":
    main()
