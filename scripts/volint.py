#!/usr/bin/env python3
"""Voiceover linter: catch/normalize text that a TTS engine would mispronounce.

`clean(text)` is a PURE, deterministic normalizer applied right before synthesis
(so a rule change re-synthesizes via the cache key). `lint(text)` returns the
residual warnings a human should look at. Runnable standalone to audit a deck:

    python scripts/volint.py --pdf <pdf> [--strict]
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import common as C

# ---- deterministic auto-fixes (safe: never change medical meaning) -----------
# ordered list of (pattern, replacement)
_FIXES = [
    (r"```[a-zA-Z]*", " "),            # stray code fences
    (r"[`*_#]+", " "),                 # markdown emphasis / headings
    (r"[•‣◦·]", " "),                  # bullet glyphs
    (r"::", " "),                       # "BIRC3::MALT1" -> spoken "BIRC3 MALT1" (not "colon colon")
    (r"\s*[→➔⇒➞]\s*", " leads to "),   # arrows
    (r"≥", " greater than or equal to "),
    (r"≤", " less than or equal to "),
    (r"([0-9])\s*%", r"\1 percent"),   # "80%" -> "80 percent"
    (r"\s*&\s*", " and "),
    (r"\s+", " "),                      # collapse whitespace (last)
]

# ---- residual hazards we only WARN about (auto-fixing would risk meaning) -----
_WARN = [
    (r"[<>]", "angle bracket < or > (TTS may read literally)"),
    (r"\w/\w", "slash between words (TTS reads 'slash'; consider 'or')"),
    (r"[;]", "semicolon (fine inside 't 8;14', otherwise check phrasing)"),
    (r"[^\x00-\x7f]", "non-ASCII character (check pronunciation)"),
    (r"\bhttps?://", "URL in voiceover"),
]


def clean(text: str) -> str:
    out = text.strip()
    for pat, rep in _FIXES:
        out = re.sub(pat, rep, out)
    return out.strip()


def lint(text: str):
    issues = []
    if not text.strip():
        issues.append("empty voiceover")
    for pat, msg in _WARN:
        m = re.search(pat, text)
        if m:
            issues.append(f"{msg} -> …{text[max(0, m.start()-15):m.start()+15]}…")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any residual warning remains")
    args = ap.parse_args()

    prod = C.Prod(Path(args.pdf))
    content = C.load_json(prod.content_path)
    total = 0
    for page in content["pages"]:
        for seg in page["segments"]:
            cleaned = clean(seg["voiceover"])
            issues = lint(cleaned)
            if issues:
                total += len(issues)
                print(f"[{seg['id']}] {len(issues)} warning(s):")
                for it in issues:
                    print(f"    - {it}")
    if total == 0:
        print("voiceover lint: clean ✓")
    else:
        print(f"voiceover lint: {total} residual warning(s)")
    raise SystemExit(1 if (args.strict and total) else 0)


if __name__ == "__main__":
    main()
