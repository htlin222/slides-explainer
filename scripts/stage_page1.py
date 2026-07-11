#!/usr/bin/env python3
"""Render page 1 of a PDF to a slug-independent staging PNG.

Used at the very start of /enrich so a haiku agent can look at the first slide and
propose a human-readable slug BEFORE the production directory (named by that slug)
exists. Prints the PNG path.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import common as C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    args = ap.parse_args()
    pdf = Path(args.pdf).resolve()
    if not pdf.exists():
        raise SystemExit(f"PDF not found: {pdf}")

    tag = hashlib.sha1(C.repo_rel(pdf).encode("utf-8")).hexdigest()[:10]
    staging = C.ROOT / "production" / "_staging" / tag
    staging.mkdir(parents=True, exist_ok=True)
    prefix = staging / "page"
    C.run([C.PDFTOPPM, "-png", "-r", "150", "-f", "1", "-l", "1", str(pdf), str(prefix)])
    # pdftoppm names it page-1.png / page-01.png depending on page-count digits
    produced = sorted(staging.glob("page-*.png"))
    if not produced:
        raise SystemExit("pdftoppm produced no page")
    out = staging / "page-001.png"
    if produced[0] != out:
        produced[0].replace(out)
    print(str(out))


if __name__ == "__main__":
    main()
