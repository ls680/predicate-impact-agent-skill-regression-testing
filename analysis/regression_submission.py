"""Build submission tables, figures, and LaTeX macros for predicate-level RTS."""
from __future__ import annotations

from collections import defaultdict
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'results/regression_testing'
FIGURES = ROOT / 'results/figures'

DATASETS = {
    'R23 deletion': ROOT / 'revisions/23_reserved_confirmation',
    'R24 multi-operator': ROOT / 'revisions/24_operator_transfer_confirmation',
}


def jsonl(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.strip()]


def write_csv(path, records):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=records[0].keys())
        writer.writeheader()
        writer.writerows(records)


def family_sizes(root):
    records = jsonl(root / 'results/reserved_oracles/trajectories.jsonl')
    sizes = defaultdict(int)
    for row in records:
        if row['success'] and not row['error']:
            sizes[(row['environment'], row['family'])] += 1
    return sizes


def dataset_summary(label, root):
    result = json.loads((root / 'results/selection_analysis/completion.json').read_text())
    artifact_name = 'predicate_specs.json' if 'R23' in label else 'operator_specs.json'
    artifact = json.loads((root / artifact_name).read_text())
    outcomes = jsonl(root / 'results/native_mutations/outcomes.jsonl')
    killed = {row['spec_id'] for row in outcomes if row['killed']}
    detectable = [spec for spec in artifact['specs'] if spec['spec_id'] in killed]
    overall = result['overall']
    sizes = family_sizes(root)
    full = sum(sizes[(spec['environment'], spec['family'])] for spec in detectable)
    selected = sum(min(result['primary_task_budget'], sizes[(spec['environment'], spec['family'])])
                   for spec in detectable)
    return {
        'dataset': label,
        'reserved_tasks': result['reserved_tasks_accessed'],
        'mutation_specs': len(artifact['specs']),
        'killable_specs': len(detectable),
        'native_replays': len(outcomes),
        'killed_task_mutation_pairs': sum(row['killed'] for row in outcomes),
        'predicate_detection_rate': overall['detection_rate'],
        'skill_family_random_expected_rate': overall['skill_family_random_expected_rate'],
        'absolute_lift': (overall.get('absolute_lift') if 'absolute_lift' in overall
                          else overall['absolute_lift_over_skill_family_random']),
        'conditional_randomization_p': overall['conditional_randomization_p_one_sided'],
        'coverage_random_expected_rate': overall.get(
            'predicate_coverage_random_expected_rate', overall['detection_rate']),
        'all_mutation_detection_score': overall['detected'] / len(artifact['specs']),
        'all_mutation_family_random_expected_score':
            overall['skill_family_random_expected_rate'] * len(detectable) / len(artifact['specs']),
        'test_execution_reduction_vs_full_family': 1 - selected / full,
    }


def budget_rows(label, root):
    artifact_name = 'predicate_specs.json' if 'R23' in label else 'operator_specs.json'
    artifact = json.loads((root / artifact_name).read_text())
    outcomes = jsonl(root / 'results/native_mutations/outcomes.jsonl')
    detectable = {row['spec_id'] for row in outcomes if row['killed']}
    evaluations = [row for row in jsonl(root / 'results/selection_analysis/evaluations.jsonl')
                   if row['spec_id'] in detectable]
    methods = ('predicate_impact', 'family_predicate_random', 'skill_family_random',
               'random', 'lexical_similarity', 'shortest_first', 'oracle_upper_bound')
    budgets = sorted(int(key) for key in evaluations[0]['task_budget_curve'])
    records = []
    for method in methods:
        group = [row for row in evaluations if row['method'] == method]
        for budget in budgets:
            values = [int(row['task_budget_curve'][str(budget)]['detected']) for row in group]
            records.append({'dataset': label, 'method': method, 'task_budget': budget,
                            'mean_detection_rate': sum(values) / len(values),
                            'evaluation_rows': len(values),
                            'killable_specs': len(detectable),
                            'total_specs': len(artifact['specs'])})
    return records


def operator_rows():
    result = json.loads((DATASETS['R24 multi-operator'] /
                         'results/selection_analysis/completion.json').read_text())
    return [{'operator': operator, **values} for operator, values in result['by_operator'].items()]


def noise_rows():
    source = ROOT / 'revisions/26_coverage_noise_sensitivity/results/coverage_noise.csv'
    with source.open() as stream:
        records = list(csv.DictReader(stream))
    key = {(0.0, 0.0), (0.2, 0.1), (0.5, 0.2)}
    return [row for row in records if row['stratum'] == 'overall' and
            (float(row['false_negative_rate']), float(row['false_positive_rate'])) in key]


