"""Evaluate frozen predicate-impact selection against skill-family random testing."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys

REVISION = Path(__file__).resolve().parent
ROOT = REVISION.parents[1]
sys.path.insert(0, str(ROOT / 'revisions/07_executor_search'))
from run_preflight import digest, rows
from selection_methods import select_order, task_table
from skilllineage.provenance import source_hash

RANDOMIZED = {'family_predicate_random', 'skill_family_random', 'random', 'family_stratified'}


def random_probability(population, kills, budget):
    if not kills:
        return 0.0
    draw = min(population, budget)
    return 1.0 if population - kills < draw else (
        1.0 - math.comb(population - kills, draw) / math.comb(population, draw))


def upper_tail(probabilities, observed):
    distribution = [1.0] + [0.0] * len(probabilities)
    for probability in probabilities:
        updated = [0.0] * len(distribution)
        for count, mass in enumerate(distribution):
            updated[count] += mass * (1 - probability)
            if count + 1 < len(updated):
                updated[count + 1] += mass * probability
        distribution = updated
    return sum(distribution[observed:])


def curves(order, killed, task_budgets, step_budgets):
    task_curve = {str(b): {'detected': any(killed[t['task_id']] for t in order[:b]),
                           'estimated_steps': sum(t['healthy_steps'] for t in order[:b])}
                  for b in task_budgets}
    step_curve = {}
    for budget in step_budgets:
        selected, cost = [], 0
        for task in order:
            if cost + task['healthy_steps'] > budget:
                break
            selected.append(task)
            cost += task['healthy_steps']
        step_curve[str(budget)] = {'detected': any(killed[t['task_id']] for t in selected),
                                   'tasks': len(selected), 'estimated_steps': cost}
    first = next((i for i, task in enumerate(order) if killed[task['task_id']]), None)
    return task_curve, step_curve, first


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=REVISION / 'config.json')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    artifact = json.loads(Path(config['spec_output']).read_text())
    mutation_dir = Path(config['mutation_output'])
    if (not (mutation_dir / 'completion.json').exists() or
            json.loads((mutation_dir / 'completion.json').read_text()).get('status') != 'completed'):
        raise ValueError('R22 mutation materialization is incomplete')
    records = {environment: rows(path + '/trajectories.jsonl')
               for environment, path in config['healthy_runs'].items()}
    tasks = {environment: task_table(environment, group) for environment, group in records.items()}
    outcomes = rows(mutation_dir / 'outcomes.jsonl')
    outcome_map = {(row['spec_id'], row['task_id']): row for row in outcomes}
    expected = {(spec['spec_id'], task_id) for spec in artifact['specs']
                for task_id in spec['support_task_ids']}
    if set(outcome_map) != expected or len(outcome_map) != len(outcomes):
        raise ValueError('R22 mutation outcomes do not match frozen specifications')
    evaluations, killed_by_spec = [], {}
    for spec in artifact['specs']:
        pool = tasks[spec['environment']]
        killed = {task['task_id']: bool(outcome_map.get((spec['spec_id'], task['task_id']), {}).get('killed'))
                  for task in pool}
        killed_by_spec[spec['spec_id']] = killed
        for method in config['selection_methods']:
            seeds = range(config['random_seeds']) if method in RANDOMIZED else [0]
            for seed in seeds:
                order = select_order(method, pool, spec, seed=seed, killed=killed)
                task_curve, step_curve, first = curves(
                    order, killed, config['task_budgets'], config['estimated_step_budgets'])
                evaluation = {
                    'spec_id': spec['spec_id'], 'environment': spec['environment'],
                    'family': spec['family'], 'predicate_kind': spec['predicate_kind'],
                    'predicate_value': spec['predicate_value'], 'support_count': spec['support_count'],
                    'method': method, 'seed': seed if method in RANDOMIZED else None,
                    'task_budget_curve': task_curve, 'estimated_step_budget_curve': step_curve,
                    'first_kill_rank': first + 1 if first is not None else None,
                    'first_kill_estimated_steps': (sum(t['healthy_steps'] for t in order[:first + 1])
                                                   if first is not None else None),
                }
                if method not in RANDOMIZED:
                    evaluation['order'] = [task['task_id'] for task in order]
                evaluations.append(evaluation)
    output = Path(config['selection_output'])
    output.mkdir(parents=True, exist_ok=True)
    inputs = [args.config, REVISION / 'predicate_specs.json', REVISION / 'atoms.py',
              REVISION / 'selection_methods.py', REVISION / 'evaluate.py', REVISION / 'PROTOCOL.md',
              mutation_dir / 'run_spec.json', mutation_dir / 'completion.json',
              mutation_dir / 'outcomes.jsonl', Path(config['exposure_snapshot'])]
    for path in config['healthy_runs'].values():
        inputs.extend([Path(path) / name for name in
                       ('run_spec.json', 'completion.json', 'trajectories.jsonl')])
    spec_record = {
        'status': 'predicate_impact_selection_development_analysis', 'config': config,
        'original_source_sha256': source_hash(),
        'revision_inputs': {str(p.resolve().relative_to(ROOT)): digest(p) for p in inputs},
        'tasks': [{'environment': environment, 'task_id': task['task_id']}
                  for environment, group in tasks.items() for task in group],
    }
    spec_path = output / 'run_spec.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec_record:
        raise ValueError('Frozen R22 selection inputs changed')
    spec_path.write_text(json.dumps(spec_record, ensure_ascii=False, indent=2) + '\n')
    evaluation_path = output / 'evaluations.jsonl'
    with evaluation_path.open('w') as stream:
        for row in evaluations:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    detectable = [spec for spec in artifact['specs'] if any(killed_by_spec[spec['spec_id']].values())]
    budget = config['primary_task_budget']
    method_rows = {row['spec_id']: row for row in evaluations
                   if row['method'] == 'predicate_impact' and row['seed'] is None}
    detected = sum(method_rows[spec['spec_id']]['task_budget_curve'][str(budget)]['detected']
                   for spec in detectable)
    probabilities = []
    for spec in detectable:
        family_size = sum(task['family'] == spec['family'] for task in tasks[spec['environment']])
        kills = sum(killed_by_spec[spec['spec_id']].values())
        probabilities.append(random_probability(family_size, kills, budget))
    method_rate = detected / len(detectable) if detectable else 0.0
    baseline_rate = sum(probabilities) / len(probabilities) if probabilities else 0.0
    p_value = upper_tail(probabilities, detected) if probabilities else 1.0
    multi = [spec for spec in detectable if spec['support_count'] > 1]
    environments = {spec['environment'] for spec in detectable}
    families = {(spec['environment'], spec['family']) for spec in detectable}
    gate = config['development_gate']
    checks = {
        'minimum_detectable_predicate_specs': len(detectable) >= gate['minimum_detectable_predicate_specs'],
        'minimum_multitask_detectable_specs': len(multi) >= gate['minimum_multitask_detectable_specs'],
        'minimum_environments': len(environments) >= gate['minimum_environments'],
        'minimum_skill_families': len(families) >= gate['minimum_skill_families'],
        'minimum_predicate_impact_detection_rate': method_rate >= gate['minimum_predicate_impact_detection_rate'],
        'minimum_absolute_lift_over_skill_family_random': method_rate - baseline_rate >= gate['minimum_absolute_lift_over_skill_family_random'],
        'maximum_conditional_randomization_p': p_value <= gate['maximum_conditional_randomization_p'],
    }
    result = {
        'status': 'completed', 'scope': 'exposed_cross_environment_development_only',
        'predicate_specs': len(artifact['specs']), 'detectable_predicate_specs': len(detectable),
        'multitask_detectable_specs': len(multi), 'detectable_environments': sorted(environments),
        'detectable_skill_families': len(families), 'primary_task_budget': budget,
        'predicate_impact_detected': detected, 'predicate_impact_detection_rate': method_rate,
        'skill_family_random_expected_detection_rate': baseline_rate,
        'absolute_lift_over_skill_family_random': method_rate - baseline_rate,
        'conditional_randomization_p_one_sided': p_value,
        'p_value_scope_warning': 'Conditional development-benchmark randomization, not population inference.',
        'development_gate_checks': checks, 'development_gate_passed': all(checks.values()),
        'advance_to_reserved_confirmation': all(checks.values()),
        'detectable_by_environment': dict(Counter(spec['environment'] for spec in detectable)),
        'reserved_tasks_accessed': 0, 'evaluations_sha256': digest(evaluation_path),
    }
    (output / 'completion.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
