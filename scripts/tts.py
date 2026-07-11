#!/usr/bin/env python3
"""S4 TTS: synth each segment's voiceover -> audio/<id>.mp3 + audio/<id>.bound.json.

Robustness (per vox-styled-reels wiki):
  * retry 3x with linear backoff on edge-tts hiccups / empty streams
  * cache keyed on (text, voice, rate, volume); only re-synth when spoken text changes

Andrew (and other Conversation/Copilot voices) emit SentenceBoundary events, not
WordBoundary; we capture whatever boundary events come and store them verbatim
(ticks -> ms) for the SRT builder.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import edge_tts

import common as C
import validate
import volint
from defaults import DEFAULT_STYLE


def synth(text, voice, rate, volume, mp3_path: Path, bound_path: Path, attempts=3):
    last = None
    for i in range(1, attempts + 1):
        try:
            comm = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
            audio = bytearray()
            bounds = []
            for chunk in comm.stream_sync():
                t = chunk.get("type")
                if t == "audio":
                    audio += chunk["data"]
                elif t in ("WordBoundary", "SentenceBoundary"):
                    bounds.append({
                        "text": chunk["text"],
                        "start_ms": round(chunk["offset"] / 10000.0, 1),
                        "dur_ms": round(chunk["duration"] / 10000.0, 1),
                        "kind": t,
                    })
            if not audio:
                raise RuntimeError("empty audio stream")
            mp3_path.write_bytes(bytes(audio))
            C.save_json(bound_path, bounds)
            return
        except Exception as e:  # noqa: BLE001
            last = e
            sys.stderr.write(f"[tts] {mp3_path.name} attempt {i}/{attempts} failed: {e}\n")
            time.sleep(i * 3)
    raise RuntimeError(f"TTS failed for {mp3_path.name} after {attempts} attempts: {last}")


def each_segment(content):
    for page in content["pages"]:
        for seg in page["segments"]:
            yield seg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--shard", type=int, default=0, help="this worker's shard index")
    ap.add_argument("--of", type=int, default=1, help="total number of shards")
    args = ap.parse_args()
    if not (0 <= args.shard < args.of):
        raise SystemExit("--shard must be in [0, --of)")

    prod = C.Prod(Path(args.pdf)).ensure()
    style = C.load_json(prod.style_path, DEFAULT_STYLE)
    tts = style["tts"]
    voice, rate, volume = tts["voice"], tts["rate"], tts["volume"]
    content = C.load_json(prod.content_path)

    # TTS is embarrassingly parallel; each worker synthesizes its slice of
    # segments. timeline.py (a downstream barrier) needs ALL audio, so a gather
    # job collects every shard's audio before computing offsets.
    segs = [s for i, s in enumerate(each_segment(content)) if i % args.of == args.shard]
    n = 0
    for seg in segs:
        sid = seg["id"]
        text = volint.clean(seg["voiceover"])       # deterministic TTS-safe normalize
        for issue in volint.lint(text):
            sys.stderr.write(f"[volint] {sid}: {issue}\n")
        mp3 = prod.audio / f"{sid}.mp3"
        bound = prod.audio / f"{sid}.bound.json"
        stamp = prod.audio / f"{sid}.hash"
        key = C.sha256_text("\x1f".join([text, voice, rate, volume]))
        if (not args.force and mp3.exists() and bound.exists()
                and stamp.exists() and stamp.read_text() == key):
            continue
        synth(text, voice, rate, volume, mp3, bound, attempts=3)
        validate.validate_audio(mp3, bound)          # lint after synth
        stamp.write_text(key)
        n += 1
        print(f"tts {sid} ({len(text)} chars)")
    print(f"shard {args.shard}/{args.of}: synthesized {n} of {len(segs)} segment(s)")


if __name__ == "__main__":
    main()
