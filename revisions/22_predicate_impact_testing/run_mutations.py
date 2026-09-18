"""Native replay of frozen sparse predicate-scoped skill regressions."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys
import time

REVISION = Path(__file__).resolve().parent
ROOT = REVISION.parents[1]
sys.path.insert(0, str(ROOT / 'revisions/04_state_matched_execution'))
sys.path.insert(0, str(ROOT / 'revisions/07_executor_search'))
from run_preflight import append, digest, rows
from state_check import PinnedScienceworldSession, state_signature, validate_jar
from atoms import PredicateDeletion, trace_atoms
from skilllineage.interactive_envs import AlfworldEpisode
from skilllineage.provenance import source_hash


def load_inputs(config):
    artifact = json.loads(Path(config['spec_output']).read_text())
    if artifact['status'] != config['status'] or artifact['generation_reads_mutation_outcomes']:
        raise ValueError('Predicate specification artifact is not outcome-blind and frozen')
    records = {environment: rows(path + '/trajectories.jsonl')
               for environment, path in config['healthy_runs'].items()}
    lookup = {(environment, record['task_id']): record
              for environment, group in records.items() for record in group}
    for environment, group in records.items():
        if len(group) != config['expected_tasks'][environment]:
            raise ValueError('Healthy input count changed')
    for spec in artifact['specs']:
        actual = sorted(record['task_id'] for record in records[spec['environment']]
                        if record['family'] == spec['family'] and record['success'] and not record['error']
                        and (spec['predicate_kind'], spec['predicate_value']) in
                        trace_atoms(spec['environment'], record['executed_actions']))
        if actual != spec['support_task_ids']:
            raise ValueError(f'Predicate support changed for {spec["spec_id"]}')
    return artifact, records, lookup


def initial_signature(record):
    if not record['observations'] or not record['turns']:
        raise ValueError(f"Healthy reference lacks initial state: {record['task_id']}")
    return state_signature(record['observations'][0], record['task_description'],
                           record['turns'][0]['admissible_actions'])


def summarize(config, artifact, records, outcomes, output):
    expected = {(spec['spec_id'], task_id) for spec in artifact['specs']
                for task_id in spec['support_task_ids']}
    observed = [(row['spec_id'], row['task_id']) for row in outcomes]
    if len(observed) != len(set(observed)) or set(observed) != expected:
        raise ValueError('Incomplete or duplicate predicate mutation coverage')
    grouped = defaultdict(list)
    for row in outcomes:
        grouped[row['spec_id']].append(row)
    eligible = sum(r['success'] and not r['error'] for group in records.values() for r in group)
    result = {
        'status': 'completed', 'predicate_specs': len(artifact['specs']),
        'actual_native_replays': len(outcomes),
        'eligible_healthy_tasks': eligible,
        'inferred_identical_no_ops': sum(
            spec['family_healthy_tasks'] - spec['support_count'] for spec in artifact['specs']),
        'killed_pairs': sum(row['killed'] for row in outcomes),
        'detectable_specs': sum(any(row['killed'] for row in grouped[spec['spec_id']])
                                for spec in artifact['specs']),
        'technical_failures_counted_as_kills': 0,
        'initial_state_exact_matches': sum(row['initial_state_match'] for row in outcomes),
        'by_environment': dict(Counter(row['environment'] for row in outcomes)),
        'reserved_tasks_accessed': 0,
        'outcomes_sha256': digest(output / 'outcomes.jsonl'),
    }
    (output / 'completion.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=REVISION / 'config.json')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    validate_jar(config['scienceworld_jar'])
    artifact, records, lookup = load_inputs(config)
    exposure = json.loads(Path(config['exposure_snapshot']).read_text())
    reserved = {(r['environment'], r['task_id']) for r in exposure['reserved_test_pool']}
    planned = [(spec, lookup[(spec['environment'], task_id)])
               for spec in artifact['specs'] for task_id in spec['support_task_ids']]
    if reserved & {(spec['environment'], record['task_id']) for spec, record in planned}:
        raise ValueError('Reserved task selected for predicate mutation development')
    if args.validate_only:
        print(json.dumps({'status': 'validated_without_environment',
                          'specs': len(artifact['specs']), 'native_replays': len(planned),
                          'by_environment': dict(Counter(s['environment'] for s, _ in planned)),
                          'reserved_overlap': 0}))
        return
    output = Path(config['mutation_output'])
    output.mkdir(parents=True, exist_ok=True)
    inputs = [args.config, REVISION / 'predicate_specs.json', REVISION / 'atoms.py',
              REVISION / 'run_mutations.py', REVISION / 'PROTOCOL.md',
              Path(config['exposure_snapshot']), Path(config['scienceworld_jar']),
              ROOT / 'src/skilllineage/interactive_envs.py',
              ROOT / 'revisions/04_state_matched_execution/state_check.py',
              ROOT / 'revisions/07_executor_search/run_preflight.py']
    for path in config['healthy_runs'].values():
        inputs.extend([Path(path) / name for name in
                       ('run_spec.json', 'completion.json', 'trajectories.jsonl')])
    spec = {
        'status': config['status'], 'config': config, 'original_source_sha256': source_hash(),
        'revision_inputs': {str(p.resolve().relative_to(ROOT)): digest(p) for p in inputs},
        'tasks': [{'environment': environment, 'task_id': record['task_id']}
                  for environment, group in records.items() for record in group],
        'planned_replays': [{'spec_id': s['spec_id'], 'environment': s['environment'],
                             'task_id': r['task_id']} for s, r in planned],
    }
    spec_path = output / 'run_spec.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec:
        raise ValueError('Frozen R22 mutation inputs changed')
    if not spec_path.exists():
        if list(output.glob('*.jsonl')):
            raise ValueError('Cold R22 run contains unowned evidence')
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
    outcome_path = output / 'outcomes.jsonl'
    outcomes = rows(outcome_path)
    completed = {(row['spec_id'], row['task_id']) for row in outcomes}
    expected = {(s['spec_id'], r['task_id']) for s, r in planned}
    if len(completed) != len(outcomes) or not completed <= expected:
        raise ValueError('Invalid saved R22 outcomes')
    science = PinnedScienceworldSession(max_steps=config['max_steps']['scienceworld'],
                                        jar=Path(config['scienceworld_jar']))
    try:
        for mutation_spec, record in planned:
            key = mutation_spec['spec_id'], record['task_id']
            if key in completed:
                continue
            started = time.perf_counter()
            episode = None
            if mutation_spec['environment'] == 'scienceworld':
                science.configure(record['family'], record['variation'], record['simplifications'])
                episode = science
            else:
                episode = AlfworldEpisode(Path(os.environ['ALFWORLD_DATA']) / record['gamefile'],
                                          max_steps=config['max_steps']['alfworld'], expert=False)
            try:
                observation, objective, admissible = episode.reset()
                signature = state_signature(observation, objective, admissible)
                if signature != initial_signature(record):
                    raise RuntimeError(f'Initial state mismatch for {mutation_spec["spec_id"]}/{record["task_id"]}')
                mutation = PredicateDeletion(mutation_spec)
                score, done, environment_steps = 0.0, False, 0
                turns, events = [], []
                for program_index, original_action in enumerate(record['executed_actions']):
                    if done or environment_steps >= config['max_steps'][mutation_spec['environment']]:
                        break
                    action, changed, evidence = mutation.transform(original_action)
                    if changed:
                        events.append({'program_index': program_index,
                                       'environment_step_before': environment_steps,
                                       'original_action': original_action, 'mutated_action': action,
                                       **(evidence or {})})
                    if action is None:
                        turns.append({'program_index': program_index, 'original_action': original_action,
                                      'action': None, 'deleted': True, 'score': score, 'done': done})
                        continue
                    next_observation, score, done, next_actions = episode.step(action)
                    turns.append({'program_index': program_index, 'environment_step': environment_steps,
                                  'original_action': original_action, 'action': action,
                                  'changed': changed, 'listed_admissible': action in admissible,
                                  'observation': next_observation, 'score': score, 'done': done})
                    environment_steps += 1
                    observation, admissible = next_observation, next_actions
                if not mutation.applied:
                    raise RuntimeError(f'Predicate mutation was not applied: {mutation_spec["spec_id"]}')
            finally:
                if mutation_spec['environment'] == 'alfworld' and episode is not None:
                    episode.close()
            outcome = {
                'spec_id': mutation_spec['spec_id'], 'environment': mutation_spec['environment'],
                'family': mutation_spec['family'], 'predicate_kind': mutation_spec['predicate_kind'],
                'predicate_value': mutation_spec['predicate_value'], 'task_id': record['task_id'],
                'healthy_success': True, 'healthy_steps': len(record['executed_actions']),
                'initial_state_match': True, 'initial_state_sha256': signature,
                'mutation_applied': True, 'mutation_events': events, 'turns': turns,
                'environment_steps': environment_steps, 'score': score, 'done': done,
                'success': score >= .999, 'killed': score < .999, 'technical_error': None,
                'elapsed_seconds': time.perf_counter() - started,
            }
            append(outcome_path, outcome)
            outcomes.append(outcome)
            completed.add(key)
            print(json.dumps({k: v for k, v in outcome.items()
                              if k not in ('turns', 'mutation_events')}, ensure_ascii=False), flush=True)
    finally:
        science.close()
    result = summarize(config, artifact, records, outcomes, output)
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
