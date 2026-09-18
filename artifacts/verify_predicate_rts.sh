#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
cd "${PROJECT_ROOT}"
export PYTHONPATH="${PROJECT_ROOT}/src"

for suite in \
  tests \
  revisions/22_predicate_impact_testing/tests \
  revisions/23_reserved_confirmation/tests \
  revisions/24_operator_transfer_confirmation/tests \
  revisions/25_real_skill_change_audit/tests \
  revisions/26_coverage_noise_sensitivity/tests
do
  PYTHONPATH="${PROJECT_ROOT}/src:${PROJECT_ROOT}/$(dirname "${suite}")" \
    "${PYTHON_BIN}" -m pytest -q "${suite}"
done

for run in \
  revisions/22_predicate_impact_testing/results/native_mutations \
  revisions/22_predicate_impact_testing/results/selection_analysis
do
  "${PYTHON_BIN}" research/validation/audit_revision_sources.py --run "${run}"
done

for run in \
  revisions/23_reserved_confirmation/results/reserved_oracles \
  revisions/23_reserved_confirmation/results/native_mutations \
  revisions/23_reserved_confirmation/results/selection_analysis
do
  "${PYTHON_BIN}" revisions/23_reserved_confirmation/audit_confirmation.py --run "${run}"
done

for run in \
  revisions/24_operator_transfer_confirmation/results/reserved_oracles \
  revisions/24_operator_transfer_confirmation/results/native_mutations \
  revisions/24_operator_transfer_confirmation/results/selection_analysis
do
  "${PYTHON_BIN}" revisions/24_operator_transfer_confirmation/audit_confirmation.py --run "${run}"
done

"${PYTHON_BIN}" revisions/26_coverage_noise_sensitivity/analyze.py
MPLBACKEND=Agg "${PYTHON_BIN}" analysis/regression_submission.py
bash paper/predicate_rts/build.sh

for log in paper/predicate_rts/en/main.log paper/predicate_rts/zh/main.log
do
  if rg -n 'undefined|Overfull|Fatal|Error' "${log}"; then
    echo "Manuscript log check failed: ${log}" >&2
    exit 1
  fi
done

echo "PredicateImpact verification passed."
