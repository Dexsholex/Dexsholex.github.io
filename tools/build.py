#!/usr/bin/env python3
"""Build the site into dist/.

    python tools/build.py            preview build: missing items show as TODO markers
    python tools/build.py --release  public build: missing items are left out quietly

Pages are Jinja2 templates in src/pages/<lang>/. Each one starts with a front-matter
comment, {#page {...} #}, holding its kind, title and description. The default language
(English) is served from the site root and every other language from /<code>/. A page
and its translations sit at the same path inside their language folders, which is how
the hreflang links are paired. Service pages are generated from the services data with
src/templates/service.html.

Content is split in two. content/*.json hold structure: URLs, slugs, numbers, icons.
content/i18n/<lang>/ hold everything a reader sees: ui.json (interface text and the
site's own wording), services.json and products.json. Every language must have exactly
the same keys as English; the build stops and lists any that differ.
"""
import argparse
import base64
import copy
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

import jinja2
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent.parent
SRC, CONTENT, STATIC, DIST = (ROOT / d for d in ("src", "content", "static", "dist"))
TEMPLATES, PAGES, I18N = SRC / "templates", SRC / "pages", CONTENT / "i18n"
FRONT = re.compile(r"\A\{#page\s*(\{.*?\})\s*#\}\s*", re.S)
BLANK_GIF = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
CATEGORY_SLOT = [0, 1, 1, 2, 3]  # hospital, clinic, doctors, pharmacy, other -> legend slot
CASES = {"oil-palm": "/work/oil-palm-tree-counting/", "geoaid": "/work/geoaid-flood-susceptibility/",
         "access-map": "/#access-map"}
NNBSP, NBSP = " ", " "

# How each language writes numbers and dates. Arabic pages keep Western digits, as most
# technical and map material in the region does.
FORMATS = {
    "en": {"group": ",", "decimal": ".", "pct": "{}%", "locale": "en-GB",
           "date": "{d} {m} {y}", "month": "{m} {y}",
           "months": ["January", "February", "March", "April", "May", "June", "July", "August",
                      "September", "October", "November", "December"]},
    "fr": {"group": NNBSP, "decimal": ",", "pct": "{}" + NNBSP + "%", "locale": "fr-FR",
           "date": "{d} {m} {y}", "month": "{m} {y}",
           "months": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
                      "septembre", "octobre", "novembre", "décembre"]},
    "pt": {"group": NNBSP, "decimal": ",", "pct": "{}%", "locale": "pt-PT",
           "date": "{d} de {m} de {y}", "month": "{m} de {y}",
           "months": ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
                      "setembro", "outubro", "novembro", "dezembro"]},
    "es": {"group": NNBSP, "decimal": ",", "pct": "{}" + NNBSP + "%", "locale": "es-ES",
           "date": "{d} de {m} de {y}", "month": "{m} de {y}",
           "months": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                      "septiembre", "octubre", "noviembre", "diciembre"]},
    "ar": {"group": ",", "decimal": ".", "pct": "{}%", "locale": "ar-EG-u-nu-latn",
           "date": "{d} {m} {y}", "month": "{m} {y}",
           "months": ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس",
                      "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]},
}

# Runs before the page paints: theme, the "js" class, full layout before a jump to #section,
# and a move to the visitor's chosen language when this page exists in it.
HEAD_SCRIPT = (
    'var d=document.documentElement;'
    'try{var t=localStorage.getItem("theme");if(t==="light"||t==="dark")d.dataset.theme=t;'
    'var l=localStorage.getItem("lang");'
    'if(l&&/^[a-z]{2}$/.test(l)&&l!==d.lang){'
    'var a=document.querySelector(\'link[rel="alternate"][hreflang="\'+l+\'"]\');'
    'if(a)location.replace(a.href+location.hash)}}catch(e){}'
    'd.classList.add("js");if(location.hash)d.classList.add("cv-off")'
)


class Env(jinja2.Environment):
    """Dictionary keys win over dict methods, so {{ group.items }} means the key, not dict.items."""

    def getattr(self, obj, attribute):
        if isinstance(obj, dict) and attribute in obj:
            return obj[attribute]
        return super().getattr(obj, attribute)


