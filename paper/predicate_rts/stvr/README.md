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
- `graphical_toc_text.txt`: title, authors, and a two-sentence
  summary below the journal's 80-word limit;
- `../../../artifacts/predicate_rts_reproducibility_bundle.tar.gz`: supporting
  reproducibility archive for review.

## Author metadata

Names, order, affiliations, correspondence, the available ORCID, funding,
competing interests, acknowledgements, CRediT roles, the generative-AI
statement, GitHub URL, and Zenodo DOI are centralized in `stvr_metadata.tex`. Both
authors have verified the CRediT allocation and approved the final manuscript.
The frozen dataset is archived at https://doi.org/10.5281/zenodo.22824889.
