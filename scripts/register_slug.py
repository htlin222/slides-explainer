#!/usr/bin/env python3
"""Register a PDF -> slug mapping in production/index.json.

The slug (proposed by a haiku agent from page 1) becomes the production dir name,
the release tag, and the output filenames (<slug>.mp4 / <slug>.srt). Sanitized to
kebab-case and de-duplicated so two decks never share a slug.

    python scripts/register_slug.py --pdf <pdf> --slug "wbc-ii-lymphoma"
"""
from __future__ import annotations

import argparse
from pathlib import Path

import common as C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("--force", action="store_true", help="overwrite an existing mapping")
    args = ap.parse_args()

    pdf = Path(args.pdf).resolve()
    rel = C.repo_rel(pdf)
    mapping = C.slug_map()

    if rel in mapping and not args.force:
        print(mapping[rel])          # already registered; keep it stable
        return

    want = C.kebab(args.slug)
    taken = {v for k, v in mapping.items() if k != rel}
    slug = want
    n = 2
    while slug in taken:             # de-dup against other PDFs
        slug = f"{want}-{n}"
        n += 1

    mapping[rel] = slug
    C.save_json(C.SLUG_INDEX, mapping)
    print(slug)


if __name__ == "__main__":
    main()
