#!/usr/bin/env bash
set -euo pipefail

STVR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${STVR_DIR}"

python3 make_graphical_toc.py
latexmk -xelatex -interaction=nonstopmode -halt-on-error stvr_research_paper.tex
latexmk -xelatex -interaction=nonstopmode -halt-on-error graphical_toc_entry.tex
