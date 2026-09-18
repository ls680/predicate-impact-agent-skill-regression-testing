#!/usr/bin/env bash
set -euo pipefail

PAPER_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for language in en zh; do
  (
    cd "${PAPER_ROOT}/${language}"
    latexmk -xelatex -interaction=nonstopmode -halt-on-error main.tex
  )
done
