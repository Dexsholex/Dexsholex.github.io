"""Checks on the built site. Builds a release copy into dist/ first.

    python -m unittest discover -s tests -v
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SITE = json.loads((ROOT / "content" / "site.json").read_text(encoding="utf-8"))
BASE = SITE["base_url"].rstrip("/")
LANGS = {l["code"]: l for l in SITE["languages"]}
DEFAULT = SITE["default_language"]


class Page(HTMLParser):
    """Collects what the tests need from one HTML file."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []          # (tag, attrs dict)
        self.scripts = []       # (attrs, text) for every <script>
        self.styles = []        # text of every <style>
        self.h1 = 0
        self.title = ""
        self._in = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if tag == "h1":
            self.h1 += 1
        if tag in ("script", "style", "title"):
            self._in, self._buf = (tag, a), []

    def handle_endtag(self, tag):
        if self._in and tag == self._in[0]:
            text = "".join(self._buf)
            if tag == "script":
                self.scripts.append((self._in[1], text))
            elif tag == "style":
                self.styles.append(text)
            else:
                self.title = text
            self._in = None

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)

    def first(self, tag, **match):
        for t, a in self.tags:
            if t == tag and all(a.get(k) == v for k, v in match.items()):
                return a
        return None

    def all(self, tag, **match):
        return [a for t, a in self.tags if t == tag and all(a.get(k) == v for k, v in match.items())]


def url_path(p):
    rel = p.relative_to(DIST).as_posix()
    return "/" + (rel[:-len("index.html")] if rel.endswith("index.html") else rel)


def sha(text):
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode("utf-8")).digest()).decode() + "'"


PAGES = {}


def setUpModule():
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "build.py"), "--release"], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8", env=env)
    if out.returncode:
        raise RuntimeError("build failed:\n" + out.stdout + out.stderr)
    for f in sorted(DIST.rglob("*.html")):
        p = Page()
        p.feed(f.read_text(encoding="utf-8"))
        PAGES[url_path(f)] = (f, p)


def indexable():
    for path, (f, p) in PAGES.items():
        robots = p.first("meta", name="robots")
        if robots and "noindex" not in robots["content"]:
            yield path, f, p


class Structure(unittest.TestCase):
    def test_one_h1_per_page(self):
        for path, (f, p) in PAGES.items():
            self.assertEqual(p.h1, 1, path)

    def test_language_and_direction(self):
        for path, (f, p) in PAGES.items():
            html = p.first("html")
            first = path.strip("/").split("/")[0]
            lang = first if first in LANGS and first != DEFAULT else DEFAULT
            self.assertEqual(html.get("lang"), lang, path)
            self.assertEqual(html.get("dir"), LANGS[lang]["dir"], path)

    def test_titles_and_descriptions(self):
        for path, f, p in indexable():
            self.assertTrue(10 <= len(p.title) <= 90, f"{path}: title {len(p.title)} chars")
            d = p.first("meta", name="description")["content"]
            self.assertTrue(50 <= len(d) <= 160, f"{path}: description {len(d)} chars")

    def test_no_template_leftovers_or_todo(self):
        for path, (f, p) in PAGES.items():
            text = f.read_text(encoding="utf-8")
            body = re.sub(r"<(script|style)\b.*?</\1>", "", text, flags=re.S)
            for token in ("{{", "{%", "{#", "TODO:"):
                self.assertNotIn(token, body, f"{path}: {token}")

    def test_no_inline_style_attributes(self):
        for path, (f, p) in PAGES.items():
            styled = [t for t, a in p.tags if "style" in a]
            self.assertEqual(styled, [], path)

    def test_images_have_alt_and_size(self):
        for path, (f, p) in PAGES.items():
            for a in p.all("img"):
                self.assertIn("alt", a, f"{path}: {a.get('src')}")
                self.assertTrue(a.get("width") and a.get("height"), f"{path}: {a.get('src')}")