def sha256(text):
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode() + "'"


def read_json(p):
    return json.loads(p.read_text(encoding="utf-8"))


# ---------- languages ----------
def shape_problems(ref, other, where):
    """Differences in keys, list lengths or types between the English text and a translation."""
    if isinstance(ref, dict):
        if not isinstance(other, dict):
            return [f"{where}: expected an object"]
        out = [f"{where}.{k}: missing" for k in ref if k not in other]
        out += [f"{where}.{k}: not in English" for k in other if k not in ref]
        for k in ref:
            if k in other:
                out += shape_problems(ref[k], other[k], f"{where}.{k}")
        return out
    if isinstance(ref, list):
        if not isinstance(other, list):
            return [f"{where}: expected a list"]
        if len(ref) != len(other):
            return [f"{where}: {len(other)} items, English has {len(ref)}"]
        out = []
        for i, (a, b) in enumerate(zip(ref, other)):
            out += shape_problems(a, b, f"{where}[{i}]")
        return out
    if isinstance(other, (dict, list)):
        return [f"{where}: expected text"]
    return []


def load_text(langs, default):
    text = {l: {f: read_json(I18N / l / f"{f}.json") for f in ("ui", "services", "products")} for l in langs}
    problems = []
    for l in langs:
        if l != default:
            for f in text[l]:
                problems += shape_problems(text[default][f], text[l][f], f"{l}/{f}")
    return text, problems


def fmt_num(x, lang, decimals=None):
    f = FORMATS[lang]
    if decimals is None:
        decimals = 0 if isinstance(x, int) else 1
    s = f"{x:,.{decimals}f}"
    return s.replace(",", "\0").replace(".", f["decimal"]).replace("\0", f["group"])


def fmt_pct(x, lang):
    return FORMATS[lang]["pct"].format(fmt_num(x, lang, 1))


def fmt_date(iso, lang, day=True):
    f = FORMATS[lang]
    d = dt.date.fromisoformat(iso if len(iso) == 10 else iso + "-01")
    m = f["months"][d.month - 1]
    if not day:
        return f["month"].format(m=m, y=d.year)
    n = "1er" if lang == "fr" and d.day == 1 else str(d.day)
    return f["date"].format(d=n, m=m, y=d.year)


def typography(page_html, lang):
    """Language-specific spacing in visible text: grouped digits (fr, pt, es) and French high punctuation."""
    if lang not in ("fr", "pt", "es"):
        return page_html

    def text(s):
        s = re.sub(r"(\d) (\d{3})(?!\d)", r"\1" + NNBSP + r"\2", s)
        if lang in ("fr", "es"):
            s = re.sub(r"(\d) %", r"\1" + NNBSP + "%", s)
        if lang == "fr":
            s = re.sub(r" ([?!;»])", NNBSP + r"\1", s)
            s = re.sub(r" :(?=\s|$)", NBSP + ":", s)
            s = s.replace("« ", "«" + NBSP)
        return s

    def attrs(m):
        return f'{m.group(1)}="{text(m.group(2))}"'

    parts = re.split(r"(<script\b.*?</script>|<style\b.*?</style>)", page_html, flags=re.S)
    for i in range(0, len(parts), 2):
        s = re.sub(r">([^<]+)<", lambda m: ">" + text(m.group(1)) + "<", parts[i])
        parts[i] = re.sub(r'\b(content|alt|aria-label|title|placeholder)="([^"]*)"', attrs, s)
    return "".join(parts)


# ---------- content for one language ----------
def merged_site(site, ui):
    s = copy.deepcopy(site)
    u = ui["site"]
    for k in ("roles", "flagship", "topic", "title", "description", "call_subject", "call_body"):
        s[k] = u[k]
    s["booking_options"] = [dict(o, label=u["booking"][o["key"]]) for o in site["booking_options"]]
    s["tools"] = [{"group": u["tool_groups"][g["key"]], "items": [u["tool_items"].get(i, i) for i in g["items"]]}
                  for g in site["tools"]]
    return s


