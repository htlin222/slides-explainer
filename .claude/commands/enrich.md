---
description: Local LLM stage — classify + enrich a PDF's slides into content.json (no media)
argument-hint: "<pdf-path> [--pages 1-5|all]"
---

You are running the **local LLM stage** of the slides-explainer pipeline for the
PDF given in `$ARGUMENTS`. This stage produces ONLY text (voiceover + key points);
it must NOT generate any audio/video. All heavy rendering happens later in cloud CI.

Parse `$ARGUMENTS`: first token is the PDF path; optional `--pages` (default `all`).

Work through these steps and do not stop until `content.json` is assembled:

## 0. Name the deck (haiku reads page 1 → semantic slug)
This slug becomes the production dir, the release tag, and the output filenames
`<slug>.mp4` / `<slug>.srt`, so make it human-readable.
1. `.venv/bin/python scripts/stage_page1.py --pdf "<pdf>"` → prints a staging PNG path.
2. Dispatch ONE **haiku** subagent (Agent tool, model: haiku):
   > Read the image at <staging-png>. This is the FIRST slide of a lecture deck.
   > Propose a short, human-readable slug (lowercase kebab-case, 2–5 words, no dates/
   > author names) that captures the deck's topic — e.g. "wbc-part2-lymphoma",
   > "coagulation-hemostasis", "rbc-disorders". Output ONLY: {"slug":"…","title":"…"}
3. `.venv/bin/python scripts/register_slug.py --pdf "<pdf>" --slug "<proposed-slug>"`
   → prints the FINAL slug (sanitized + de-duplicated). Use this slug from here on.

## 1. Rasterize (feed images to the models)
Run: `.venv/bin/python scripts/rasterize.py --pdf "<pdf>" --pages <pages>`
Note the printed `slug` and `production dir`. Page PNGs are at
`production/<slug>/pages/page-NNN.png`.

## 2. Triage every page with **haiku** subagents (Agent tool, model: haiku)
Dispatch pages in parallel batches (≤10 at a time). Each agent reads one page PNG
and returns ONLY this JSON (no prose, no fences):
```
{"index": N, "kind": "content"|"title", "enrich_model": "sonnet"|"opus", "reason": "…"}
```
Prompt each agent:
> Read the image at production/<slug>/pages/page-NNN.png . Classify this hematology
> board-review slide. kind="content" if it carries teachable material (table, figure,
> scoring system, dense factual list); kind="title" if it is a cover/section-divider/
> outline slide. Also pick enrich_model: "sonnet" normally, "opus" only if the slide
> is unusually dense (many numbers, subtle distinctions worth deeper reasoning).
> Output ONLY the JSON: {"index":N,"kind":…,"enrich_model":…,"reason":…}

## 3. Enrich each page (parallel batches)
- **content** pages → Agent with **model = the page's `enrich_model`** (sonnet, or opus).
- **title** pages → Agent with **model: haiku**.

Content prompt (audience = hematology fellows prepping for boards, want high-yield points):
> Read production/<slug>/pages/page-NNN.png . Produce a spoken English
> `content_voiceover` (~45–75 s) that teaches the slide like a sharp board-review tutor
> (orient, then walk the genuinely high-yield associations and the numbers examiners
> love; synthesize, don't read verbatim); `keypoints` = 3–5 SHORT high-yield lines for a
> "Key Points" card (display text — symbols like t(8;14), %, arrows OK here); and a
> `keypoint_voiceover` (~20–35 s) reading/reinforcing them.
> TTS RULES for the two *_voiceover fields (a text-to-speech engine speaks them):
> natural spoken English, NO markdown, NO bullet symbols, and NEVER write "::" or
> anything that would be read as "colon colon" — say "X-Y fusion" instead. Render
> translocations spoken-style, e.g. "t(8;14)" → "the t 8;14 translocation".
> Output ONLY: {"index":N,"kind":"content","content_voiceover":…,"keypoints":[…],"keypoint_voiceover":…}

Title prompt:
> Read production/<slug>/pages/page-NNN.png . Write a brief spoken English
> `title_voiceover` (~8–20 s) introducing this title/outline slide as a narrator would.
> Natural spoken English, no symbols/markdown.
> Output ONLY: {"index":N,"kind":"title","title_voiceover":…}

Save each agent's JSON verbatim to `production/<slug>/ai/page-NNN.json`.

## 4. Assemble + lint
- `.venv/bin/python scripts/assemble_content.py --pdf "<pdf>"`  → builds content.json segments
- `.venv/bin/python scripts/volint.py --pdf "<pdf>"`            → voiceover lint report

## 5. Summarize
Report per-page kinds, how many used sonnet vs opus, any volint warnings, and remind:
> Commit `production/<slug>/config/{content.json,style.json}` + `production/<slug>/ai/*.json`,
> push the `pdf/<slug>` branch, open a PR. Merging to main triggers the cloud build + release.

Do NOT run any of the rendering stages (slide/tts/srt/timeline/caption/compose/concat) —
those belong to cloud CI.
