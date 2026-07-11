#!/usr/bin/env python3
"""S5 build SRT: boundary events -> readable per-segment SRT (local timeline).

Andrew emits one SentenceBoundary per sentence. A sentence longer than
`caption.max_chars_per_cue` is split into sub-cues at word gaps, with the
sentence's time span allocated proportionally to each sub-cue's character count
(deterministic). Cues then HOLD to the next cue's start so there is never a blank
gap flicker inside a segment (vox-styled-reels scanHoldIndex lesson).
"""
from __future__ import annotations

import argparse
from pathlib import Path

import common as C
import validate
from defaults import DEFAULT_STYLE


def wrap_words(text: str, max_chars: int) -> list[str]:
    """Greedy word-wrap into lines of <= max_chars (never splits a word)."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if not cur:
            cur = w
        elif len(cur) + 1 + len(w) <= max_chars:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [text]


def cues_for_segment(bounds, max_chars: int) -> list[dict]:
    """Turn boundary events into local-timeline cues."""
    raw = []
    for b in bounds:
        start = float(b["start_ms"])
        end = start + float(b["dur_ms"])
        text = b["text"].strip()
        if not text:
            continue
        parts = wrap_words(text, max_chars)
        if len(parts) == 1:
            raw.append({"start_ms": start, "end_ms": end, "text": parts[0]})
            continue
        # allocate [start, end] to parts by character proportion
        total_chars = sum(len(p) for p in parts)
        span = end - start
        acc = 0
        for p in parts:
            s = start + span * (acc / total_chars)
            acc += len(p)
            e = start + span * (acc / total_chars)
            raw.append({"start_ms": s, "end_ms": e, "text": p})
    raw.sort(key=lambda c: c["start_ms"])
    # HOLD each cue to the next cue's start (no blank gaps within the segment)
    for i in range(len(raw) - 1):
        raw[i]["end_ms"] = raw[i + 1]["start_ms"]
    # round to int ms
    for c in raw:
        c["start_ms"] = int(round(c["start_ms"]))
        c["end_ms"] = max(c["start_ms"] + 200, int(round(c["end_ms"])))
    return raw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    args = ap.parse_args()

    prod = C.Prod(Path(args.pdf))
    style = C.load_json(prod.style_path, DEFAULT_STYLE)
    max_chars = style["caption"]["max_chars_per_cue"]
    content = C.load_json(prod.content_path)

    n = 0
    for page in content["pages"]:
        for seg in page["segments"]:
            sid = seg["id"]
            bounds = C.load_json(prod.audio / f"{sid}.bound.json", [])
            cues = cues_for_segment(bounds, max_chars)
            srt = prod.audio / f"{sid}.srt"
            C.write_srt(cues, srt)
            audio_ms = C.probe_duration_ms(prod.audio / f"{sid}.mp3")
            validate.validate_srt(C.parse_srt(srt), audio_ms)  # lint after build
            n += 1
            print(f"srt {sid}: {len(cues)} cue(s)")
    print(f"built {n} SRT file(s)")


if __name__ == "__main__":
    main()