def merged_services(struct, text):
    services = []
    for s in struct["services"]:
        t = text["services"][s["slug"]]
        services.append(dict(s, title=t["title"], short=t["short"], page=dict(t["page"], related=s["related"])))
    return {"sectors": {k: text["sectors"][k] for k in struct["sectors"]}, "also": text["also"], "services": services}


def merged_products(struct, text):
    return [dict(p, summary=text[p["id"]]["summary"], audience=text[p["id"]]["audience"], tags=text[p["id"]]["tags"],
                 links=[dict(l, label=lbl) for l, lbl in zip(p["links"], text[p["id"]]["links"])]) for p in struct]


def pick(value, lang, default):
    """Testimonials may give a value per language ({"en": ..., "fr": ...}); fall back to the default language."""
    if isinstance(value, dict) and default in value:
        return value.get(lang, value[default])
    if isinstance(value, dict):
        return {k: pick(v, lang, default) for k, v in value.items()}
    if isinstance(value, list):
        return [pick(v, lang, default) for v in value]
    return value


# ---------- assets ----------
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


# ---------- pages ----------
def route(lang, rel, default):
    """URL path for a page file. rel is relative to its language folder, without the suffix."""
    prefix = "" if lang == default else f"/{lang}"
    rel = rel.as_posix()
    if rel == "index":
        return prefix + "/"
    if rel == "404":
        return prefix + "/404.html"
    return f"{prefix}/{rel}/"


def out_file(path):
    if path.endswith(".html"):
        return Path(path.lstrip("/"))
    return Path(path.lstrip("/")) / "index.html"


PAGE_DEFAULTS = {
    "og_title": None, "og_image": "og.png", "og_image_alt": None, "noindex": False,
    "headline": None, "crumb": None, "published": None, "keywords": [], "faq": [],
}


def load_pages(langs, default, services_by_lang):
    pages = []
    for lang in langs:
        folder = PAGES / lang
        for p in sorted(folder.rglob("*.html")):
            text = p.read_text(encoding="utf-8")
            m = FRONT.match(text)
            if not m:
                sys.exit(f"build: {p} must start with a {{#page {{...}} #}} front-matter comment")
            meta = dict(PAGE_DEFAULTS, **json.loads(m.group(1)))
            rel = p.relative_to(folder).with_suffix("")
            meta.update(lang=lang, path=route(lang, rel, default), key=route(default, rel, default),
                        template=p.relative_to(PAGES).as_posix(), sources=[p])
            pages.append(meta)
        for s in services_by_lang[lang]["services"]:
            sp = s["page"]
            rel = Path("services") / s["slug"]
            meta = dict(PAGE_DEFAULTS, kind="service", title=sp["title"], description=sp["description"],
                        headline=sp["headline"], crumb=sp["crumb"], faq=sp["faq"], slug=s["slug"])
            meta.update(lang=lang, path=route(lang, rel, default), key=route(default, rel, default),
                        template="service.html",
                        sources=[TEMPLATES / "service.html", CONTENT / "services.json", I18N / lang / "services.json"])
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


