#!/usr/bin/env python3
"""Everything that has to pass before the site goes live, in one command.

    python tools/release.py            build, test and check; nothing leaves this computer
    python tools/release.py --audit    also run the full Lighthouse, layout and link audit (npm run audit)
    python tools/release.py --push     after every check passes, push main to GitHub, which deploys the site

Steps: release build and unit tests, then tools/check.py (blocked names, filler words,
page weight), then the optional audit. It stops at the first failure.
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(label, cmd):
    print(f"\n== {label}")
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    if subprocess.run(cmd, cwd=ROOT, env=env).returncode:
        sys.exit(f"release: {label} failed, so nothing was published")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit", action="store_true", help="also run npm run audit (Lighthouse, layout, links)")
    ap.add_argument("--push", action="store_true", help="push main to GitHub once every check passes")
    args = ap.parse_args()

    status = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    if status.strip():
        print("Note: there are uncommitted changes; the checks run on the working copy.")

    run("Release build and tests", [sys.executable, "-m", "unittest", "discover", "-s", "tests"])
    run("Pre-publish checks", [sys.executable, "tools/check.py"])
    if args.audit:
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            sys.exit("release: npm not found; install Node.js or run without --audit")
        run("Audit", [npm, "run", "audit"])

    if args.push:
        if status.strip():
            sys.exit("release: commit your changes before pushing")
        run("Push to GitHub", ["git", "push", "origin", "main"])
        print("\nPushed. GitHub Actions now tests the site again and deploys it.")
    else:
        print("\nAll checks passed. Nothing was pushed. Run with --push when you are ready to publish.")


if __name__ == "__main__":
    main()
