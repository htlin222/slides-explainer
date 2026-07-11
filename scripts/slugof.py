#!/usr/bin/env python3
"""Print the production slug for a PDF (same rule as the pipeline)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as C  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: slugof.py <pdf>")
    print(C.slugify(Path(sys.argv[1]).stem))
