# STVR submission version

This directory contains the English-only, journal-specific submission version
for *Software Testing, Verification and Reliability* (STVR). The scientific
source at `../en/main.tex` is not modified. `stvr_research_paper.tex` imports
that source and replaces only the abstract, title page, typography, and
post-reference declaration material required for this submission.

## Build

```bash
bash build_stvr.sh
```

Expected submission-facing outputs:

- `stvr_research_paper.pdf`: main Research Paper with embedded figures/tables;
- `graphical_toc_entry.pdf`: separate graphical table-of-contents entry;
- `graphical_toc_image.pdf` and `.png`: 50 mm x 60 mm graphical image;
- `graphical_toc_text.txt`: title, author placeholder, and a two-sentence
  summary below the journal's 80-word limit;
- `../../../artifacts/predicate_rts_reproducibility_bundle.tar.gz`: supporting
  reproducibility archive for review.

## Fields still requiring author confirmation

Edit only `stvr_metadata.tex` after the authors provide names, order,
affiliations, correspondence, ORCIDs, funding, competing interests,
acknowledgements, CRediT roles, the generative-AI statement, GitHub release URL,
and archival DOI. Do not replace placeholders with invented information.

