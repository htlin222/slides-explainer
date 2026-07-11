#!/usr/bin/env bash
# Create an isolated git worktree + branch for one PDF, ready for the local
# LLM stage (/enrich). Run from the repo root.
#
#   scripts/new_pdf.sh "pdf/1-1_ 簡聖軒醫師_WBC II.pdf"
set -euo pipefail

pdf="${1:?usage: new_pdf.sh <pdf>}"
[ -f "$pdf" ] || { echo "PDF not found: $pdf" >&2; exit 1; }

slug="$(.venv/bin/python scripts/slugof.py "$pdf")"
branch="pdf/$slug"
wt="../slides-explainer-$slug"

if git show-ref --quiet "refs/heads/$branch"; then
  echo "branch $branch already exists" >&2; exit 1
fi

git worktree add "$wt" -b "$branch"
cat <<EOF

worktree : $wt
branch   : $branch
slug     : $slug

next steps (in the worktree, inside Claude Code):
  cd "$wt"
  /enrich "$pdf"                    # local LLM: classify + enrich -> content.json
  git add production/$slug/config production/$slug/ai
  git commit -m "enrich $slug"
  git push -u origin "$branch"
  gh pr create --fill               # review content.json, then merge to main
                                    # -> cloud Action builds + releases video/$slug
EOF