class Search(unittest.TestCase):
    def test_canonical(self):
        for path, f, p in indexable():
            self.assertEqual(p.first("link", rel="canonical")["href"], BASE + path, path)

    def test_hreflang_pairs_are_reciprocal(self):
        for path, f, p in indexable():
            alts = {a["hreflang"]: a["href"] for a in p.all("link", rel="alternate") if "hreflang" in a}
            if not alts:
                continue
            self.assertIn("x-default", alts, path)
            self.assertIn(BASE + path, alts.values(), f"{path}: does not list itself")
            for lang, href in alts.items():
                other = href[len(BASE):]
                self.assertIn(other, PAGES, f"{path}: hreflang {lang} -> missing {other}")
                back = {a["href"] for a in PAGES[other][1].all("link", rel="alternate")}
                self.assertIn(BASE + path, back, f"{other} does not link back to {path}")

    def test_structured_data_parses(self):
        for path, (f, p) in PAGES.items():
            for attrs, text in p.scripts:
                if attrs.get("type") == "application/ld+json":
                    data = json.loads(text)
                    self.assertEqual(data["@context"], "https://schema.org", path)

    def test_sitemap_lists_exactly_the_indexable_pages(self):
        xml = (DIST / "sitemap.xml").read_text(encoding="utf-8")
        listed = set(re.findall(r"<loc>(.*?)</loc>", xml))
        expected = {BASE + path for path, f, p in indexable()}
        self.assertEqual(listed, expected)
        self.assertIn('hreflang="x-default"', xml)


class Security(unittest.TestCase):
    def test_csp_hashes_match_inline_code(self):
        for path, (f, p) in PAGES.items():
            csp = p.first("meta", **{"http-equiv": "Content-Security-Policy"})
            self.assertIsNotNone(csp, path)
            policy = csp["content"]
            for attrs, text in p.scripts:
                if "src" in attrs or attrs.get("type") in ("application/ld+json", "application/json"):
                    continue
                self.assertIn(sha(text), policy, f"{path}: inline script not allowed by the policy")
            for text in p.styles:
                self.assertIn(sha(text), policy, f"{path}: inline style not allowed by the policy")
            self.assertIn("object-src 'none'", policy)

    def test_external_links_use_https(self):
        for path, (f, p) in PAGES.items():
            for a in p.all("a"):
                href = a.get("href", "")
                self.assertFalse(href.startswith("http://"), f"{path}: {href}")


class Links(unittest.TestCase):
    def test_internal_links_and_assets_resolve(self):
        for path, (f, p) in PAGES.items():
            refs = [a.get("href") for t, a in p.tags if t in ("a", "link") and a.get("href")]
            refs += [a.get("src") for t, a in p.tags if t in ("img", "script", "source") and a.get("src")]
            refs += [s.split()[0] for t, a in p.tags if t in ("img", "source") and a.get("srcset")
                     for s in a["srcset"].split(",") if not s.strip().startswith("data:")]
            for ref in refs:
                if ref.startswith(BASE):
                    ref = ref[len(BASE):] or "/"
                if not ref.startswith("/") or ref.startswith("//"):
                    continue
                target = urlsplit(ref).path
                file = DIST / target.lstrip("/")
                if target.endswith("/"):
                    file = file / "index.html"
                self.assertTrue(file.exists(), f"{path}: {ref}")

    def test_same_page_anchors_exist(self):
        for path, (f, p) in PAGES.items():
            ids = {a.get("id") for t, a in p.tags if a.get("id")}
            for a in p.all("a"):
                href = a.get("href", "")
                if href.startswith("#") and len(href) > 1:
                    self.assertIn(href[1:], ids, f"{path}: {href}")


class Translations(unittest.TestCase):
    def test_every_language_has_the_same_keys_as_english(self):
        sys.path.insert(0, str(ROOT / "tools"))
        import build
        _, problems = build.load_text(list(LANGS), DEFAULT)
        self.assertEqual(problems, [])

    def test_every_language_has_every_page(self):
        en = {p for p in PAGES if not any(p.startswith(f"/{l}/") for l in LANGS)}
        en -= {"/404.html", "/work/geoaid-flood-susceptibility/methods-log/"}
        for lang in LANGS:
            if lang == DEFAULT:
                continue
            for p in en:
                self.assertIn(f"/{lang}{p}", PAGES, f"{lang} is missing {p}")


if __name__ == "__main__":
    unittest.main()
