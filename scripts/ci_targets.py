#!/usr/bin/env python3
"""Decide which production slugs a cloud build should (re)build.

Outputs a JSON array of {"slug","pdf"} to stdout, consumable by a GitHub Actions
matrix via fromJSON(). A slug is buildable only if it has config/content.json
(the committed LLM output).

Modes:
  --slug <slug>            explicit (workflow_dispatch)
  --base <sha> --head <sha> diff range (push); scripts/tools/.github change -> all slugs
  (no args)                all buildable slugs
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

PROD = C.ROOT / "production"


def buildable_slugs():
    out = []
    if PROD.exists():
        for d in sorted(PROD.iterdir()):
            if (d / "config" / "content.json").exists():
                out.append(d.name)
    return out


def slug_to_pdf(slug: str):
    content = C.load_json(PROD / slug / "config" / "content.json")
    return content.get("pdf") if content else None


def changed_files(base: str, head: str):
    # first push / created branch: base is all-zeros -> treat as "everything"
    if not base or set(base) <= {"0"}:
        return None
    try:
        r = C.run(["git", "-C", str(C.ROOT), "diff", "--name-only", base, head])
    except Exception:
        return None
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug")
    ap.add_argument("--base")
    ap.add_argument("--head")
    args = ap.parse_args()

    all_slugs = set(buildable_slugs())

    if args.slug:
        slugs = {args.slug} & all_slugs
    elif args.base and args.head:
        files = changed_files(args.base, args.head)
        if files is None:                   # unknown base -> rebuild all
            slugs = set(all_slugs)
        else:
            slugs = set()
            if any(f.startswith(("scripts/", "tools/", ".github/")) for f in files):
                slugs = set(all_slugs)      # code affects every video
            for f in files:
                m = re.match(r"production/([^/]+)/", f)
                if m:
                    slugs.add(m.group(1))
            slugs &= all_slugs              # only those with content.json
    else:
        slugs = set(all_slugs)

    targets = [{"slug": s, "pdf": slug_to_pdf(s)} for s in sorted(slugs)]
    targets = [t for t in targets if t["pdf"]]
    print(json.dumps(targets))


if __name__ == "__main__":
    main()
