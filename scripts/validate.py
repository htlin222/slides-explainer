#!/usr/bin/env python3
"""Per-artifact validators: every stage validates its output before the next
stage consumes it ("lenient in, strict out"). Import the helpers into a stage,
or run standalone to gate a whole production dir:

    python scripts/validate.py --pdf <pdf> [--stage pages|content|audio|srt|segments|final|all]

All checks use only ffprobe + file inspection (no extra deps).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import common as C
from defaults import DEFAULT_STYLE


class ValidationError(Exception):
    pass


def require(cond, msg):
    if not cond:
        raise ValidationError(msg)


# ------------------------------------------------------------------ artifacts
def validate_png(path: Path, w: int | None = None, h: int | None = None):
    path = Path(path)
    require(path.exists() and path.stat().st_size > 0, f"missing/empty PNG: {path}")
    pw, ph = C.probe_wh(path)
    require(pw > 0 and ph > 0, f"bad PNG dims: {path}")
    if w is not None:
        require((pw, ph) == (w, h), f"PNG {path.name} is {pw}x{ph}, expected {w}x{h}")
    return pw, ph


def validate_keypoints(keypoints, ks):
    require(3 <= len(keypoints) <= ks["max_points"] + 0,
            f"keypoints count {len(keypoints)} outside 3..{ks['max_points']}")
    for k in keypoints:
        require(bool(k.strip()), "empty keypoint line")
        require(len(k) <= 120, f"keypoint line too long ({len(k)} chars), may overflow: {k[:40]}…")


def validate_content(content, style):
    require(content and content.get("pages"), "content.json has no pages")
    ks = style["keypoint"]
    for p in content["pages"]:
        require(p.get("kind") in ("content", "title"), f"page {p['index']} unclassified")
        require(p.get("segments"), f"page {p['index']} has no segments")
        for seg in p["segments"]:
            require(seg.get("id"), f"page {p['index']} segment missing id")
            require(bool(seg.get("voiceover", "").strip()),
                    f"{seg.get('id')} empty voiceover")
            if seg["role"] == "keypoint":
                validate_keypoints(seg.get("keypoints", []), ks)


def validate_audio(mp3: Path, bound_path: Path):
    mp3 = Path(mp3)
    require(mp3.exists() and mp3.stat().st_size > 500, f"missing/tiny mp3: {mp3}")
    ms = C.probe_duration_ms(mp3)
    require(ms >= 200, f"audio too short ({ms} ms): {mp3}")
    bounds = C.load_json(bound_path, [])
    require(len(bounds) >= 1, f"no boundary events: {bound_path}")
    last_end = max((b["start_ms"] + b["dur_ms"]) for b in bounds)
    require(last_end <= ms + 1500, f"boundaries overrun audio: {last_end:.0f} > {ms}")
    return ms


def validate_srt(cues, audio_ms: int):
    require(len(cues) >= 1, "SRT has no cues")
    prev_start = -1
    for c in cues:
        require(c["start_ms"] >= 0, "negative cue start")
        require(c["end_ms"] > c["start_ms"], f"non-positive cue duration @ {c['start_ms']}ms")
        require(c["start_ms"] >= prev_start, "cue starts not monotonic")
        require(bool(c["text"].strip()), "empty cue text")
        prev_start = c["start_ms"]
    require(cues[-1]["end_ms"] <= audio_ms + 2000,
            f"last cue {cues[-1]['end_ms']}ms overruns audio {audio_ms}ms")


def validate_segment(mp4: Path, w: int, h: int, expected_ms: int, tol_ms: int = 200):
    mp4 = Path(mp4)
    require(mp4.exists() and mp4.stat().st_size > 1000, f"missing/tiny segment: {mp4}")
    pw, ph = C.probe_wh(mp4)
    require((pw, ph) == (w, h), f"segment {mp4.name} is {pw}x{ph}, expected {w}x{h}")
    # audio stream present
    out = C.run([C.FFPROBE, "-v", "error", "-select_streams", "a:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(mp4)]).stdout.strip()
    require(out == "audio", f"segment {mp4.name} has no audio stream")
    ms = C.probe_duration_ms(mp4)
    require(abs(ms - expected_ms) <= tol_ms,
            f"segment {mp4.name} duration {ms}ms != expected {expected_ms}ms (±{tol_ms})")
    return ms


def validate_final(mp4: Path, expected_ms: int, tol_ms: int = 500):
    mp4 = Path(mp4)
    require(mp4.exists() and mp4.stat().st_size > 10000, f"missing/tiny final: {mp4}")
    ms = C.probe_duration_ms(mp4)
    require(abs(ms - expected_ms) <= tol_ms,
            f"final duration {ms}ms != expected {expected_ms}ms (±{tol_ms})")
    return ms


# ------------------------------------------------------------------ CLI gate
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--stage", default="all",
                    choices=["pages", "content", "audio", "srt", "segments", "final", "all"])
    args = ap.parse_args()

    prod = C.Prod(Path(args.pdf))
    style = C.load_json(prod.style_path, DEFAULT_STYLE)
    content = C.load_json(prod.content_path)
    W, H = style["video"]["width"], style["video"]["height"]
    checks = 0

    def do(stage):
        return args.stage in (stage, "all")

    if do("pages"):
        for p in content["pages"]:
            validate_png(prod.dir / p["image"]); checks += 1
    if do("content"):
        validate_content(content, style); checks += 1
    if do("audio"):
        for p in content["pages"]:
            for seg in p["segments"]:
                validate_audio(prod.audio / f"{seg['id']}.mp3",
                               prod.audio / f"{seg['id']}.bound.json"); checks += 1
    if do("srt"):
        for p in content["pages"]:
            for seg in p["segments"]:
                srt = prod.audio / f"{seg['id']}.srt"
                if srt.exists():
                    ms = C.probe_duration_ms(prod.audio / f"{seg['id']}.mp3")
                    validate_srt(C.parse_srt(srt), ms); checks += 1
    if do("segments"):
        tl = C.load_json(prod.timeline_path)
        if tl:
            for s in tl["segments"]:
                validate_segment(prod.segments / f"{s['id']}.mp4", W, H,
                                 round(s["clip_frames"] / tl["fps"] * 1000)); checks += 1
    if do("final"):
        tl = C.load_json(prod.timeline_path)
        if tl:
            validate_final(prod.final_mp4, round(tl["total_frames"] / tl["fps"] * 1000)); checks += 1

    print(f"validate[{args.stage}]: {checks} check group(s) passed ✓")


if __name__ == "__main__":
    main()
