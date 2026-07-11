#!/usr/bin/env python3
"""S3 render keypoint cards: keypoints[] + style -> slides/kp-NNN.png (WxH).

Idempotent: cached on a hash of (keypoints, keypoint style, video size). Only the
keypoint segments of content pages get a generated card.
"""
from __future__ import annotations

import argparse
import html as _html
import json
from pathlib import Path

import common as C
import validate
from defaults import DEFAULT_STYLE


def build_html(keypoints, ks, W, H) -> str:
    items = "\n".join(
        f'<li>{_html.escape(k)}</li>' for k in keypoints[: ks["max_points"]]
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  html,body {{ margin:0; padding:0; }}
  body {{ width:{W}px; height:{H}px; background:{ks['bg']};
          font-family:{ks['font_family']}; -webkit-font-smoothing:antialiased;
          box-sizing:border-box; padding:{ks['pad_top']}px {ks['pad_x']}px;
          display:flex; flex-direction:column; }}
  .title {{ font-size:{ks['title_size']}px; font-weight:700;
            color:{ks['title_color']}; margin:0 0 8px 0; }}
  .rule {{ height:4px; width:160px; background:{ks['accent']};
           border-radius:2px; margin:0 0 40px 0; }}
  ul {{ list-style:none; margin:0; padding:0; }}
  li {{ position:relative; font-size:{ks['bullet_size']}px;
        color:{ks['bullet_color']}; line-height:{ks['bullet_line_height']};
        margin:0 0 22px 0; padding-left:44px; }}
  li:before {{ content:""; position:absolute; left:0; top:0.62em;
               width:16px; height:16px; border-radius:50%;
               background:{ks['accent']}; }}
</style></head><body>
  <div class="title">{_html.escape(ks['title'])}</div>
  <div class="rule"></div>
  <ul>
  {items}
  </ul>
</body></html>"""


def render_page(prod: C.Prod, page: dict, style: dict, force: bool):
    ks = style["keypoint"]
    W, H = style["video"]["width"], style["video"]["height"]
    for seg in page["segments"]:
        if seg["role"] != "keypoint":
            continue
        keypoints = seg.get("keypoints", [])
        validate.validate_keypoints(keypoints, ks)   # lint before render
        out = prod.slides / f"kp-{page['index']:03d}.png"
        cache_key = C.sha256_text(json.dumps([keypoints, ks, W, H], ensure_ascii=False, sort_keys=True))
        stamp = out.with_suffix(".hash")
        if not force and out.exists() and stamp.exists() and stamp.read_text() == cache_key:
            continue
        C.chrome_screenshot(build_html(keypoints, ks, W, H), out, W, H, transparent=False)
        validate.validate_png(out, W, H)             # lint after render
        stamp.write_text(cache_key)
        seg["slide"] = f"slides/{out.name}"
        print(f"rendered {out.name}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    prod = C.Prod(Path(args.pdf))
    style = C.load_json(prod.style_path, DEFAULT_STYLE)
    content = C.load_json(prod.content_path)
    for page in content["pages"]:
        if page["kind"] == "content":
            render_page(prod, page, style, args.force)
    C.save_json(prod.content_path, content)


if __name__ == "__main__":
    main()