# ---------- structured data ----------
def jsonld(page, ctx):
    site, lang, base = ctx["site"], page["lang"], ctx["site"]["base_url"]
    url = base.rstrip("/") + page["path"]
    home = base.rstrip("/") + ctx["link"]("/")
    t = ctx["t"]
    services = ctx["services"]["services"]
    address = {"@type": "PostalAddress", "addressLocality": site["locality"], "addressCountry": site["country_code"]}
    same_as = [u for u in site["links"].values() if u]
    area = [{"@type": "Country", "name": "Nigeria"}, {"@type": "Continent", "name": "Africa"},
            {"@type": "Place", "name": "Worldwide"}]
    ilorin = {"@type": "CollegeOrUniversity", "name": "University of Ilorin"}
    miva = {"@type": "CollegeOrUniversity", "name": "Miva Open University"}
    person = {
        "@type": "Person", "@id": base + "#person", "name": site["name"], "jobTitle": site["roles"],
        "url": base, "image": base.rstrip("/") + ctx["manifest"]["portrait"][-1]["src"],
        "email": "mailto:" + site["email"], "address": address, "alumniOf": [ilorin, miva],
        "hasCredential": [
            {"@type": "EducationalOccupationalCredential", "credentialCategory": "degree",
             "name": "BSc Surveying and Geoinformatics", "recognizedBy": ilorin},
            {"@type": "EducationalOccupationalCredential", "credentialCategory": "degree",
             "name": "Master of Information Technology (MIT), AI specialisation", "recognizedBy": miva},
        ],
        "knowsAbout": [s["title"] for s in services] + [i for g in site["tools"] for i in g["items"]],
        "knowsLanguage": "en", "sameAs": same_as,
    }
    service = {
        "@type": "ProfessionalService", "@id": base + "#service", "name": site["name"],
        "description": site["description"], "url": home, "image": base + ctx["og_default"],
        "logo": base + "apple-touch-icon.png",
        "email": "mailto:" + site["email"], "address": address, "areaServed": area,
        "availableLanguage": "en", "founder": {"@id": base + "#person"},
        "knowsAbout": [s["title"] for s in services], "sameAs": same_as,
        "hasOfferCatalog": {
            "@type": "OfferCatalog", "name": t["nav"]["services"],
            "itemListElement": [{"@type": "Offer", "itemOffered": {
                "@type": "Service", "name": s["title"], "description": s["short"],
                "url": base.rstrip("/") + ctx["link"](f"/services/{s['slug']}/")}} for s in services]},
    }
    website = {"@type": "WebSite", "@id": home + "#website", "url": home, "name": site["name"],
               "inLanguage": lang, "publisher": {"@id": base + "#person"}}

    def crumbs(*items):
        return {"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(items)]}

    nav = t["nav"]
    kind = page["kind"]
    if kind == "home":
        graph = [person, service, website, {
            "@type": "WebPage", "@id": url + "#webpage", "url": url, "name": page["title"],
            "description": page["description"], "isPartOf": {"@id": home + "#website"},
            "about": {"@id": base + "#person"}, "mainEntity": {"@id": base + "#service"},
            "primaryImageOfPage": {"@type": "ImageObject", "url": base + page["og_image"], "width": 1200, "height": 630},
            "inLanguage": lang}]
    elif kind == "case":
        article = {
            "@type": "Article", "@id": url + "#article", "url": url, "headline": page["headline"],
            "description": page["description"], "image": base + page["og_image"],
            "author": {"@id": base + "#person"}, "publisher": {"@id": base + "#person"},
            "datePublished": page["published"], "dateModified": page.get("modified", page["published"]),
            "isPartOf": {"@id": home + "#website"}, "inLanguage": lang, "keywords": page["keywords"]}
        graph = [person, website, article,
                 crumbs((nav["home"], home), (nav["case_studies"], home + "#work"), (page["crumb"], url))]
        pre = site["preprint"]
        if page.get("preprint") and pre.get("doi"):
            doi_url = ctx["preprint_url"]
            authors = [{"@id": base + "#person"}] + [{"@type": "Person", "name": n} for n in pre["author_names"][1:]]
            graph.append({
                "@type": "ScholarlyArticle", "@id": doi_url, "url": doi_url, "headline": pre["title"],
                "author": authors, "datePublished": pre["posted"], "inLanguage": "en",
                "publisher": {"@type": "Organization", "name": pre["server"]},
                "identifier": {"@type": "PropertyValue", "propertyID": "DOI", "value": pre["doi"]}})
            article["citation"] = {"@id": doi_url}
    elif kind == "service":
        graph = [person, service, website, {
            "@type": "Service", "@id": url + "#service", "url": url, "name": page["headline"],
            "serviceType": page["headline"], "description": page["description"],
            "provider": {"@id": base + "#service"}, "areaServed": area, "availableLanguage": "en"},
            crumbs((nav["home"], home), (nav["services"], base.rstrip("/") + ctx["link"]("/services/")), (page["crumb"], url))]
        if page["faq"]:
            graph.append({"@type": "FAQPage", "@id": url + "#faq", "inLanguage": lang, "mainEntity": [
                {"@type": "Question", "name": item["q"], "acceptedAnswer": {"@type": "Answer", "text": item["a"]}}
                for item in page["faq"]]})
    elif kind == "hub":
        graph = [person, service, website, {
            "@type": "CollectionPage", "@id": url + "#webpage", "url": url, "name": page["title"],
            "description": page["description"], "isPartOf": {"@id": home + "#website"},
            "about": {"@id": base + "#service"}, "inLanguage": lang},
            crumbs((nav["home"], home), (nav["services"], url))]
    elif kind == "doc":
        parent = page["parent"]
        graph = [person, website, {
            "@type": "TechArticle", "@id": url + "#article", "url": url, "headline": page["headline"],
            "description": page["description"], "author": {"@id": base + "#person"},
            "datePublished": page["published"], "isBasedOn": page["source"], "inLanguage": lang,
            "isPartOf": {"@id": home + "#website"}},
            crumbs((nav["home"], home), (parent["name"], base.rstrip("/") + parent["path"]), (page["crumb"], url))]
    elif kind == "page" and not page["noindex"]:
        graph = [website, {
            "@type": "WebPage", "@id": url + "#webpage", "url": url, "name": page["title"],
            "description": page["description"], "isPartOf": {"@id": home + "#website"}, "inLanguage": lang},
            crumbs((nav["home"], home), (page["crumb"] or page["title"], url))]
    else:
        return Markup("")
    text = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=1)
    return Markup('<script type="application/ld+json">' + text.replace("</", "<\\/") + "</script>")


