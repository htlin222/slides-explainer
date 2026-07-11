#!/usr/bin/env python3
"""S1/S2 commit: fold ai/page-NNN.json (subagent output) into config/content.json.

Each ai file is one of:
  title:   {"index","kind":"title","title_voiceover"}
  content: {"index","kind":"content","content_voiceover","keypoints":[...],
            "keypoint_voiceover"}

Produces per-page `segments` in canonical order:
  title  -> [ {role:title,   voiceover} ]
  content-> [ {role:content, voiceover},
              {role:keypoint, voiceover, keypoints:[...]} ]
"""
from __future__ import annotations

import argparse
from pathlib import Path

import common as C


def segments_for(ai: dict) -> list[dict]:
    kind = ai["kind"]
    if kind == "title":
        return [{"role": "title", "voiceover": ai["title_voiceover"].strip()}]
    if kind == "content":
        return [
            {"role": "content", "voiceover": ai["content_voiceover"].strip()},
            {
                "role": "keypoint",
                "voiceover": ai["keypoint_voiceover"].strip(),
                "keypoints": [k.strip() for k in ai["keypoints"]],
            },
        ]
    raise ValueError(f"unknown kind: {kind}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    args = ap.parse_args()

    prod = C.Prod(Path(args.pdf))
    content = C.load_json(prod.content_path)
    if content is None:
        raise SystemExit("content.json missing; run rasterize first")

    ai_dir = prod.dir / "ai"
    by_index = {p["index"]: p for p in content["pages"]}
    for ai_file in sorted(ai_dir.glob("page-*.json")):
        ai = C.load_json(ai_file)
        idx = ai["index"]
        if idx not in by_index:
            continue
        page = by_index[idx]
        page["kind"] = ai["kind"]
        page["segments"] = segments_for(ai)
        # stamp segment ids for downstream stages
        for seg in page["segments"]:
            seg["id"] = C.seg_id(idx, seg["role"])
            seg["page"] = idx

    content["pages"] = [by_index[k] for k in sorted(by_index)]
    C.save_json(prod.content_path, content)

    n_seg = sum(len(p["segments"]) for p in content["pages"])
    kinds = {p["index"]: p["kind"] for p in content["pages"]}
    print(f"assembled content.json: {len(content['pages'])} pages, {n_seg} segments")
    print("kinds:", kinds)


if __name__ == "__main__":
    main()
