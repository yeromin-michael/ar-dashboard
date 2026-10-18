#!/usr/bin/env python3
"""Fail if any tracked or staged file contains a denied term.

Terms are never stored in this repo. They are loaded from, in order:
  1. $AR_DENYLIST            newline-separated terms (used by CI via a secret)
  2. $AR_DENYLIST_FILE       path to a file with one term per line
  3. ~/.config/ar-dashboard/denylist.txt

Lines starting with '#' and blank lines are ignored. Matching is
case-insensitive on word boundaries. With no terms loaded the check fails,
so a missing secret can never pass silently.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_FILE = Path.home() / ".config" / "ar-dashboard" / "denylist.txt"


def load_terms() -> list[str]:
    raw = os.environ.get("AR_DENYLIST")
    if raw is None:
        path = Path(os.environ.get("AR_DENYLIST_FILE", DEFAULT_FILE))
        raw = path.read_text(encoding="utf-8") if path.exists() else ""
    return [t.strip() for t in raw.splitlines() if t.strip() and not t.lstrip().startswith("#")]


def repo_files(root: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, check=True, capture_output=True,
    ).stdout.decode()
    return [root / p for p in out.split("\0") if p]


def main() -> int:
    terms = load_terms()
    if not terms:
        print("denylist: no terms loaded (set AR_DENYLIST or create %s)" % DEFAULT_FILE, file=sys.stderr)
        return 2
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(t) for t in terms) + r")(?!\w)", re.IGNORECASE)
    root = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True,
                               capture_output=True, text=True).stdout.strip())
    hits = 0
    for path in repo_files(root):
        rel = path.relative_to(root)
        if pattern.search(str(rel)):
            print(f"{rel}: denied term in file name")
            hits += 1
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (IsADirectoryError, FileNotFoundError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                # Never echo the matched term or line: CI logs may be public.
                print(f"{rel}:{n}: denied term")
                hits += 1
    if hits:
        print(f"denylist: {hits} hit(s) across {len(terms)} terms", file=sys.stderr)
        return 1
    print(f"denylist: clean ({len(terms)} terms)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
