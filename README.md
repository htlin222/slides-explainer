# slides-explainer

Config-driven, deterministic pipeline that turns PDF lecture slides into
board-exam **explainer videos**: every content slide gets an English neural
voiceover with per-sentence synced subtitles, followed by an auto-generated
**Key Points** card (3–5 high-yield board points) with its own voiceover. Title
and outline slides get a short spoken intro. Subtitles are burned in; a global
`master.srt` is shipped alongside.

Built for hematology fellows prepping for boards, but the pipeline is generic.

## Why it looks the way it does

- **ffmpeg, not Remotion.** Each unit is a static slide + audio + captions, so
  ffmpeg is simpler and has no Chrome-download / CJK-font / asset-404 traps.
- **Captions are rendered PNGs, overlaid.** The local Homebrew ffmpeg is a
  minimal build with **no libass / drawtext**. So caption bands and Key Points
  cards are rendered by **headless Chrome** to PNG and composited with ffmpeg
  `overlay` — no system ffmpeg change needed.
- **Burn is a toggle (`style.caption.burn`).** `false` (default) skips all overlays
  (≈15–20× faster compose) and **soft-muxes `master.srt`** into `final.mp4` as a
  selectable `mov_text` track — player-toggleable, near-instant. `true` hard-burns
  the captions for platforms that need baked-in subs. Either way `master.srt` ships.
- **SRT is the caption source of truth.** `edge-tts` sentence boundaries →
  deterministic cue grouping → per-segment SRT → offset into one `master.srt`.
- **TTS is the only nondeterministic step**, so its output (audio + boundaries +
  measured duration) is snapshotted; every downstream render is reproducible.

## Config = single source of truth (`production/<slug>/config/`)

| file | what | when it changes |
|---|---|---|
| `style.json` | all visual + timing knobs (fps, fonts, colors, gaps, caption/keypoint layout) | you tweak the look |
| `content.json` | AI-durable content: per-page kind, voiceover, keypoints | the slide changes |
| `timeline.json` | computed clip lengths, frame offsets, master-cue map | derived, re-computable |
| `render.lock.json` | full snapshot: above + tool versions + git commit + sha256 of every artifact | every render |

Style is separated from content so a restyle re-renders **without** re-running AI
or TTS.

## Pipeline stages

| stage | script | model / tool | output |
|---|---|---|---|
| S0 raster | `rasterize.py` | pdftoppm | `pages/page-NNN.png` |
| S1 classify | *subagent* | **haiku** | `ai/page-NNN.json` `{kind}` (+ future: suggests enrich model) |
| S2 enrich | *subagent* | **sonnet** (opus for dense slides) | `ai/…` voiceover + keypoints |
| — assemble | `assemble_content.py` | — | `content.json` segments |
| S3 keypoint card | `render_slide.py` | headless Chrome | `slides/kp-NNN.png` |
| S4 TTS | `tts.py` | edge-tts (`en-US-AndrewNeural`) | `audio/<id>.mp3` + boundaries |
| S5 SRT | `build_srt.py` | — | `audio/<id>.srt` |
| S6 timeline | `timeline.py` | — | `timeline.json` + `master.srt` |
| S7 captions | `render_caption.py` | headless Chrome | `captions/cap-*.png` |
| S8 compose | `compose.py` | ffmpeg overlay | `segments/<id>.mp4` |
| S9 concat | `concat.py` | ffmpeg concat | `final.mp4` |
| S10 snapshot | `snapshot.py` | — | `render.lock.json` |

### Model routing (triage)

`classify` (haiku) is cheap and also the natural place to **route difficulty**:
it returns `{kind, enrich_model, reason}` and the enrich step uses the suggested
model — `sonnet` by default (benchmarked on par with opus for this task),
`opus` reserved for especially dense slides.

## Robustness / "every artifact is linted before render"

- `volint.py` — voiceover linter: deterministic TTS-safe normalize (`::`, arrows,
  markdown, `%`, whitespace) + residual warnings. Run in `tts.py` pre-synthesis.
- `validate.py` — per-artifact validators (PNG dims, content schema, audio+
  boundaries, SRT monotonicity, segment duration == `clip_frames/fps`, final
  duration). Each stage validates its own output; also a standalone gate:
  `python scripts/validate.py --pdf <pdf> --stage all`.
- edge-tts: 3× retry + linear backoff, empty-stream guard, per-text cache.
- Every stage is idempotent and content-hash cached.

## Usage

```bash
uv venv && uv pip install edge-tts        # one-time

# S0 + AI stages: rasterize, then run classify/enrich subagents that drop
# ai/page-NNN.json, then assemble (see below).
python scripts/rasterize.py --pdf "pdf/<file>.pdf" --pages 1-5

# deterministic chain (assumes ai/*.json exist):
python scripts/render.py --pdf "pdf/<file>.pdf" --pages 1-5 --from assemble

# restyle only (reuses cached audio):
python scripts/render.py --pdf "pdf/<file>.pdf" --from slide      # e.g. keypoint card
python scripts/render.py --pdf "pdf/<file>.pdf" --from caption    # e.g. subtitle look

# run one stage:
python scripts/render.py --pdf "pdf/<file>.pdf" --only compose
```

The AI stages currently run as Claude Code subagents (haiku/sonnet reading the
page PNGs) that write `ai/page-NNN.json`. A headless `claude -p` adapter can drive
them unattended in CI (each call reloads project context, so it is slower/costlier
than in-session subagents).

## Local (LLM only) → Cloud (deterministic + release)

The work is split so the user's machine only runs the **LLM**, and GitHub Actions
runs **all the heavy rendering** and publishes the video.

```
one PDF = one worktree = one branch = one PR = one release
```

1. **New PDF → isolated worktree**
   ```bash
   scripts/new_pdf.sh "pdf/<file>.pdf"     # git worktree + branch pdf/<slug>
   cd ../slides-explainer-<slug>
   ```
2. **Local LLM stage** (in Claude Code): `/enrich "pdf/<file>.pdf"`
   Rasterizes for the models, runs haiku triage + sonnet/opus enrich subagents,
   writes `ai/*.json` and `config/content.json`. **No media is produced.**
3. **Commit + PR**
   ```bash
   git add production/<slug>/config production/<slug>/ai
   git commit -m "enrich <slug>" && git push -u origin pdf/<slug>
   gh pr create --fill        # review content.json (the text), then merge to main
   ```
4. **Cloud build + release** — merging to `main` triggers `.github/workflows/build-video.yml`:
   it pulls the PDF (Git LFS), rasterizes, runs TTS (cached across restyles),
   renders/composes/concats, validates, and publishes a **GH Release `video/<slug>`**
   with `final.mp4`, `master.srt`, `render.lock.json`.

Split of responsibility:

| | local | cloud (CI) |
|---|---|---|
| LLM (classify/enrich) | ✅ subscription, reads slide images | — |
| rasterize / TTS / render / compose / release | — | ✅ all deterministic, CPU-heavy |
| committed | PDF (LFS), `config/*.json`, `ai/*.json` | (regenerates media, publishes release) |

Tool paths are env-overridable (`FFMPEG_BIN`, `CHROME_BIN`, `PDFTOPPM_BIN`, …) so the
same scripts run on macOS locally and Ubuntu in CI.

## Output

- `production/<slug>/final.mp4` — burned-in captions, concatenated.
- `production/<slug>/master.srt` — global subtitle sidecar (aligned to `final.mp4`).
- `production/<slug>/config/render.lock.json` — rebuild manifest.
