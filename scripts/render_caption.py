#!/usr/bin/env python3
"""S7 render captions: each unique cue text -> a full-frame transparent PNG with a
bottom caption band (via headless Chrome). Cached on (text, caption style, WxH) so
a style tweak re-renders only what changed. compose.py resolves cue -> PNG with the
same hash function.
"""
from __future__ import annotations

import argparse
import html as _html
import json
from pathlib import Path

import common as C
import validate
from defaults import DEFAULT_STYLE


def caption_png_name(text: str, cs: dict, W: int, H: int) -> str:
    key = C.sha256_text(json.dumps([text, cs, W, H], ensure_ascii=False, sort_keys=True))
    return f"cap-{key[:16]}.png"


def _rgba(hex_color: str, opacity: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{opacity})"


def build_html(text: str, cs: dict, W: int, H: int) -> str:
    band_bg = _rgba(cs["band_color"], cs["band_opacity"])
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
  html,body {{ margin:0; padding:0; width:{W}px; height:{H}px;
               background:transparent; overflow:hidden; }}
  .wrap {{ position:absolute; left:0; right:0; bottom:{cs['y_from_bottom']}px;
           display:flex; justify-content:center; }}
  .band {{ max-width:{cs['max_width_pct']}%;
           font-family:{cs['font_family']}; font-size:{cs['font_size']}px;
           font-weight:{cs['font_weight']}; color:{cs['color']};
           background:{band_bg}; padding:{cs['band_pad_y']}px {cs['band_pad_x']}px;
           border-radius:{cs['band_radius']}px; text-align:center;
           line-height:1.28; -webkit-font-smoothing:antialiased;
           text-shadow:0 2px 6px rgba(0,0,0,0.55); box-sizing:border-box; }}
</style></head><body>
  <div class="wrap"><div class="band">{_html.escape(text)}</div></div>
</body></html>"""


def render_all(prod: C.Prod, style: dict, force: bool) -> dict:
    cs = style["caption"]
    if not cs.get("burn", True):
        print("captions: burn=false -> soft subtitles, skipping PNG render")
        return {}
    W, H = style["video"]["width"], style["video"]["height"]
    content = C.load_json(prod.content_path)
    mapping = {}
    n = 0
    for page in content["pages"]:
        for seg in page["segments"]:
            srt = prod.audio / f"{seg['id']}.srt"
            if not srt.exists():
                continue
            for cue in C.parse_srt(srt):
                text = cue["text"]
                name = caption_png_name(text, cs, W, H)
                out = prod.captions / name
                mapping[text] = name
                if force or not out.exists():
                    C.chrome_screenshot(build_html(text, cs, W, H), out, W, H, transparent=True)
                    validate.validate_png(out, W, H)
                    n += 1
    C.save_json(prod.captions / "index.json", mapping)
    print(f"captions: rendered {n} new, {len(mapping)} unique cue(s)")
    return mapping


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    prod = C.Prod(Path(args.pdf))
    style = C.load_json(prod.style_path, DEFAULT_STYLE)
    render_all(prod, style, args.force)


if __name__ == "__main__":
    main()
