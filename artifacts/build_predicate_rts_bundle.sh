#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_DIR="${PROJECT_ROOT}/artifacts"
BUNDLE="${OUTPUT_DIR}/predicate_rts_reproducibility_bundle.tar.gz"
MANIFEST="${OUTPUT_DIR}/PREDICATE_RTS_MANIFEST.sha256"
STAGING_ROOT="$(mktemp -d /tmp/predicate-rts-bundle.XXXXXX)"
trap 'rm -rf -- "${STAGING_ROOT}"' EXIT

DESTINATION="${STAGING_ROOT}/predicate_rts"
mkdir -p \
  "${DESTINATION}/analysis" \
  "${DESTINATION}/paper" \
  "${DESTINATION}/research/validation" \
  "${DESTINATION}/results" \
  "${DESTINATION}/revisions" \
  "${DESTINATION}/artifacts" \
  "${DESTINATION}/configs" \
  "${DESTINATION}/scripts"

rsync -a \
  "${PROJECT_ROOT}/README.md" \
  "${PROJECT_ROOT}/REPRODUCE.md" \
  "${PROJECT_ROOT}/pyproject.toml" \
  "${PROJECT_ROOT}/.gitignore" \
  "${DESTINATION}/"
rsync -a "${PROJECT_ROOT}/analysis/regression_submission.py" "${DESTINATION}/analysis/"
rsync -a "${PROJECT_ROOT}/environment/" "${DESTINATION}/environment/"
rsync -a --exclude='__pycache__/' --exclude='*.pyc' \
  "${PROJECT_ROOT}/src/" "${DESTINATION}/src/"
rsync -a --exclude='__pycache__/' --exclude='*.pyc' \
  "${PROJECT_ROOT}/tests/" "${DESTINATION}/tests/"
rsync -a --exclude='__pycache__/' --exclude='*.pyc' \
  "${PROJECT_ROOT}/configs/" "${DESTINATION}/configs/"
rsync -a --exclude='__pycache__/' --exclude='*.pyc' \
  "${PROJECT_ROOT}/scripts/" "${DESTINATION}/scripts/"
rsync -a "${PROJECT_ROOT}/submission/" "${DESTINATION}/submission/"
rsync -a "${PROJECT_ROOT}/artifacts/verify_predicate_rts.sh" "${DESTINATION}/artifacts/"

rsync -a \
  --exclude='stvr/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.aux' \
  --exclude='*.bbl' \
  --exclude='*.blg' \
  --exclude='*.fdb_latexmk' \
  --exclude='*.fls' \
  --exclude='*.log' \
  --exclude='*.out' \
  --exclude='*.xdv' \
  "${PROJECT_ROOT}/paper/predicate_rts/" "${DESTINATION}/paper/predicate_rts/"
rsync -a \
  "${PROJECT_ROOT}/paper/references.bib" \
  "${PROJECT_ROOT}/paper/regression_results_macros.tex" \
  "${DESTINATION}/paper/"
rsync -a "${PROJECT_ROOT}/results/regression_testing/" \
  "${DESTINATION}/results/regression_testing/"
mkdir -p "${DESTINATION}/results/figures"
rsync -a \
  "${PROJECT_ROOT}/results/figures/predicate_confirmation.pdf" \
  "${PROJECT_ROOT}/results/figures/predicate_confirmation.png" \
  "${PROJECT_ROOT}/results/figures/coverage_noise.pdf" \
  "${PROJECT_ROOT}/results/figures/coverage_noise.png" \
  "${DESTINATION}/results/figures/"

for revision in \
  22_predicate_impact_testing \
  23_reserved_confirmation \
  24_operator_transfer_confirmation \
  25_real_skill_change_audit \
  26_coverage_noise_sensitivity
do
  rsync -a --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.log' \
    "${PROJECT_ROOT}/revisions/${revision}/" \
    "${DESTINATION}/revisions/${revision}/"
done

