#!/usr/bin/env python3
"""Driver: run the deterministic pipeline stages in order for one PDF.

    python scripts/render.py --pdf <pdf> --pages 1-5 [--from <stage>] [--force]

The AI stages (classify=haiku, enrich=sonnet/opus) run as Claude Code subagents
OUTSIDE this driver and drop ai/page-NNN.json; `assemble` folds those into
content.json. Everything from `slide` onward is pure/deterministic, so
`--from slide` (style tweak) or `--from caption` (caption restyle) rebuilds only
what changed while reusing cached audio.

Stages: raster assemble slide tts srt timeline caption compose concat snapshot
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
PY = str(SCRIPTS.parent / ".venv/bin/python")

# (name, script, accepts_pages, accepts_force)
STAGES = [
    ("raster",   "rasterize.py",       True,  True),
    ("assemble", "assemble_content.py", False, False),
    ("slide",    "render_slide.py",    False, True),
    ("tts",      "tts.py",             False, True),
    ("srt",      "build_srt.py",       False, False),
    ("timeline", "timeline.py",        False, False),
    ("caption",  "render_caption.py",  False, True),
    ("compose",  "compose.py",         False, True),
    ("concat",   "concat.py",          False, False),
    ("snapshot", "snapshot.py",        False, False),
]
STAGE_NAMES = [s[0] for s in STAGES]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--pages", help="e.g. 1-5 (required if running the raster stage)")
    ap.add_argument("--from", dest="from_stage", default="raster", choices=STAGE_NAMES)
    ap.add_argument("--only", help="run just this one stage", choices=STAGE_NAMES)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    start = STAGE_NAMES.index(args.from_stage)
    todo = [s for s in STAGES if (s[0] == args.only)] if args.only \
        else STAGES[start:]

    for name, script, accepts_pages, accepts_force in todo:
        cmd = [PY, str(SCRIPTS / script), "--pdf", args.pdf]
        if accepts_pages:
            if not args.pages:
                raise SystemExit(f"stage '{name}' needs --pages")
            cmd += ["--pages", args.pages]
        if accepts_force and args.force:
            cmd += ["--force"]
        print(f"\n=== [{name}] {' '.join(cmd[1:])} ===", flush=True)
        r = subprocess.run(cmd)
        if r.returncode != 0:
            sys.stderr.write(f"\n[render] stage '{name}' failed (exit {r.returncode})\n")
            raise SystemExit(r.returncode)

    print("\n[render] pipeline complete ✓")


if __name__ == "__main__":
    main()
