#!/usr/bin/env python3
"""Mirror the GeoAID methods log from GitHub as a page on this site.

    python tools/import_methods_log.py

GitHub's rendered view of long Markdown files is not always available, so the site
keeps its own copy at /work/geoaid-flood-susceptibility/methods-log/. This script
downloads the raw Markdown, converts it to HTML and writes
src/pages/en/work/geoaid-flood-susceptibility/methods-log.html (English only; the other
languages link to it). Run it again whenever the log changes in the GeoAID repository. The text is copied as-is, except that the degree
is named "MIT" as everywhere else on this site.

Needs requests and markdown (pip install markdown).
"""
import datetime as dt
import html
import json
import re
from pathlib import Path

import markdown
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = "https://raw.githubusercontent.com/Dexsholex/GeoAID-Lagos-FloodRisk/main/docs/methods_log.md"
REPO_DOCS = "https://github.com/Dexsholex/GeoAID-Lagos-FloodRisk/tree/main/docs"
OUT = ROOT / "src" / "pages" / "en" / "work" / "geoaid-flood-susceptibility" / "methods-log.html"


def main():
    text = requests.get(RAW, timeout=60).text
    text = re.sub(r"\bMSc\b", "MIT", text)
    lines = text.splitlines()
    # The first lines are the document title and notes to self; the page supplies its own title
    while lines and lines[0].startswith("# "):
        lines.pop(0)
    body = markdown.markdown("\n".join(lines), extensions=["tables", "fenced_code", "sane_lists", "toc"],
                             extension_configs={"toc": {"toc_depth": "2"}}, output_format="html")
    body = body.replace("{{", "&#123;&#123;").replace("{%", "&#123;%").replace("{#", "&#123;#")
    body = re.sub(r"<table>", '<div class="table-scroll"><table>', body)
    body = body.replace("</table>", "</table></div>")
    sections = re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', body)
    toc = "\n".join(f'          <li><a href="#{i}">{t}</a></li>' for i, t in sections)
    today = dt.date.today().isoformat()
    meta = {
        "kind": "doc",
        "title": "GeoAID methods log · Oluwasola Oyinloye",
        "headline": "GeoAID methods log",
        "description": "The working research log behind GeoAID: every data source, parameter, correction "
                       "and validation result for the Amuwo-Odofin flood susceptibility model.",
        "og_image": "og-geoaid.png",
        "crumb": "Methods log",
        "parent": {"name": "GeoAID flood susceptibility", "path": "/work/geoaid-flood-susceptibility/"},
        "published": today,
        "source": RAW,
    }
    page = f"""{{#page {json.dumps(meta, ensure_ascii=False)} #}}
{{% extends "base.html" %}}
{{% import "macros.html" as m with context %}}
{{% block content %}}
<article class="doc-page">
  <header class="case-hero">
    <div class="wrap">
      {{{{ m.crumbs([(t.nav.home, link('/')), ('GeoAID', link('/work/geoaid-flood-susceptibility/')), (page.crumb, none)]) }}}}
      <h1>GeoAID methods log</h1>
      <p class="lead">The working log kept while building GeoAID: every data source, parameter, correction and validation result, written as the work happened. Some sections repeat or were revised later; that history is part of the record.</p>
      <p class="small">Copied from the <a href="{html.escape(REPO_DOCS)}">GeoAID repository</a> on {dt.date.today().strftime('%d %B %Y').lstrip('0')}. <a href="/work/geoaid-flood-susceptibility/">Back to the case study</a></p>
    </div>
  </header>
{{% raw %}}
  <div class="wrap doc-layout">
    <nav class="doc-toc" aria-label="Sections">
      <details data-open-wide>
        <summary>Sections</summary>
        <ol>
{toc}
        </ol>
      </details>
    </nav>
    <div class="prose doc">
{body}
    </div>
  </div>
</article>
{{% endraw %}}
{{% endblock %}}
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8", newline="\n")
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(sections)} sections, {len(page) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
