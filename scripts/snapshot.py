#!/usr/bin/env python3
"""S10 snapshot: freeze everything needed to rebuild this exact video.

render.lock.json = style + content + timeline + tool versions + sha256 of every
input artifact (page PNGs, keypoint cards, audio, SRTs, caption PNGs, final.mp4).
Given the same lock file and cached audio, a re-render is bit-reproducible.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import common as C
from defaults import DEFAULT_STYLE


def git_commit() -> str:
    try:
        r = subprocess.run(["git", "-C", str(C.ROOT), "rev-parse", "HEAD"],
                           text=True, capture_output=True)
        return r.stdout.strip() or "(not a git repo)"
    except Exception:  # noqa: BLE001
        return "(git unavailable)"


def hash_dir(prod: C.Prod) -> dict:
    out = {}
    for sub in ("pages", "slides", "audio", "captions", "segments"):
        d = getattr(prod, sub, prod.dir / sub)
        d = Path(d)
        for f in sorted(d.glob("*")):
            if f.is_file() and f.suffix in (".png", ".mp3", ".srt", ".mp4"):
                out[f"{sub}/{f.name}"] = C.sha256_file(f)
    if prod.final_mp4.exists():
        out["final.mp4"] = C.sha256_file(prod.final_mp4)
    if prod.master_srt.exists():
        out["master.srt"] = C.sha256_file(prod.master_srt)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    args = ap.parse_args()

    prod = C.Prod(Path(args.pdf))
    lock = {
        "slug": prod.slug,
        "pdf": C.repo_rel(prod.pdf),
        "git_commit": git_commit(),
        "tools": {
            "ffmpeg": C.tool_version([C.FFMPEG, "-version"]),
            "edge_tts": C.tool_version([sys.executable, "-c",
                                        "import edge_tts;print('edge-tts',edge_tts.__version__)"]),
            "chrome": C.tool_version([C.CHROME, "--version"]),
            "pdftoppm": C.tool_version([C.PDFTOPPM, "-v"]),
        },
        "style": C.load_json(prod.style_path, DEFAULT_STYLE),
        "content": C.load_json(prod.content_path),
        "timeline": C.load_json(prod.timeline_path),
        "artifacts_sha256": hash_dir(prod),
    }
    C.save_json(prod.lock_path, lock)
    print(f"snapshot -> {prod.lock_path} ({len(lock['artifacts_sha256'])} artifacts hashed)")


if __name__ == "__main__":
    main()
