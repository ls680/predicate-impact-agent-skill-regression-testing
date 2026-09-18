"""Evaluate R24 operator transfer with frozen task- and step-budget endpoints."""
from __future__ import annotations

import argparse
from collections import defaultdict
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
from selection_methods import select_order, task_table
from skilllineage.provenance import source_hash

RANDOMIZED = {'family_predicate_random', 'skill_family_random', 'random', 'family_stratified'}


def random_probability(population, kills, budget):
    if not kills or not population:
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
    task_curve = {str(budget): {
        'detected': any(killed[task['task_id']] for task in order[:budget]),
        'estimated_steps': sum(task['healthy_steps'] for task in order[:budget])}
        for budget in task_budgets}
    step_curve = {}
    for budget in step_budgets:
        selected, cost = [], 0
        for task in order:
            if cost + task['healthy_steps'] > budget:
                break
            selected.append(task)
            cost += task['healthy_steps']
        step_curve[str(budget)] = {
            'detected': any(killed[task['task_id']] for task in selected),
            'tasks': len(selected), 'estimated_steps': cost}
    first = next((index for index, task in enumerate(order) if killed[task['task_id']]), None)
    return task_curve, step_curve, first


def metric(specs, tasks, killed_by_spec, method_rows, budget):
    detected = sum(method_rows[spec['spec_id']]['task_budget_curve'][str(budget)]['detected']
                   for spec in specs)
    family_probabilities, coverage_probabilities = [], []
    for spec in specs:
        pool = tasks[spec['environment']]
        family = [task for task in pool if task['family'] == spec['family']]
        kills = sum(killed_by_spec[spec['spec_id']][task['task_id']] for task in family)
        family_probabilities.append(random_probability(len(family), kills, budget))
        covered = [task for task in family if task['task_id'] in spec['support_task_ids']]
        covered_kills = sum(killed_by_spec[spec['spec_id']][task['task_id']] for task in covered)
        coverage_probabilities.append(random_probability(len(covered), covered_kills, budget))
    rate = detected / len(specs) if specs else 0.0
    family_rate = sum(family_probabilities) / len(specs) if specs else 0.0
    coverage_rate = sum(coverage_probabilities) / len(specs) if specs else 0.0
    return {'detectable_specs': len(specs), 'detected': detected, 'detection_rate': rate,
            'skill_family_random_expected_rate': family_rate,
            'absolute_lift_over_skill_family_random': rate - family_rate,
            'predicate_coverage_random_expected_rate': coverage_rate,
            'absolute_lift_over_predicate_coverage_random': rate - coverage_rate,
            'conditional_randomization_p_one_sided': upper_tail(family_probabilities, detected)
            if specs else 1.0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=REVISION / 'config.json')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    artifact = json.loads(Path(config['spec_output']).read_text())
    mutation_dir, oracle = Path(config['mutation_output']), Path(config['oracle_output'])
    if json.loads((mutation_dir / 'completion.json').read_text()).get('status') != 'completed':
        raise ValueError('R24 mutation run is incomplete')
    all_records = rows(oracle / 'trajectories.jsonl')
    records = {environment: [row for row in all_records if row['environment'] == environment]
               for environment in config['expected_tasks']}
    tasks = {environment: task_table(environment, group) for environment, group in records.items()}
    outcomes = rows(mutation_dir / 'outcomes.jsonl')
    outcome_map = {(row['spec_id'], row['task_id']): row for row in outcomes}
    expected = {(spec['spec_id'], task_id) for spec in artifact['specs']
                for task_id in spec['replay_task_ids']}
    if set(outcome_map) != expected or len(outcome_map) != len(outcomes):
        raise ValueError('R24 outcomes differ from frozen operator specs')
    evaluations, killed_by_spec = [], {}
    for spec in artifact['specs']:
        pool = tasks[spec['environment']]
        killed = {task['task_id']: bool(outcome_map.get(
            (spec['spec_id'], task['task_id']), {}).get('killed')) for task in pool}
        killed_by_spec[spec['spec_id']] = killed
        for method in config['selection_methods']:
            seeds = range(config['random_seeds']) if method in RANDOMIZED else [0]
            for seed in seeds:
                order = select_order(method, pool, spec, seed=seed, killed=killed)
                task_curve, step_curve, first = curves(
                    order, killed, config['task_budgets'], config['estimated_step_budgets'])
                row = {'spec_id': spec['spec_id'], 'operator': spec['operator'],
                       'environment': spec['environment'], 'family': spec['family'],
                       'predicate_kind': spec['predicate_kind'],
                       'predicate_value': spec['predicate_value'],
                       'support_count': spec['support_count'],
                       'operator_support_count': spec['operator_support_count'],
                       'method': method, 'seed': seed if method in RANDOMIZED else None,
                       'task_budget_curve': task_curve,
                       'estimated_step_budget_curve': step_curve,
                       'first_kill_rank': first + 1 if first is not None else None}
                if method not in RANDOMIZED:
                    row['order'] = [task['task_id'] for task in order]
                evaluations.append(row)
    output = Path(config['selection_output'])
    output.mkdir(parents=True, exist_ok=True)
    inputs = [args.config, Path(config['roster_output']), Path(config['spec_output']),
              REVISION / 'evaluate.py', REVISION / 'run_mutations.py',
              REVISION / 'generate_specs.py', REVISION / 'mutations.py',
              REVISION / 'audit_confirmation.py', REVISION / 'PROTOCOL.md',
              R22 / 'atoms.py', R22 / 'selection_methods.py',
              mutation_dir / 'run_spec.json', mutation_dir / 'completion.json',
              mutation_dir / 'outcomes.jsonl', oracle / 'run_spec.json',
              oracle / 'completion.json', oracle / 'trajectories.jsonl']
    run_spec = {'status': 'operator_transfer_selection_evaluation', 'config': config,
                'original_source_sha256': source_hash(),
                'revision_inputs': {str(path.resolve().relative_to(ROOT)): digest(path)
                                    for path in inputs},
                'tasks': [{'environment': row['environment'], 'task_id': row['task_id']}
                          for row in all_records]}
    spec_path = output / 'run_spec.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != run_spec:
        raise ValueError('Frozen R24 selection inputs changed')
    spec_path.write_text(json.dumps(run_spec, ensure_ascii=False, indent=2) + '\n')
    evaluation_path = output / 'evaluations.jsonl'
    with evaluation_path.open('w') as stream:
        for row in evaluations:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    detectable = [spec for spec in artifact['specs']
                  if any(killed_by_spec[spec['spec_id']].values())]
    candidate = {row['spec_id']: row for row in evaluations
                 if row['method'] == 'predicate_impact' and row['seed'] is None}
    budget = config['primary_task_budget']
    overall = metric(detectable, tasks, killed_by_spec, candidate, budget)
    by_environment = {environment: metric(
        [spec for spec in detectable if spec['environment'] == environment],
        tasks, killed_by_spec, candidate, budget) for environment in sorted(tasks)}
    by_operator = {operator: metric(
        [spec for spec in detectable if spec['operator'] == operator],
        tasks, killed_by_spec, candidate, budget) for operator in config['operators']}
    families = {(spec['environment'], spec['family']) for spec in detectable}
    gate = config['robustness_gate']
    checks = {
        'minimum_detectable_operator_specs': len(detectable) >= gate['minimum_detectable_operator_specs'],
        'minimum_operator_classes': sum(bool(value['detectable_specs']) for value in by_operator.values()) >= gate['minimum_operator_classes'],
        'minimum_environments': sum(bool(value['detectable_specs']) for value in by_environment.values()) >= gate['minimum_environments'],
        'minimum_skill_families': len(families) >= gate['minimum_skill_families'],
        'minimum_predicate_impact_detection_rate': overall['detection_rate'] >= gate['minimum_predicate_impact_detection_rate'],
        'minimum_absolute_lift_over_skill_family_random': overall['absolute_lift_over_skill_family_random'] >= gate['minimum_absolute_lift_over_skill_family_random'],
        'maximum_conditional_randomization_p': overall['conditional_randomization_p_one_sided'] <= gate['maximum_conditional_randomization_p'],
        'minimum_specs_per_operator': all(value['detectable_specs'] >= gate['minimum_specs_per_operator'] for value in by_operator.values()),
        'minimum_each_operator_detection_rate': all(value['detection_rate'] >= gate['minimum_each_operator_detection_rate'] for value in by_operator.values()),
        'minimum_each_operator_absolute_lift': all(value['absolute_lift_over_skill_family_random'] >= gate['minimum_each_operator_absolute_lift'] for value in by_operator.values()),
    }
    result = {'status': 'completed', 'scope': 'independent_operator_transfer_confirmation',
              'operator_specs': len(artifact['specs']),
              'detectable_operator_specs': len(detectable),
              'detectable_skill_families': len(families), 'primary_task_budget': budget,
              'overall': overall, 'by_environment': by_environment,
              'by_operator': by_operator, 'robustness_gate_checks': checks,
              'robustness_gate_passed': all(checks.values()),
              'claim_scope': ('confirmed_across_three_frozen_mutation_operators'
                              if all(checks.values()) else 'operator_transfer_failed'),
              'population_generalization_claim_permitted': False,
              'reserved_tasks_accessed': len(all_records),
              'evaluations_sha256': digest(evaluation_path)}
    (output / 'completion.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
