"""Shared helpers for the slides-explainer pipeline.

Everything here is deterministic and side-effect-light so the stage scripts can
stay small. Paths are resolved relative to a per-PDF production directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Tool paths default to a local macOS setup but are env-overridable so the same
# code runs unchanged on Linux CI (set FFMPEG_BIN=ffmpeg, CHROME_BIN=..., etc.).
FFMPEG = os.environ.get("FFMPEG_BIN", "/opt/homebrew/bin/ffmpeg")
FFPROBE = os.environ.get("FFPROBE_BIN", "/opt/homebrew/bin/ffprobe")
PDFTOPPM = os.environ.get("PDFTOPPM_BIN", "/opt/homebrew/bin/pdftoppm")
PDFINFO = os.environ.get("PDFINFO_BIN", "/opt/homebrew/bin/pdfinfo")
CHROME = os.environ.get(
    "CHROME_BIN", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
)


# ---------------------------------------------------------------- slug / paths
def slugify(name: str) -> str:
    """Filesystem-safe slug from a PDF stem (keeps ascii/num, collapses rest)."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^A-Za-z0-9]+", "-", ascii_only).strip("-").lower()
    # keep a short hash of the original so different CJK names never collide
    tag = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
    return f"{s or 'pdf'}-{tag}"


def kebab(text: str, max_len: int = 48) -> str:
    """Human-readable kebab slug (no hash) for AI-proposed names."""
    nfkd = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", nfkd).strip("-").lower()
    return s[:max_len].strip("-") or "deck"


# registry mapping repo-relative PDF path -> chosen slug (committed, CI reads it)
SLUG_INDEX = ROOT / "production" / "index.json"


def slug_map() -> dict:
    return load_json(SLUG_INDEX, {}) or {}


def resolve_slug(pdf: Path) -> str:
    """AI-registered slug if present, else the deterministic filename slug."""
    return slug_map().get(repo_rel(pdf)) or slugify(Path(pdf).stem)


class Prod:
    """Handle for one production directory: production/<slug>/…"""

    def __init__(self, pdf_path: Path, slug: str | None = None):
        self.pdf = Path(pdf_path).resolve()
        self.slug = slug or resolve_slug(self.pdf)
        self.dir = ROOT / "production" / self.slug
        self.config = self.dir / "config"
        self.pages = self.dir / "pages"
        self.slides = self.dir / "slides"
        self.audio = self.dir / "audio"
        self.captions = self.dir / "captions"
        self.segments = self.dir / "segments"

    def ensure(self):
        for p in (self.config, self.pages, self.slides, self.audio,
                  self.captions, self.segments):
            p.mkdir(parents=True, exist_ok=True)
        return self

    # canonical config files
    @property
    def style_path(self):
        return self.config / "style.json"

    @property
    def content_path(self):
        return self.config / "content.json"

    @property
    def timeline_path(self):
        return self.config / "timeline.json"

    @property
    def lock_path(self):
        return self.config / "render.lock.json"

    @property
    def master_srt(self):
        return self.dir / f"{self.slug}.srt"

    @property
    def final_mp4(self):
        return self.dir / f"{self.slug}.mp4"


# ---------------------------------------------------------------- json / hash
def load_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- subprocess
def run(cmd, **kw):
    """Run a command, raising with captured stderr on failure."""
    kw.setdefault("check", True)
    kw.setdefault("text", True)
    kw.setdefault("capture_output", True)
    try:
        return subprocess.run(cmd, **kw)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"\n[run] command failed: {' '.join(map(str, cmd))}\n")
        sys.stderr.write((e.stderr or "")[-2000:] + "\n")
        raise


def repo_rel(path) -> str:
    """Path relative to the repo root if inside it, else the plain string.

    Committed config must store repo-relative paths so cloud CI (a different
    absolute checkout dir) resolves them.
    """
    p = Path(path).resolve()
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return str(p)


def pdf_page_count(pdf: Path) -> int:
    out = run([PDFINFO, str(pdf)]).stdout
    for line in out.splitlines():
        if line.lower().startswith("pages:"):
            return int(line.split(":", 1)[1].strip())
    raise RuntimeError(f"could not read page count from pdfinfo: {pdf}")


def tool_version(cmd) -> str:
    try:
        out = subprocess.run(cmd, text=True, capture_output=True)
        return (out.stdout or out.stderr).splitlines()[0].strip()
    except Exception as e:  # noqa: BLE001
        return f"unknown ({e})"


# ---------------------------------------------------------------- media probes
def probe_duration_ms(path: Path) -> int:
    out = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", str(path)]).stdout.strip()
    return int(round(float(out) * 1000))


def probe_wh(path: Path):
    out = run([FFPROBE, "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height", "-of", "csv=p=0",
               str(path)]).stdout.strip()
    w, h = out.split(",")[:2]
    return int(w), int(h)


# ---------------------------------------------------------------- chrome render
def chrome_screenshot(html: str, out_png: Path, width: int, height: int,
                      transparent: bool = False):
    """Render an HTML string to a PNG of exact width x height via headless Chrome."""
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    tmp_html = out_png.with_suffix(".html")
    tmp_html.write_text(html, encoding="utf-8")
    cmd = [
        CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
        "--hide-scrollbars", "--force-device-scale-factor=1",
        f"--screenshot={out_png}", f"--window-size={width},{height}",
    ]
    if transparent:
        cmd.append("--default-background-color=00000000")
    cmd.append(tmp_html.as_uri())
    run(cmd)
    tmp_html.unlink(missing_ok=True)
    return out_png


# ---------------------------------------------------------------- SRT helpers
def ms_to_srt_ts(ms: int) -> str:
    ms = max(0, int(round(ms)))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(cues, path: Path):
    """cues: list of dicts {start_ms, end_ms, text}."""
    lines = []
    for i, c in enumerate(cues, 1):
        lines.append(str(i))
        lines.append(f"{ms_to_srt_ts(c['start_ms'])} --> {ms_to_srt_ts(c['end_ms'])}")
        lines.append(c["text"])
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def parse_srt(path: Path):
    text = Path(path).read_text(encoding="utf-8")
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        rows = [r for r in block.splitlines() if r.strip()]
        if len(rows) < 2:
            continue
        m = re.search(r"(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)", rows[1])
        if not m:
            continue
        a = list(map(int, m.groups()))
        start = ((a[0] * 60 + a[1]) * 60 + a[2]) * 1000 + a[3]
        end = ((a[4] * 60 + a[5]) * 60 + a[6]) * 1000 + a[7]
        cues.append({"start_ms": start, "end_ms": end, "text": " ".join(rows[2:])})
    return cues


# ---------------------------------------------------------------- segment ids
ROLE_LETTER = {"title": "t", "content": "a", "keypoint": "b"}


def seg_id(page_index: int, role: str) -> str:
    return f"seg-{page_index:03d}{ROLE_LETTER[role]}"
