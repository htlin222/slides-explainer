# slides-explainer — convenience targets
# Usage: make render PDF="pdf/1-1_ 簡聖軒醫師_WBC II.pdf" PAGES=1-5

PY := .venv/bin/python
PDF ?=
PAGES ?= 1-5
FROM ?= assemble

.PHONY: venv raster render restyle recaption validate clean-final

venv:
	uv venv && uv pip install edge-tts

raster:
	$(PY) scripts/rasterize.py --pdf "$(PDF)" --pages "$(PAGES)"

# deterministic chain (assumes ai/*.json produced by classify/enrich subagents)
render:
	$(PY) scripts/render.py --pdf "$(PDF)" --pages "$(PAGES)" --from "$(FROM)"

# restyle without re-running AI/TTS
restyle:
	$(PY) scripts/render.py --pdf "$(PDF)" --from slide

recaption:
	$(PY) scripts/render.py --pdf "$(PDF)" --from caption

validate:
	$(PY) scripts/validate.py --pdf "$(PDF)" --stage all

clean-final:
	rm -f "$$($(PY) -c "import sys;sys.path.insert(0,'scripts');import common;from pathlib import Path;print(common.Prod(Path('$(PDF)')).final_mp4)")"
