"""Simulate missing and spurious predicate-coverage edges on frozen results."""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import sys

REVISION = Path(__file__).resolve().parent
ROOT = REVISION.parents[1]
R22 = ROOT / 'revisions/22_predicate_impact_testing'
sys.path.insert(0, str(ROOT / 'revisions/07_executor_search'))
sys.path.insert(0, str(R22))
from run_preflight import digest, rows
from selection_methods import task_table


def uniform(seed, spec_id, task_id, label):
    payload = f'{seed}|{spec_id}|{task_id}|{label}'.encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], 'big') / 2**64


def corrupt_coverage(spec, family, false_negative_rate, false_positive_rate, seed):
    true = set(spec['support_task_ids'])
    observed = set()
    for task in family:
        task_id = task['task_id']
        if task_id in true:
            if uniform(seed, spec['spec_id'], task_id, 'fn') >= false_negative_rate:
                observed.add(task_id)
        elif uniform(seed, spec['spec_id'], task_id, 'fp') < false_positive_rate:
            observed.add(task_id)
    return observed


def random_probability(population, kills, budget):
    if not kills:
        return 0.0
    draw = min(population, budget)
    return 1.0 if population - kills < draw else (
        1.0 - math.comb(population - kills, draw) / math.comb(population, draw))


def quantile(values, probability):
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower, upper = math.floor(position), math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - position) + ordered[upper] * (position - lower)


def load_dataset(paths):
    artifact = json.loads(Path(paths['specs']).read_text())
    oracle = Path(paths['oracle'])
    outcome_dir = Path(paths['outcomes'])
    if json.loads((outcome_dir / 'completion.json').read_text()).get('status') != 'completed':
        raise ValueError('Noise analysis input is incomplete')
    records = rows(oracle / 'trajectories.jsonl')
    task_groups = {}
    for environment in sorted({row['environment'] for row in records}):
        task_groups[environment] = task_table(
            environment, [row for row in records if row['environment'] == environment])
    outcomes = rows(outcome_dir / 'outcomes.jsonl')
    outcome_map = {(row['spec_id'], row['task_id']): bool(row['killed']) for row in outcomes}
    killed, detectable = {}, []
    for spec in artifact['specs']:
        values = {task['task_id']: outcome_map.get((spec['spec_id'], task['task_id']), False)
                  for task in task_groups[spec['environment']]}
        killed[spec['spec_id']] = values
        if any(values.values()):
            detectable.append(spec)
    return detectable, task_groups, killed


def simulate(specs, task_groups, killed, fn_rate, fp_rate, seeds, budget):
    baseline_probabilities = []
    for spec in specs:
        family = [task for task in task_groups[spec['environment']]
                  if task['family'] == spec['family']]
        baseline_probabilities.append(random_probability(
            len(family), sum(killed[spec['spec_id']][task['task_id']] for task in family), budget))
    baseline = sum(baseline_probabilities) / len(specs)
    rates = []
    for seed in range(seeds):
        detected = 0
        for spec in specs:
            pool = task_groups[spec['environment']]
            family = [task for task in pool if task['family'] == spec['family']]
            observed = corrupt_coverage(spec, family, fn_rate, fp_rate, seed)
            ordered = sorted(family, key=lambda task: (
                task['task_id'] not in observed, task['healthy_steps'], task['task_id']))
            detected += any(killed[spec['spec_id']][task['task_id']]
                            for task in ordered[:budget])
        rates.append(detected / len(specs))
    mean = sum(rates) / len(rates)
    return {'detectable_specs': len(specs), 'false_negative_rate': fn_rate,
            'false_positive_rate': fp_rate, 'mean_detection_rate': mean,
            'simulation_q025': quantile(rates, .025), 'simulation_q975': quantile(rates, .975),
            'skill_family_random_expected_rate': baseline,
            'mean_absolute_lift': mean - baseline,
            'proportion_simulations_with_positive_lift':
                sum(rate > baseline for rate in rates) / len(rates)}


def main():
    config_path = REVISION / 'config.json'
    config = json.loads(config_path.read_text())
    results, inputs = [], [config_path, REVISION / 'PROTOCOL.md', REVISION / 'analyze.py',
                           R22 / 'selection_methods.py', R22 / 'atoms.py']
    for name, paths in config['datasets'].items():
        specs, task_groups, killed = load_dataset(paths)
        inputs.extend([Path(paths['specs']), Path(paths['oracle']) / 'completion.json',
                       Path(paths['oracle']) / 'trajectories.jsonl',
                       Path(paths['outcomes']) / 'completion.json',
                       Path(paths['outcomes']) / 'outcomes.jsonl'])
        strata = [('overall', specs)]
        strata.extend((environment, [spec for spec in specs if spec['environment'] == environment])
                      for environment in sorted(task_groups))
        for stratum, current in strata:
            if not current:
                continue
            for fn_rate in config['false_negative_rates']:
                for fp_rate in config['false_positive_rates']:
                    results.append({'dataset': name, 'stratum': stratum, **simulate(
                        current, task_groups, killed, fn_rate, fp_rate,
                        config['seeds'], config['task_budget'])})
    output = Path(config['output'])
    output.mkdir(parents=True, exist_ok=True)
    table = output / 'coverage_noise.csv'
    with table.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    completion = {
        'status': 'completed', 'scope': config['status'],
        'datasets': list(config['datasets']), 'grid_points_per_stratum':
            len(config['false_negative_rates']) * len(config['false_positive_rates']),
        'seeds_per_grid_point': config['seeds'], 'task_budget': config['task_budget'],
        'input_sha256': {str(path.resolve().relative_to(ROOT)): digest(path) for path in inputs},
        'table_sha256': digest(table),
        'inference_warning': 'Quantiles describe simulated coverage corruption, not population uncertainty.'}
    (output / 'completion.json').write_text(json.dumps(completion, indent=2) + '\n')
    print(json.dumps(completion))


if __name__ == '__main__':
    main()