mkdir -p \
  "${DESTINATION}/revisions/02_evidence_gated_repair" \
  "${DESTINATION}/revisions/04_state_matched_execution" \
  "${DESTINATION}/revisions/07_executor_search" \
  "${DESTINATION}/revisions/19_shadow_release_testing/results/exposed_science_oracles" \
  "${DESTINATION}/revisions/20_crossenv_shadow_testing/results/exposed_alf_oracles"
rsync -a "${PROJECT_ROOT}/revisions/02_evidence_gated_repair/repair.py" \
  "${DESTINATION}/revisions/02_evidence_gated_repair/"
rsync -a "${PROJECT_ROOT}/revisions/04_state_matched_execution/state_check.py" \
  "${DESTINATION}/revisions/04_state_matched_execution/"
rsync -a \
  "${PROJECT_ROOT}/revisions/07_executor_search/run_preflight.py" \
  "${PROJECT_ROOT}/revisions/07_executor_search/controllers.py" \
  "${DESTINATION}/revisions/07_executor_search/"
rsync -a "${PROJECT_ROOT}/revisions/19_shadow_release_testing/results/exposed_science_oracles/" \
  "${DESTINATION}/revisions/19_shadow_release_testing/results/exposed_science_oracles/"
rsync -a "${PROJECT_ROOT}/revisions/20_crossenv_shadow_testing/results/exposed_alf_oracles/" \
  "${DESTINATION}/revisions/20_crossenv_shadow_testing/results/exposed_alf_oracles/"

rsync -a \
  "${PROJECT_ROOT}/research/PREDICATE_RTS_CLAIM_EVIDENCE.md" \
  "${PROJECT_ROOT}/research/PREDICATE_RTS_RUN_ENVIRONMENT.md" \
  "${PROJECT_ROOT}/research/PREDICATE_RTS_SUBMISSION_READINESS.md" \
  "${DESTINATION}/research/"
rsync -a \
  "${PROJECT_ROOT}/research/validation/audit_revision_sources.py" \
  "${PROJECT_ROOT}/research/validation/exposure_snapshot_20260905.json" \
  "${PROJECT_ROOT}/research/validation/fetch_scienceworld_130.sh" \
  "${PROJECT_ROOT}/research/validation/PIVOT_RECORD_05.md" \
  "${PROJECT_ROOT}/research/validation/R19_LITERATURE_POSITIONING.md" \
  "${DESTINATION}/research/validation/"

tar --sort=name --mtime='UTC 2026-09-06' --owner=0 --group=0 --numeric-owner \
  -C "${STAGING_ROOT}" -cf - predicate_rts | gzip -n > "${BUNDLE}"

(
  cd "${PROJECT_ROOT}"
  find \
    README.md REPRODUCE.md pyproject.toml \
    analysis/regression_submission.py configs scripts \
    artifacts/verify_predicate_rts.sh \
    paper/predicate_rts paper/references.bib paper/regression_results_macros.tex \
    results/regression_testing \
    results/figures/predicate_confirmation.pdf \
    results/figures/predicate_confirmation.png \
    results/figures/coverage_noise.pdf \
    results/figures/coverage_noise.png \
    revisions/22_predicate_impact_testing \
    revisions/23_reserved_confirmation \
    revisions/24_operator_transfer_confirmation \
    revisions/25_real_skill_change_audit \
    revisions/26_coverage_noise_sensitivity \
    research/PREDICATE_RTS_CLAIM_EVIDENCE.md \
    research/PREDICATE_RTS_RUN_ENVIRONMENT.md \
    research/PREDICATE_RTS_SUBMISSION_READINESS.md \
    -type f \
    ! -path '*/__pycache__/*' \
    ! -name '*.pyc' \
    ! -name '*.aux' \
    ! -name '*.bbl' \
    ! -name '*.blg' \
    ! -name '*.fdb_latexmk' \
    ! -name '*.fls' \
    ! -name '*.log' \
    ! -name '*.out' \
    ! -name '*.xdv' \
    -print0 | sort -z | xargs -0 sha256sum
  sha256sum artifacts/predicate_rts_reproducibility_bundle.tar.gz
) > "${MANIFEST}"

echo "${BUNDLE}"
echo "${MANIFEST}"
