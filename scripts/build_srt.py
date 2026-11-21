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
import string
from pathlib import Path

import common as C
import validate
from defaults import DEFAULT_STYLE

# Words we never want a caption line to END on: stranding them reads badly and
# is exactly what greedy char-fill used to do ("...cheat sheet for", "...is the").
TRAILING_BAD = frozenset("""
a an the this that these those my your his her its our their
of in on at to for with from by as into onto upon about over under
between through during before after above below off out up down near
and or but nor so yet
is are was were be been being am
has have had do does did
will would shall should can could may might must
""".split())

# Clause/coordination starters: breaking JUST BEFORE these is natural, so we make
# a break at that gap cheap ("...MYC control, | and that's Burkitt").
CLAUSE_STARTERS = frozenset("""
and but or nor so yet because although though while when where which who whom
whose that if unless until since as
""".split())

_END_PUNCT = tuple(".!?")          # sentence end
_SOFT_PUNCT = tuple(",;:")         # clause/phrase break
_DASHES = ("—", "–", "-")  # em/en/hyphen


def _bare(word: str) -> str:
    """Lowercased word with surrounding punctuation stripped (for classifying)."""
    return word.strip(string.punctuation + "—–“”‘’").lower()


def _break_cost(prev: str, nxt: str) -> int:
    """Penalty for breaking a caption line between `prev` and `nxt`.

    Lower = more natural. Punctuation gaps are near-free; stranding a function
    word is expensive; landing just before a clause starter is cheap.
    """
    p = prev.rstrip(string.punctuation + "—–“”‘’")
    ends_end = prev.endswith(_END_PUNCT)
    ends_soft = prev.endswith(_SOFT_PUNCT) or prev.endswith(_DASHES)
    if ends_end:
        return 0
    if ends_soft:
        cost = 1
    else:
        cost = 10
    if _bare(prev) in TRAILING_BAD:      # don't end a line on a function word
        cost += 40
    if _bare(nxt) in CLAUSE_STARTERS:    # breaking before a clause is natural
        cost = min(cost, 2)
    return cost


def wrap_words(text: str, max_chars: int) -> list[str]:
    """Break text into lines of <= max_chars, minimizing total break penalty.

    A DP (Knuth-Plass-style) over word gaps: every candidate line must fit in
    max_chars (a single over-long word is allowed to overflow so we never split
    a word), and among all fitting layouts we pick the one whose break points
    land on the most natural boundaries — punctuation and clause edges, never
    stranded articles/prepositions/conjunctions.
    """
    words = text.split()
    n = len(words)
    if n <= 1:
        return words or [text]

    # width[i][j] = char length of "words[i..j-1]" joined by single spaces
    def width(i: int, j: int) -> int:
        return sum(len(words[k]) for k in range(i, j)) + (j - i - 1)

    INF = float("inf")
    best = [INF] * (n + 1)
    prev_break = [0] * (n + 1)
    best[0] = 0
    for j in range(1, n + 1):
        for i in range(j - 1, -1, -1):
            if i < j - 1 and width(i, j) > max_chars:
                break  # longer runs only get wider; stop scanning
            # cost of the break AFTER this line (none for the final line)
            step = 0 if j == n else _break_cost(words[j - 1], words[j])
            cand = best[i] + step
            if cand < best[j]:
                best[j] = cand
                prev_break[j] = i
    # reconstruct line boundaries
    cuts = []
    j = n
    while j > 0:
        i = prev_break[j]
        cuts.append((i, j))
        j = i
    cuts.reverse()
    return [" ".join(words[i:j]) for i, j in cuts]


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
    ap.add_argument("--pdf")
    ap.add_argument("--slug", help="rebuild by slug when the source PDF isn't at hand")
    args = ap.parse_args()
    if not args.pdf and not args.slug:
        ap.error("one of --pdf or --slug is required")

    pdf = Path(args.pdf) if args.pdf else Path(f"{args.slug}.pdf")
    prod = C.Prod(pdf, slug=args.slug)
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
