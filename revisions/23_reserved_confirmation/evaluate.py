"""Confirm predicate-impact selection on the independently frozen reserved roster."""
from __future__ import annotations

import argparse
from collections import Counter
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


def metric(specs, tasks, killed_by_spec, method_rows, budget):
    detected = sum(method_rows[spec['spec_id']]['task_budget_curve'][str(budget)]['detected']
                   for spec in specs)
    probabilities = []
    for spec in specs:
        family_size = sum(task['family'] == spec['family'] for task in tasks[spec['environment']])
        probabilities.append(random_probability(
            family_size, sum(killed_by_spec[spec['spec_id']].values()), budget))
    rate = detected / len(specs) if specs else 0.0
    baseline = sum(probabilities) / len(probabilities) if probabilities else 0.0
    return {'detectable_specs': len(specs), 'detected': detected,
            'detection_rate': rate, 'skill_family_random_expected_rate': baseline,
            'absolute_lift': rate - baseline,
            'conditional_randomization_p_one_sided': upper_tail(probabilities, detected)
            if probabilities else 1.0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=REVISION / 'config.json')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    artifact = json.loads(Path(config['spec_output']).read_text())
    mutation_dir, oracle = Path(config['mutation_output']), Path(config['oracle_output'])
    if (not (mutation_dir / 'completion.json').exists() or
            json.loads((mutation_dir / 'completion.json').read_text()).get('status') != 'completed'):
        raise ValueError('Reserved mutation run is incomplete')
    all_records = rows(oracle / 'trajectories.jsonl')
    records = {environment: [r for r in all_records if r['environment'] == environment]
               for environment in config['expected_tasks']}
    tasks = {environment: task_table(environment, group) for environment, group in records.items()}
    outcomes = rows(mutation_dir / 'outcomes.jsonl')
    outcome_map = {(row['spec_id'], row['task_id']): row for row in outcomes}
    expected = {(spec['spec_id'], task_id) for spec in artifact['specs']
                for task_id in spec['support_task_ids']}
    if set(outcome_map) != expected or len(outcome_map) != len(outcomes):
        raise ValueError('Reserved outcomes differ from frozen predicate specs')
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
                row = {'spec_id': spec['spec_id'], 'environment': spec['environment'],
                       'family': spec['family'], 'predicate_kind': spec['predicate_kind'],
                       'predicate_value': spec['predicate_value'], 'support_count': spec['support_count'],
                       'method': method, 'seed': seed if method in RANDOMIZED else None,
                       'task_budget_curve': task_curve, 'estimated_step_budget_curve': step_curve,
                       'first_kill_rank': first + 1 if first is not None else None,
                       'first_kill_estimated_steps': (sum(t['healthy_steps'] for t in order[:first + 1])
                                                      if first is not None else None)}
                if method not in RANDOMIZED:
                    row['order'] = [task['task_id'] for task in order]
                evaluations.append(row)
    output = Path(config['selection_output'])
    output.mkdir(parents=True, exist_ok=True)
    inputs = [args.config, Path(config['roster_output']), Path(config['spec_output']),
              REVISION / 'evaluate.py', REVISION / 'run_mutations.py',
              REVISION / 'generate_specs.py', REVISION / 'audit_confirmation.py',
              REVISION / 'PROTOCOL.md', R22 / 'atoms.py', R22 / 'selection_methods.py',
              mutation_dir / 'run_spec.json', mutation_dir / 'completion.json',
              mutation_dir / 'outcomes.jsonl', oracle / 'run_spec.json',
              oracle / 'completion.json', oracle / 'trajectories.jsonl']
    spec_record = {'status': 'reserved_predicate_selection_confirmation', 'config': config,
                   'original_source_sha256': source_hash(),
                   'revision_inputs': {str(p.resolve().relative_to(ROOT)): digest(p) for p in inputs},
                   'tasks': [{'environment': environment, 'task_id': task['task_id']}
                             for environment, group in tasks.items() for task in group]}
    spec_path = output / 'run_spec.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec_record:
        raise ValueError('Frozen reserved selection inputs changed')
    spec_path.write_text(json.dumps(spec_record, ensure_ascii=False, indent=2) + '\n')
    evaluation_path = output / 'evaluations.jsonl'
    with evaluation_path.open('w') as stream:
        for row in evaluations:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
    detectable = [spec for spec in artifact['specs'] if any(killed_by_spec[spec['spec_id']].values())]
    method_rows = {row['spec_id']: row for row in evaluations
                   if row['method'] == 'predicate_impact' and row['seed'] is None}
    budget = config['primary_task_budget']
    overall = metric(detectable, tasks, killed_by_spec, method_rows, budget)
    by_environment = {environment: metric(
        [spec for spec in detectable if spec['environment'] == environment],
        tasks, killed_by_spec, method_rows, budget) for environment in sorted(tasks)}
    multi = [spec for spec in detectable if spec['support_count'] > 1]
    families = {(spec['environment'], spec['family']) for spec in detectable}
    gate = config['confirmatory_gate']
    checks = {
        'minimum_detectable_predicate_specs': len(detectable) >= gate['minimum_detectable_predicate_specs'],
        'minimum_multitask_detectable_specs': len(multi) >= gate['minimum_multitask_detectable_specs'],
        'minimum_environments': sum(bool(v['detectable_specs']) for v in by_environment.values()) >= gate['minimum_environments'],
        'minimum_skill_families': len(families) >= gate['minimum_skill_families'],
        'minimum_predicate_impact_detection_rate': overall['detection_rate'] >= gate['minimum_predicate_impact_detection_rate'],
        'minimum_absolute_lift_over_skill_family_random': overall['absolute_lift'] >= gate['minimum_absolute_lift_over_skill_family_random'],
        'maximum_conditional_randomization_p': overall['conditional_randomization_p_one_sided'] <= gate['maximum_conditional_randomization_p'],
        'minimum_each_environment_detection_rate': all(v['detection_rate'] >= gate['minimum_each_environment_detection_rate'] for v in by_environment.values()),
        'minimum_each_environment_absolute_lift': all(v['absolute_lift'] >= gate['minimum_each_environment_absolute_lift'] for v in by_environment.values()),
        'maximum_each_environment_conditional_p': all(v['conditional_randomization_p_one_sided'] <= gate['maximum_each_environment_conditional_p'] for v in by_environment.values()),
    }
    result = {'status': 'completed', 'scope': 'independent_reserved_confirmation',
              'predicate_specs': len(artifact['specs']), 'detectable_predicate_specs': len(detectable),
              'multitask_detectable_specs': len(multi), 'detectable_skill_families': len(families),
              'primary_task_budget': budget, 'overall': overall,
              'by_environment': by_environment, 'confirmatory_gate_checks': checks,
              'confirmatory_gate_passed': all(checks.values()),
              'claim_scope': ('confirmed_on_frozen_mutation_benchmark' if all(checks.values())
                              else 'confirmation_failed'),
              'population_generalization_claim_permitted': False,
              'reserved_tasks_accessed': len(all_records),
              'evaluations_sha256': digest(evaluation_path)}
    (output / 'completion.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
