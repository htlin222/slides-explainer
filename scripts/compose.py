#!/usr/bin/env python3
"""S8 compose: one deterministic clip per timeline segment.

    [slide looped WxH] + [caption PNGs overlaid on their time windows]
    + [speech delayed by lead, padded/trimmed to exact clip length]

Every clip has identical codec params (WxH, fps, yuv420p, aac 48k stereo) so S9
can concat with -c copy. Clip length == clip_frames / fps, exactly.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import common as C
import render_caption
import validate
from defaults import DEFAULT_STYLE


def build_clip(prod: C.Prod, style: dict, seg: dict, force: bool):
    v = style["video"]
    cs = style["caption"]
    W, H, fps = v["width"], v["height"], v["fps"]
    out = prod.segments / f"{seg['id']}.mp4"
    clip_s = seg["clip_frames"] / fps
    lead_ms = seg["lead_ms"]

    burn = cs.get("burn", True)
    slide = prod.dir / seg["slide"]
    mp3 = prod.dir / seg["audio"]
    cues = C.parse_srt(prod.audio / f"{seg['id']}.srt") if burn else []

    # cache key: everything that determines the pixels/audio of this clip
    key = C.sha256_text("|".join([
        C.sha256_file(slide), C.sha256_file(mp3),
        str([cs, v, seg["clip_frames"], lead_ms, burn]),
        str([(c["start_ms"], c["end_ms"], c["text"]) for c in cues]),
    ]))
    stamp = out.with_suffix(".hash")
    if not force and out.exists() and stamp.exists() and stamp.read_text() == key:
        return False

    inputs = ["-loop", "1", "-framerate", str(fps), "-t", f"{clip_s:.4f}", "-i", str(slide),
              "-i", str(mp3)]
    for cue in cues:  # only when burning
        png = prod.captions / render_caption.caption_png_name(cue["text"], cs, W, H)
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{clip_s:.4f}", "-i", str(png)]

    # video filtergraph: scale/pad slide, then (optionally) chain caption overlays
    fc = [
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
        f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,"
        f"fps={fps},format=rgba[v0]"
    ]
    cur = "v0"
    for k, cue in enumerate(cues):
        s = (lead_ms + cue["start_ms"]) / 1000.0
        e = (lead_ms + cue["end_ms"]) / 1000.0
        nxt = f"v{k+1}"
        fc.append(f"[{cur}][{2+k}:v]overlay=0:0:enable='between(t,{s:.3f},{e:.3f})'[{nxt}]")
        cur = nxt
    fc.append(f"[{cur}]format=yuv420p[vout]")
    fc.append(
        f"[1:a]adelay={lead_ms}:all=1,apad,atrim=0:{clip_s:.4f},"
        f"aresample=48000,aformat=sample_fmts=fltp:channel_layouts=stereo[aout]"
    )

    cmd = [C.FFMPEG, "-y", *inputs,
           "-filter_complex", ";".join(fc),
           "-map", "[vout]", "-map", "[aout]",
           "-r", str(fps), "-fps_mode", "cfr",
           "-c:v", v["vcodec"], "-pix_fmt", v["pix_fmt"],
           "-crf", str(v["crf"]), "-preset", v["preset"],
           "-c:a", v["acodec"], "-b:a", v["abitrate"], "-ar", "48000", "-ac", "2",
           "-t", f"{clip_s:.4f}", "-movflags", "+faststart", str(out)]
    C.run(cmd)

    expected_ms = round(seg["clip_frames"] / fps * 1000)
    validate.validate_segment(out, W, H, expected_ms)
    stamp.write_text(key)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--shard", type=int, default=0, help="this worker's shard index")
    ap.add_argument("--of", type=int, default=1, help="total number of shards")
    args = ap.parse_args()
    if not (0 <= args.shard < args.of):
        raise SystemExit("--shard must be in [0, --of)")

    prod = C.Prod(Path(args.pdf))
    style = C.load_json(prod.style_path, DEFAULT_STYLE)
    tl = C.load_json(prod.timeline_path)
    # each worker composes only its slice of segments (round-robin by ordinal),
    # so N parallel CI jobs share the compose cost; combine happens downstream.
    mine = [s for i, s in enumerate(tl["segments"]) if i % args.of == args.shard]
    built = 0
    for seg in mine:
        if build_clip(prod, style, seg, args.force):
            built += 1
            print(f"composed {seg['id']}.mp4 ({seg['clip_frames']} frames)")
    print(f"shard {args.shard}/{args.of}: composed {built} of {len(mine)} clip(s) "
          f"({len(tl['segments'])} total)")


if __name__ == "__main__":
    main()
