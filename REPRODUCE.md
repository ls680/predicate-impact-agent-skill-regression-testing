# Reproducing PredicateImpact

The current paper can be audited at three levels. Released-record verification
is CPU-only. Hash auditing additionally needs the 7.5 MB pinned ScienceWorld
JAR; native replay also needs ALFWorld data and Java 17. No Docker and no GPU
are required for the current paper.

## 1. Verify the Released Records

The Git repository contains a compressed, hash-checked copy of every released
record. Extract it to a separate directory so the large expanded JSONL files
do not have to live in the normal Git checkout:

```bash
grep ' artifacts/predicate_rts_reproducibility_bundle.tar.gz$' \
  artifacts/PREDICATE_RTS_MANIFEST.sha256 | sha256sum -c -
mkdir -p ../predicate_rts_artifact
tar -xzf artifacts/predicate_rts_reproducibility_bundle.tar.gz \
  -C ../predicate_rts_artifact
cd ../predicate_rts_artifact/predicate_rts
python3 -m pip install 'setuptools>=68' wheel
python3 -m pip install -e '.[dev]' --no-build-isolation
bash research/validation/fetch_scienceworld_130.sh
bash artifacts/verify_predicate_rts.sh
```

Use Python 3.10--3.12. The verifier runs the stage tests in separate processes
because frozen revision directories intentionally contain same-named modules
and tests. It runs 43 offline tests, audits every R22--R24 input hash and roster,
regenerates the submission tables and figures, compiles both manuscripts, and
fails on undefined references, overfull boxes, or LaTeX errors.

## 2. Regenerate Tables and PDFs

```bash
MPLBACKEND=Agg python3 analysis/regression_submission.py
bash paper/predicate_rts/build.sh
```

Required paper tools are XeLaTeX, Latexmk, BibTeX, and Noto Serif/Sans CJK SC.
The primary generated outputs are:

```text
results/regression_testing/confirmation_summary.csv
results/regression_testing/task_budget_curves.csv
results/regression_testing/operator_summary.csv
results/regression_testing/coverage_noise_key_points.csv
results/figures/predicate_confirmation.{pdf,png}
results/figures/coverage_noise.{pdf,png}
paper/predicate_rts/en/main.pdf
paper/predicate_rts/zh/main.pdf
```

## 3. Native Environment Setup

On AutoDL, keep environments, caches, and benchmark data on the data disk:

```bash
cd /root/autodl-tmp/papers/01_skilllineage
export SKILLLINEAGE_DATA_ROOT=/root/autodl-tmp
bash environment/setup_autodl.sh "$(pwd)"
source environment/activate_autodl.sh
bash environment/setup_interactive.sh
bash research/validation/fetch_scienceworld_130.sh
```

The frozen native stack is ALFWorld 0.4.2, TextWorld 1.7.0, ScienceWorld
1.2.3 with simulator commit `e8216d6`, OpenJDK 17, and Python 3.10--3.12. The
pinned JAR must hash to
`e77b0fee7d68abe3ca5b12e57d86e2bfe7603f20c5200da0b0f085939faeb465`.

## 4. Clean-Room Native Replay

Run these commands in a fresh extracted artifact or a separate clean checkout.
Do not delete or overwrite the released run directories merely to demonstrate
reproduction. Each runner refuses to mix records when its frozen inputs differ.

Development and first independent confirmation:

```bash
export PYTHONPATH=src
python3 revisions/22_predicate_impact_testing/generate_specs.py
python3 revisions/22_predicate_impact_testing/run_mutations.py
python3 revisions/22_predicate_impact_testing/evaluate.py

python3 revisions/23_reserved_confirmation/freeze_roster.py
python3 revisions/23_reserved_confirmation/collect_oracles.py
python3 revisions/23_reserved_confirmation/generate_specs.py
python3 revisions/23_reserved_confirmation/run_mutations.py
python3 revisions/23_reserved_confirmation/evaluate.py
```

Disjoint three-operator confirmation:

```bash
python3 revisions/24_operator_transfer_confirmation/freeze_roster.py
python3 revisions/24_operator_transfer_confirmation/collect_oracles.py
python3 revisions/24_operator_transfer_confirmation/generate_specs.py
python3 revisions/24_operator_transfer_confirmation/run_mutations.py
python3 revisions/24_operator_transfer_confirmation/evaluate.py
```

The complete run materializes 164 independent-roster healthy references and
491 native mutation replays. The reported sum of per-episode runtimes is about
22.1 minutes with a 20-core container quota and 90 GiB memory limit on an AMD
EPYC 7642 host. Wall time depends on process startup and storage. The RTX 3090
is present but unused.

## 5. Audits and Sensitivity

The one-command verifier runs the following audits for each applicable run:

```bash
PYTHONPATH=src python3 revisions/23_reserved_confirmation/audit_confirmation.py \
  --run revisions/23_reserved_confirmation/results/native_mutations
PYTHONPATH=src python3 revisions/24_operator_transfer_confirmation/audit_confirmation.py \
  --run revisions/24_operator_transfer_confirmation/results/native_mutations
python3 revisions/26_coverage_noise_sensitivity/analyze.py
```

R25 additionally needs local clones of the three pinned public repositories.
Clone them into directories named `anthropics-skills`, `openai-skills`, and
`microsoftdocs-agent-skills`, check out the commits in
`revisions/25_real_skill_change_audit/repositories.json`, then run:

```bash
python3 revisions/25_real_skill_change_audit/audit_history.py \
  --repo-root /path/to/pinned-clones
```

That audit records paths and aggregate edit-shape counts, not third-party file
contents. It is external grounding, not a natural-fault effectiveness test.

## 6. Reproducibility Bundle

```bash
bash artifacts/build_predicate_rts_bundle.sh
sha256sum -c artifacts/PREDICATE_RTS_MANIFEST.sha256
```

The Git repository excludes the large, deterministically regenerated
`selection_analysis/evaluations.jsonl` files and the upstream simulator JAR.
The release bundle retains the full evaluation records; the pinned JAR is
retrieved and hash-checked by the provided script.
