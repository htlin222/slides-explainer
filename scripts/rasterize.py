#!/usr/bin/env python3
"""S0 rasterize: PDF pages -> pages/page-NNN.png, and init the production dir.

Idempotent: skips a page whose PNG already exists unless --force.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import common as C
import validate
from defaults import DEFAULT_STYLE


def parse_pages(spec: str, total_hint: int | None = None):
    """'1-5' or '1,3,7' or '1-5,9' -> sorted unique 1-based page indices."""
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            out.update(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(out)


def rasterize(pdf: Path, pages: list[int], dpi: int, prod: C.Prod, force: bool):
    lo, hi = min(pages), max(pages)
    tmp_prefix = prod.pages / "_raw"
    # pdftoppm renders the whole [lo,hi] range in one pass, names _raw-<n>.png
    need = [p for p in pages if force or not (prod.pages / f"page-{p:03d}.png").exists()]
    if not need:
        return
    C.run([C.PDFTOPPM, "-png", "-r", str(dpi), "-f", str(lo), "-l", str(hi),
           str(pdf), str(tmp_prefix)])
    produced = {}
    for f in prod.pages.glob("_raw-*.png"):
        m = re.search(r"_raw-0*(\d+)\.png$", f.name)
        if m:
            produced[int(m.group(1))] = f
    for p in pages:
        src = produced.get(p)
        if src is None:
            raise SystemExit(f"pdftoppm did not produce page {p}")
        dst = prod.pages / f"page-{p:03d}.png"
        src.replace(dst)
    for leftover in prod.pages.glob("_raw-*.png"):
        leftover.unlink()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", required=True, help="e.g. 1-5 or 1,3,5")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    pdf = Path(args.pdf).resolve()
    if not pdf.exists():
        raise SystemExit(f"PDF not found: {pdf}")
    prod = C.Prod(pdf).ensure()

    # init style.json (never clobber an edited one)
    if not prod.style_path.exists():
        C.save_json(prod.style_path, DEFAULT_STYLE)

    style = C.load_json(prod.style_path, DEFAULT_STYLE)
    dpi = style.get("raster", {}).get("dpi", 150)
    if args.pages.strip().lower() == "all":
        pages = list(range(1, C.pdf_page_count(pdf) + 1))
    else:
        pages = parse_pages(args.pages)
    rasterize(pdf, pages, dpi, prod, args.force)
    for p in pages:  # validate every produced page PNG
        validate.validate_png(prod.pages / f"page-{p:03d}.png")

    # init / update content.json skeleton (preserve existing AI output)
    content = C.load_json(prod.content_path,
                          {"pdf": C.repo_rel(pdf), "slug": prod.slug, "pages": []})
    content["pdf"] = C.repo_rel(pdf)  # always keep repo-relative for CI portability
    by_index = {p["index"]: p for p in content.get("pages", [])}
    for p in pages:
        img = f"pages/page-{p:03d}.png"
        if p not in by_index:
            by_index[p] = {"index": p, "kind": None, "image": img, "segments": []}
        else:
            by_index[p]["image"] = img
    content["pages"] = [by_index[k] for k in sorted(by_index)]
    C.save_json(prod.content_path, content)

    print(f"rasterized {len(pages)} page(s) -> {prod.pages}")
    print(f"production dir: {prod.dir}")
    print(f"slug: {prod.slug}")


if __name__ == "__main__":
    main()