# ---------- per-language context ----------
def language_context(lang, data, todo, routes, release):
    default = data["site"]["default_language"]
    text = data["text"][lang]
    t = text["ui"]
    site = merged_site(data["site"], t)
    conf = next(l for l in data["site"]["languages"] if l["code"] == lang)

    def link(path):
        """A site path in this language when the page exists in it, otherwise the default-language page."""
        p, _, frag = path.partition("#")
        if lang != default and f"/{lang}{p}" in routes:
            p = f"/{lang}{p}"
        return p + ("#" + frag if frag else "")

    q = urllib.parse.quote
    body = site["call_body"].replace("\n", "\r\n")
    email_book = f"mailto:{site['email']}?subject={q(site['call_subject'])}&body={q(body)}"
    palm_raw = site["projects"]["oil_palm"]
    palm = {k: (fmt_num(v, lang) if isinstance(v, (int, float)) and not isinstance(v, bool) else v)
            for k, v in palm_raw.items()}
    palm["double_count_share"] = fmt_pct(palm_raw["double_count_share"], lang)
    palm["as_of"] = fmt_date(palm_raw["as_of"], lang, day=False)
    palm["density"] = fmt_num(palm_raw["density"], lang, 1)
    osm = data["osm"]
    rows = []
    for feat in osm["lgas"]["features"]:
        props = feat["properties"]
        if not props.get("counts"):
            continue
        slots = [0, 0, 0, 0]
        for i, n in enumerate(props["counts"]):
            slots[CATEGORY_SLOT[i]] += n
        rows.append({"name": props["name"], "slots": [fmt_num(v, lang) for v in slots],
                     "total": fmt_num(sum(slots), lang), "sort": sum(slots)})
    rows.sort(key=lambda r: -r["sort"])
    pre = site["preprint"]
    suggest = {l: {"text": data["text"][l]["ui"]["js"]["lang_suggest"], "switch": data["text"][l]["ui"]["js"]["lang_switch"],
                   "stay": data["text"][l]["ui"]["js"]["lang_stay"],
                   "dir": next(x["dir"] for x in data["site"]["languages"] if x["code"] == l)} for l in data["text"]}
    f = FORMATS[lang]
    js_strings = dict(t["js"], lang=lang, suggest=suggest, pulled=fmt_date(osm["pulled"], lang),
                      num={"group": f["group"], "decimal": f["decimal"]})
    return {
        "lang": lang, "dir": conf["dir"], "t": t, "site": site,
        "services": merged_services(data["services"], text["services"]),
        "products": merged_products(data["products"], text["products"]),
        "testimonial_items": pick(data["testimonials"], lang, default),
        "manifest": data["manifest"], "blank_gif": BLANK_GIF, "release": release, "todo": todo,
        "year": dt.date.today().year, "link": link,
        "call_url": site.get("booking_url") or email_book, "email_book_url": email_book,
        "mailto_url": f"mailto:{site['email']}",
        "preprint_url": "https://doi.org/" + pre["doi"] if pre.get("doi") else None,
        "palm": palm, "osm_rows": rows, "osm_count": fmt_num(len(osm["facilities"]), lang),
        "osm_pulled": fmt_date(osm["pulled"], lang), "cases": CASES,
        "today_month": fmt_date(dt.date.today().isoformat(), lang, day=False),
        "site_host": site["base_url"].split("//", 1)[-1].rstrip("/"),
        "og_default": "og.png" if lang == default else f"og-{lang}.png",
        "pdf": "oluwasola-oyinloye-capability-statement" + ("" if lang == default else f"-{lang}") + ".pdf",
        "js_strings": js_strings, "num": lambda x, d=None: fmt_num(x, lang, d),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--release", action="store_true", help="leave out missing items instead of showing TODO markers")
    args = ap.parse_args()

    site = read_json(CONTENT / "site.json")
    if not site["base_url"].endswith("/"):
        sys.exit("build: base_url must end with '/'")
    langs = [l["code"] for l in site["languages"]]
    default = site["default_language"]
    unready = [l for l in langs if not (I18N / l).is_dir() or not (PAGES / l).is_dir()]
    if unready and args.release:
        sys.exit(f"build: no text or pages yet for: {', '.join(unready)}")
    if unready:
        print(f"  Skipping languages with no text or pages yet: {', '.join(unready)}")
        langs = [l for l in langs if l not in unready]
    site["languages"] = [l for l in site["languages"] if l["code"] in langs]
    text, problems = load_text(langs, default)
    if problems:
        sys.exit("build: translations differ from English:\n  " + "\n  ".join(problems))
    data = {
        "site": site, "services": read_json(CONTENT / "services.json"), "products": read_json(CONTENT / "products.json"),
        "testimonials": read_json(CONTENT / "testimonials.json"), "text": text,
        "osm": read_json(STATIC / "data" / "lagos-health-osm.json"), "manifest": read_json(STATIC / "img" / "manifest.json"),
    }

    gaps = []

    def todo(label):
        if label not in gaps:
            gaps.append(label)
        return Markup("") if args.release else Markup('<span class="todo">TODO: {}</span>').format(label)

    # Empty dist/ rather than deleting it: on Windows a folder that a shell or
    # the preview server has open cannot be removed.
    DIST.mkdir(exist_ok=True)
    for p in DIST.iterdir():
        shutil.rmtree(p) if p.is_dir() else p.unlink()
    shutil.copytree(STATIC, DIST, dirs_exist_ok=True)
    (DIST / "img" / "manifest.json").unlink(missing_ok=True)

    css = build_css()
    js = build_js()
    js_name = f"main.{hashlib.sha256(js.encode()).hexdigest()[:10]}.js"
    (DIST / "assets").mkdir(exist_ok=True)
    (DIST / "assets" / js_name).write_text(js, encoding="utf-8", newline="\n")
    csp = "; ".join([
        "default-src 'self'", f"script-src 'self' {sha256(HEAD_SCRIPT)}", f"style-src 'self' {sha256(css)}",
        "img-src 'self' data:", "media-src 'self'", "font-src 'self'", "connect-src 'self'",
        "object-src 'none'", "base-uri 'self'", "form-action 'self'"])

    env = Env(loader=jinja2.FileSystemLoader([str(TEMPLATES), str(PAGES)]), autoescape=True,
              trim_blocks=True, lstrip_blocks=True, undefined=jinja2.StrictUndefined)
    env.globals.update(css=Markup(css), head_script=Markup(HEAD_SCRIPT), csp=csp, js_src=f"/assets/{js_name}")

    services_by_lang = {l: merged_services(data["services"], text[l]["services"]) for l in langs}
    pages = load_pages(langs, default, services_by_lang)
    routes = {p["path"] for p in pages}
    by_key = {}
    for p in pages:
        by_key.setdefault(p["key"], {})[p["lang"]] = p
    contexts = {l: language_context(l, data, todo, routes, args.release) for l in langs}
    og_locale = {l["code"]: l["og_locale"] for l in site["languages"]}
    names = {l["code"]: l["name"] for l in site["languages"]}
    base = site["base_url"].rstrip("/")

    sitemap = []
    for page in pages:
        ctx = dict(contexts[page["lang"]])
        lang = page["lang"]
        if page["kind"] == "service":
            ctx["service"] = next(s for s in ctx["services"]["services"] if s["slug"] == page["slug"])
        if lang != default and page["og_image"] == "og.png":
            page["og_image"] = f"og-{lang}.png"
        siblings = by_key[page["key"]]
        alternates = []
        if not page["noindex"] and sum(not s["noindex"] for s in siblings.values()) > 1:
            alternates = [{"lang": l, "url": base + siblings[l]["path"], "og_locale": og_locale[l]}
                          for l in langs if l in siblings and not siblings[l]["noindex"]]
        page["alternates"] = alternates
        home_path = ctx["link"]("/")
        ctx.update(
            page=page, canonical=base + page["path"], alternates=alternates,
            x_default=base + siblings[default]["path"] if default in siblings else base + "/",
            language_links=[{"code": l, "name": names[l], "current": l == lang,
                             "href": siblings[l]["path"] if l in siblings else ("/" if l == default else f"/{l}/")}
                            for l in langs],
            section=lambda sid, _home=(page["key"] == "/"), _hp=home_path: f"#{sid}" if _home else f"{_hp}#{sid}",
        )
        ctx["jsonld"] = jsonld(page, ctx)
        try:
            out = env.get_template(page["template"]).render(ctx)
        except jinja2.TemplateError as e:
            sys.exit(f"build: {page['template']} ({lang}): {e}")
        out = typography(out, lang)
        target = DIST / out_file(page["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(out, encoding="utf-8", newline="\n")
        if not page["noindex"]:
            sitemap.append((page, last_modified(page["sources"] + [CONTENT])))
        page["bytes"] = len(out.encode("utf-8"))
        page["gz"] = len(gzip.compress(out.encode("utf-8")))

    (DIST / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {base}/sitemap.xml\n",
                                     encoding="utf-8", newline="\n")
    esc = lambda s: html.escape(s, quote=True)
    urls = []
    for page, lastmod in sitemap:
        links = "".join(f'    <xhtml:link rel="alternate" hreflang="{a["lang"]}" href="{esc(a["url"])}"/>\n'
                        for a in page["alternates"])
        if page["alternates"]:
            links += f'    <xhtml:link rel="alternate" hreflang="x-default" href="{esc(base + by_key[page["key"]][default]["path"])}"/>\n'
        urls.append(f"  <url>\n    <loc>{esc(base + page['path'])}</loc>\n    <lastmod>{lastmod}</lastmod>\n{links}  </url>\n")
    (DIST / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "".join(urls) + "</urlset>\n", encoding="utf-8", newline="\n")
    (DIST / ".nojekyll").write_text("", encoding="utf-8")

    print(f"Built {'release' if args.release else 'preview'} -> {DIST}: {len(pages)} pages in {len(langs)} languages")
    by_lang = {}
    for page in pages:
        by_lang.setdefault(page["lang"], []).append(page)
    for l in langs:
        ps = by_lang.get(l, [])
        if ps:
            print(f"  {l}: {len(ps):3d} pages, largest {max(p['bytes'] for p in ps) / 1024:5.1f} KB raw, "
                  f"{max(p['gz'] for p in ps) / 1024:4.1f} KB gzipped")
    print(f"  /assets/{js_name} {len(js.encode()) / 1024:.1f} KB · inline CSS {len(css.encode()) / 1024:.1f} KB")
    if gaps:
        verb = "left out" if args.release else "shown as TODO"
        print(f"  {len(gaps)} missing item(s) {verb}:")
        for g in gaps:
            print(f"    - {g}")


if __name__ == "__main__":
    main()
