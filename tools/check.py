#!/usr/bin/env python3
"""Pre-publish checks. Run after tools/build.py and before every push.

    python tools/check.py

1. Blocked names: reads private/blocked_terms.txt (one term per line, never
   committed) and searches every file git would publish, every commit message
   and the built dist/ folder. Any hit fails the check.
2. Filler words the brief rules out, in the page source and content files.
3. TODO markers left in dist/index.html.
4. Page weight of dist/index.html, raw and gzipped.
"""
import gzip
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TERMS_FILE = ROOT / "private" / "blocked_terms.txt"
FILLER = ["cutting-edge", "cutting edge", "leverage", "seamless", "empower", "state-of-the-art",
          "world-class", "synergy", "revolutionary", "unlock"]
WEIGHT_BUDGET_KB = 300


def git(*args):
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return out.stdout if out.returncode == 0 else ""


def publishable_files():
    tracked = git("ls-files").splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard").splitlines()
    files = [ROOT / p for p in tracked + untracked]
    dist = ROOT / "dist"
    if dist.exists():
        files += [p for p in dist.rglob("*") if p.is_file()]
    return [p for p in files if p.is_file()]


def main():
    failed = False

    if TERMS_FILE.exists():
        terms = [t.strip() for t in TERMS_FILE.read_text(encoding="utf-8").splitlines() if t.strip()]
        rx = re.compile("|".join(re.escape(t).replace(r"\ ", r"\s*") for t in terms), re.I)
        hits = []
        for p in publishable_files():
            try:
                text = p.read_bytes().decode("utf-8", errors="ignore")
            except OSError:
                continue
            if rx.search(text) or rx.search(p.name):
                hits.append(str(p.relative_to(ROOT)))
        if rx.search(git("log", "--all", "--format=%B")):
            hits.append("(a commit message)")
        if hits:
            failed = True
            print(f"FAIL blocked names found in {len(hits)} place(s):")
            for h in hits:
                print(f"     {h}")
        else:
            print(f"ok   no blocked names ({len(terms)} terms) in publishable files, dist/ or commit messages")
    else:
        print("WARN private/blocked_terms.txt missing, so the blocked-names check did not run")

    sources = [ROOT / "src" / "index.html", *sorted((ROOT / "content").glob("*.json"))]
    found = []
    for p in sources:
        text = p.read_text(encoding="utf-8").lower()
        found += [f"{p.name}: {w}" for w in FILLER if w in text]
    print("WARN filler words: " + ", ".join(found) if found else "ok   no filler words")

    page = ROOT / "dist" / "index.html"
    if not page.exists():
        print("FAIL dist/index.html missing. Run python tools/build.py first.")
        sys.exit(1)
    html = page.read_text(encoding="utf-8")
    todos = re.findall(r'<span class="todo">TODO: (.*?)</span>', html)
    print(f"WARN {len(todos)} TODO marker(s): " + "; ".join(todos) if todos else "ok   no TODO markers")

    raw = len(html.encode("utf-8"))
    gz = len(gzip.compress(html.encode("utf-8")))
    status = "ok  " if gz / 1024 < WEIGHT_BUDGET_KB else "FAIL"
    print(f"{status} page weight: {raw / 1024:.1f} KB raw, {gz / 1024:.1f} KB gzipped (budget {WEIGHT_BUDGET_KB} KB)")
    failed |= status == "FAIL"

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
