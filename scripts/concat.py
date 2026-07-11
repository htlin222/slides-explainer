#!/usr/bin/env python3
"""S9 concat: join segment clips in timeline order -> final.mp4 (+ master.srt sidecar).

Clips share identical codec params, so the concat demuxer with -c copy is exact
and fast. Falls back to a re-encode if copy is rejected.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import common as C
import validate
from defaults import DEFAULT_STYLE


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    args = ap.parse_args()

    prod = C.Prod(Path(args.pdf))
    style = C.load_json(prod.style_path, DEFAULT_STYLE)
    tl = C.load_json(prod.timeline_path)

    listfile = prod.dir / "concat.txt"
    lines = []
    for seg in tl["segments"]:
        mp4 = prod.segments / f"{seg['id']}.mp4"
        if not mp4.exists():
            raise SystemExit(f"missing segment clip: {mp4}")
        lines.append(f"file '{mp4.as_posix()}'")
    listfile.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out = prod.final_mp4
    burn = style["caption"].get("burn", True)
    joined = out if burn else (prod.dir / "_joined.mp4")
    try:
        C.run([C.FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
               "-c", "copy", "-movflags", "+faststart", str(joined)])
    except Exception:
        v = style["video"]
        C.run([C.FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(listfile),
               "-r", str(v["fps"]), "-c:v", v["vcodec"], "-pix_fmt", v["pix_fmt"],
               "-crf", str(v["crf"]), "-preset", v["preset"],
               "-c:a", v["acodec"], "-b:a", v["abitrate"], "-ar", "48000", "-ac", "2",
               "-movflags", "+faststart", str(joined)])

    if not burn:
        # captions weren't burned in; embed master.srt as a selectable soft track
        C.run([C.FFMPEG, "-y", "-i", str(joined), "-i", str(prod.master_srt),
               "-c", "copy", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng",
               "-movflags", "+faststart", str(out)])
        joined.unlink(missing_ok=True)

    expected_ms = round(tl["total_frames"] / tl["fps"] * 1000)
    ms = validate.validate_final(out, expected_ms)
    mode = "burned-in" if burn else "soft mov_text"
    print(f"final.mp4: {ms/1000:.1f}s (expected {expected_ms/1000:.1f}s) [{mode} subtitles]  ->  {out}")
    print(f"master.srt sidecar: {prod.master_srt}")


if __name__ == "__main__":
    main()