def draw_main(summaries):
    labels = ['Deletion\nconfirmation', 'Three-operator\ntransfer']
    series = [
        ('Predicate coverage', [row['predicate_detection_rate'] for row in summaries], '#087e8b'),
        ('Skill-family random', [row['skill_family_random_expected_rate'] for row in summaries], '#c7522a'),
        ('Coverage-set random', [row['coverage_random_expected_rate'] for row in summaries], '#6b7280'),
    ]
    fig, axis = plt.subplots(figsize=(6.8, 3.6))
    x = range(len(labels))
    width = .24
    for index, (name, values, color) in enumerate(series):
        positions = [value + (index - 1) * width for value in x]
        bars = axis.bar(positions, values, width=width, label=name, color=color)
        for position, value in zip(positions, values):
            inside = value >= .9
            axis.text(position, value - .035 if inside else value + .015,
                      f'{value:.1%}', ha='center', va='center', fontsize=8,
                      color='white' if inside else 'black')
    axis.set_xticks(list(x), labels)
    axis.set_ylim(0, 1.10)
    axis.set_ylabel('Detection rate among killable changes')
    axis.legend(frameon=False, ncol=3, loc='upper center',
                bbox_to_anchor=(.5, 1.16))
    axis.spines[['top', 'right']].set_visible(False)
    fig.tight_layout()
    for suffix in ('png', 'pdf'):
        fig.savefig(FIGURES / f'predicate_confirmation.{suffix}', dpi=220, bbox_inches='tight')
    plt.close(fig)


def draw_noise():
    path = ROOT / 'revisions/26_coverage_noise_sensitivity/results/coverage_noise.csv'
    with path.open() as stream:
        rows = [row for row in csv.DictReader(stream) if row['stratum'] == 'overall']
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2), sharey=True)
    colors = ['#087e8b', '#56a3a6', '#d9a441', '#c7522a']
    datasets = [('r23_deletion_confirmation', 'Deletion confirmation'),
                ('r24_operator_transfer', 'Three-operator transfer')]
    for axis, (dataset, title) in zip(axes, datasets):
        group = [row for row in rows if row['dataset'] == dataset]
        for color, fp in zip(colors, (0.0, 0.05, 0.1, 0.2)):
            values = sorted((float(row['false_negative_rate']), float(row['mean_detection_rate']))
                            for row in group if float(row['false_positive_rate']) == fp)
            axis.plot([x for x, _ in values], [y for _, y in values], marker='o',
                      color=color, label=f'FP={fp:.0%}')
        baseline = float(group[0]['skill_family_random_expected_rate'])
        axis.axhline(baseline, color='#333333', linestyle='--', linewidth=1,
                     label='Skill-family random')
        axis.set_title(title, fontsize=10)
        axis.set_xlabel('Missing true coverage edges')
        axis.set_ylim(.45, 1.03)
        axis.spines[['top', 'right']].set_visible(False)
    axes[0].set_ylabel('Mean detection rate')
    axes[1].legend(frameon=False, fontsize=7, ncol=2, loc='lower left')
    fig.tight_layout()
    for suffix in ('png', 'pdf'):
        fig.savefig(FIGURES / f'coverage_noise.{suffix}', dpi=220, bbox_inches='tight')
    plt.close(fig)


def macros(summaries, operators, edits):
    r23, r24 = summaries
    mapping = {
        'RXXIIIReservedTasks': r23['reserved_tasks'],
        'RXXIIISpecs': r23['mutation_specs'],
        'RXXIIIDetectable': r23['killable_specs'],
        'RXXIIILift': f"{100 * r23['absolute_lift']:.2f}\\%",
        'RXXIIIP': f"{r23['conditional_randomization_p']:.2e}",
        'RXXIVReservedTasks': r24['reserved_tasks'],
        'RXXIVSpecs': r24['mutation_specs'],
        'RXXIVDetectable': r24['killable_specs'],
        'RXXIVReplays': r24['native_replays'],
        'RXXIVLift': f"{100 * r24['absolute_lift']:.2f}\\%",
        'RXXIVP': f"{r24['conditional_randomization_p']:.2e}",
        'PublicRepoCount': edits['repositories'],
        'PublicMainlineCommits': sum(edits['mainline_commits_traversed'].values()),
        'PublicModifiedSkills': edits['modified_skill_file_edits'],
    }
    lines = [f'\\newcommand{{\\{key}}}{{{value}}}' for key, value in mapping.items()]
    (ROOT / 'paper/regression_results_macros.tex').write_text('\n'.join(lines) + '\n')


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    summaries = [dataset_summary(label, root) for label, root in DATASETS.items()]
    budgets = [row for label, root in DATASETS.items() for row in budget_rows(label, root)]
    operators = operator_rows()
    noise = noise_rows()
    edits = json.loads((ROOT / 'revisions/25_real_skill_change_audit/results/completion.json').read_text())
    write_csv(OUTPUT / 'confirmation_summary.csv', summaries)
    write_csv(OUTPUT / 'task_budget_curves.csv', budgets)
    write_csv(OUTPUT / 'operator_summary.csv', operators)
    write_csv(OUTPUT / 'coverage_noise_key_points.csv', noise)
    (OUTPUT / 'public_change_audit.json').write_text(json.dumps(edits, indent=2) + '\n')
    draw_main(summaries)
    draw_noise()
    macros(summaries, operators, edits)
    print(json.dumps({'summaries': summaries, 'operator_rows': len(operators),
                      'budget_rows': len(budgets), 'noise_rows': len(noise)}))


if __name__ == '__main__':
    main()
