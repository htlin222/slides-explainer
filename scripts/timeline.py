#!/usr/bin/env python3
"""S6 timeline: deterministic clip lengths + global offsets + master.srt.

Pure arithmetic over measured audio durations and per-segment local SRTs. Given
the same audio + SRT snapshot it always yields the same timeline, so any render
downstream is reproducible.

Per segment the clip is:  [lead silence][speech][tail silence]
    clip_frames = ceil((lead + audio_s + tail) * fps)
The last segment's tail gets an extra end_hold.
Global start_ms accumulates clip_frames; master.srt shifts each segment's local
cues by (start_ms + lead_ms).
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import common as C
from defaults import DEFAULT_STYLE


def ordered_segments(content):
    """Flatten pages -> segments in play order (title; or content then keypoint)."""
    for page in content["pages"]:
        for seg in page["segments"]:
            yield page, seg


def slide_for(page, seg):
    if seg["role"] == "keypoint":
        return f"slides/kp-{page['index']:03d}.png"
    return page["image"]  # title & content use the rasterized page


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    args = ap.parse_args()

    prod = C.Prod(Path(args.pdf))
    style = C.load_json(prod.style_path, DEFAULT_STYLE)
    fps = style["video"]["fps"]
    g = style["gaps_s"]
    content = C.load_json(prod.content_path)

    segs = list(ordered_segments(content))
    tl = {"fps": fps, "segments": [], "total_frames": 0, "master_srt": "master.srt"}
    master_cues = []
    acc_frames = 0

    for i, (page, seg) in enumerate(segs):
        sid = seg["id"]
        role = seg["role"]
        mp3 = prod.audio / f"{sid}.mp3"
        audio_ms = C.probe_duration_ms(mp3)
        lead = g["lead"]
        tail = {"title": g["title_settle"], "content": g["post_content"],
                "keypoint": g["post_keypoint"]}[role]
        if i == len(segs) - 1:
            tail += g["end_hold"]
        clip_frames = math.ceil((lead + audio_ms / 1000.0 + tail) * fps)
        lead_ms = int(round(lead * 1000))

        rec = {
            "id": sid, "role": role, "page": page["index"],
            "slide": slide_for(page, seg),
            "audio": f"audio/{sid}.mp3", "audio_ms": audio_ms,
            "srt_local": f"audio/{sid}.srt",
            "lead_ms": lead_ms, "tail_ms": int(round(tail * 1000)),
            "clip_frames": clip_frames,
            "start_frame": acc_frames,
            "start_ms": int(round(acc_frames / fps * 1000)),
            "end_frame": acc_frames + clip_frames,
        }
        tl["segments"].append(rec)

        # offset local SRT into the global master track
        srt = prod.audio / f"{sid}.srt"
        if srt.exists():
            base = rec["start_ms"] + lead_ms
            for c in C.parse_srt(srt):
                master_cues.append({
                    "start_ms": base + c["start_ms"],
                    "end_ms": base + c["end_ms"],
                    "text": c["text"],
                })
        acc_frames += clip_frames

    tl["total_frames"] = acc_frames
    tl["total_ms"] = int(round(acc_frames / fps * 1000))
    C.save_json(prod.timeline_path, tl)
    C.write_srt(master_cues, prod.master_srt)

    # deterministic self-checks
    assert sum(s["clip_frames"] for s in tl["segments"]) == tl["total_frames"]
    for a, b in zip(tl["segments"], tl["segments"][1:]):
        assert b["start_frame"] == a["end_frame"], "timeline frames not contiguous"

    print(f"timeline: {len(tl['segments'])} segments, "
          f"{tl['total_frames']} frames ({tl['total_ms']/1000:.1f}s), "
          f"{len(master_cues)} master cues")


if __name__ == "__main__":
    main()
