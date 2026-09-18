# PredicateImpact Submission Readiness

Status: **scientific draft and reproducibility artifact complete; venue-specific
submission metadata remains open** (2026-09-06).

## Completed Scientific Items

- [x] Research question and closest-work boundary against FRAMES, SkillFuzz,
  SkillAudit, and SkillOps are stated.
- [x] Failed coarse-grained and recovery paths are retained and reported.
- [x] R22 development rules were frozen without reading mutation outcomes.
- [x] R23 uses a content-blind independent roster and frozen advancement gates.
- [x] R24 has zero task overlap with R23 and freezes its three-operator question
  before opening the second roster.
- [x] Skill-family random receives the changed-skill identity and is the strong
  primary baseline.
- [x] Exact predicate-coverage-set random isolates the actual source of gain.
- [x] All surviving mutations remain in all-mutation-score denominators.
- [x] Both environments and all three operators pass their frozen subgroup gates.
- [x] All 491 mutation replays have exact initial-state matches and zero
  technical errors.
- [x] Coverage corruption is clearly labeled post hoc.
- [x] The public history audit is labeled structural grounding, not a natural
  fault evaluation.
- [x] English and Chinese PDFs compile without undefined references, overfull
  boxes, or fatal errors and have been visually inspected.
- [x] Forty-three offline tests and all R22--R24 source/roster audits pass.

## Required Before Uploading to a Journal

- [ ] Select the target journal and article type, then apply its current
  template, length limit, data policy, and generative-AI disclosure policy.
- [ ] Supply real author names, order, affiliations, ORCIDs, and corresponding
  author details.
- [ ] Confirm funding, competing interests, acknowledgements, ethics status,
  and preprint/previous-submission statements.
- [ ] Create the public GitHub release, choose code/data licenses, and archive
  the release for a DOI.
- [ ] Replace anonymous placeholders only in the journal's required title-page
  file; preserve anonymization when double-blind review requires it.

## Residual Scientific Risk

The strongest missing evidence is a set of naturally faulty skill revisions
linked to independent failing tests. Public repositories currently ground edit
shapes only. This does not invalidate the mutation-benchmark result, but it
limits the paper's venue ceiling and must remain explicit. The manuscript is a
defensible software-testing/agent-maintenance submission; acceptance or a
particular SCI quartile cannot be guaranteed from experimental significance
alone.
