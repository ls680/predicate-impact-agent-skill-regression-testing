# PredicateImpact: Regression Test Selection for Agent Skills

Current paper (2026-09-06): **From Skill-Level to Predicate-Level: Budgeted
Regression Test Selection for Evolving LLM Agent Skills**.

This is the first positive paper produced from the Agent Skill lifecycle
research matrix. It studies a practical maintenance problem: after a small
conditional part of a skill changes, which previously passing interactive
tests should run first when replay is expensive?

PredicateImpact maps successful traces to skill-internal action predicates and
prioritizes tests that covered the changed predicate. At a three-test budget:

| Confirmation | Killable changes | PredicateImpact | Skill-family random | Absolute lift | One-sided conditional p |
|---|---:|---:|---:|---:|---:|
| R23 deletion, untouched roster | 64 | 1.0000 | 0.5561 | 0.4439 | 1.65e-19 |
| R24 three operators, disjoint roster | 115 | 1.0000 | 0.5567 | 0.4433 | 8.29e-35 |

The effect appears separately in ALFWorld and ScienceWorld and for deletion,
same-kind argument substitution, and adjacent-order swap. All 491 native
mutation replays match their healthy initial states and have no technical
errors. A stronger ablation that randomizes only within the exact predicate
coverage set also scores 1.0000, so the supported contribution is the finer
coverage granularity, not the proposed within-set tie-breaker.

## Repository Contents

- English manuscript source/PDF: `paper/predicate_rts/en/`
- STVR submission source/PDF and graphical abstract: `paper/predicate_rts/stvr/`
- Chinese manuscript source/PDF: `paper/predicate_rts/zh/`
- Frozen protocols and raw records: `revisions/22_predicate_impact_testing/`
  through `revisions/26_coverage_noise_sensitivity/`
- Derived tables and figures: `results/regression_testing/` and
  `results/figures/`
- Complete frozen artifact: `artifacts/predicate_rts_reproducibility_bundle.tar.gz`
- Claim boundary: `research/PREDICATE_RTS_CLAIM_EVIDENCE.md`
- Submission status: `research/PREDICATE_RTS_SUBMISSION_READINESS.md`
- Audited machine/software snapshot: `research/PREDICATE_RTS_RUN_ENVIRONMENT.md`

Large expanded JSONL records are intentionally excluded from the Git tree to
keep normal clones small. They remain inside the tracked, hash-checked
reproducibility bundle. The bundle contains the exact source and records used
for the paper and can be extracted into an independent directory for audit.

## Repository Layout

```text
predicate-impact-agent-skill-regression-testing/
|-- analysis/                         Submission analysis and figures
|-- artifacts/                        Complete bundle, builder, and checksums
|-- environment/                      No-Docker AutoDL setup
|-- paper/predicate_rts/en/            Current English manuscript and PDF
|-- paper/predicate_rts/stvr/          Journal-specific English submission
|-- paper/predicate_rts/zh/            Current Chinese manuscript and PDF
|-- research/                         Protocol, evidence, and claim boundaries
|-- revisions/22_predicate_impact_testing/
|-- revisions/23_reserved_confirmation/
|-- revisions/24_operator_transfer_confirmation/
|-- revisions/25_real_skill_change_audit/
|-- revisions/26_coverage_noise_sensitivity/
|-- results/                          Generated tables and figures
|-- submission/                       Journal-facing editable templates
|-- src/                              Shared implementation
`-- tests/                            Network-free tests
```

## Quick Verification

First verify the frozen archive:

```bash
grep ' artifacts/predicate_rts_reproducibility_bundle.tar.gz$' \
  artifacts/PREDICATE_RTS_MANIFEST.sha256 | sha256sum -c -
```

For the complete record audit, extract the bundle into a separate directory.
This avoids overwriting the lightweight checkout with the expanded JSONL
records:

```bash
mkdir -p ../predicate_rts_artifact
tar -xzf artifacts/predicate_rts_reproducibility_bundle.tar.gz \
  -C ../predicate_rts_artifact
cd ../predicate_rts_artifact/predicate_rts
python3 -m pip install 'setuptools>=68' wheel
python3 -m pip install -e '.[dev]' --no-build-isolation
bash research/validation/fetch_scienceworld_130.sh
bash artifacts/verify_predicate_rts.sh
```

The core confirmation does not call an LLM and does not use the installed RTX
3090. A CPU machine with Java 17, 16 GB RAM, and the upstream ALFWorld data is
sufficient; the reported AutoDL container had a 20-core quota and 90 GiB memory
limit on an AMD EPYC 7642 host. See
`REPRODUCE.md` for dependency, environment, and clean-room rerun commands.

## Third-Party Assets

ALFWorld, TextWorld, ScienceWorld, model weights, and cloned public skill
repositories are not redistributed. Their versions or commits are pinned in
the protocols, and the ScienceWorld simulator JAR is fetched separately and
hash-checked. Users must comply with each upstream project's license.

## Citation

Citation metadata will be added when the author list is confirmed.

## License

Original code and repository materials are released under the Apache License
2.0; see `LICENSE`. Third-party benchmarks, model weights, simulator assets,
and audited repositories remain subject to their respective upstream licenses
and are not relicensed or redistributed here.

## Evidence Boundary

The result is reliable for the two frozen mutation benchmarks and their three
edit operators. It does not establish automatic localization in arbitrary
free-form `SKILL.md` files or population-level benefit on naturally faulty
production commits. The public-repository audit only establishes that
deletion-, replacement-, and relocation-shaped edits occur in real skill
histories. These limits are stated in the abstract, discussion, threats to
validity, and conclusion.
