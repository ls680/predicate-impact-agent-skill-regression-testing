"""Native replay of the frozen R24 predicate-operator specifications."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

REVISION = Path(__file__).resolve().parent
ROOT = REVISION.parents[1]
R22 = ROOT / 'revisions/22_predicate_impact_testing'
sys.path.insert(0, str(ROOT / 'revisions/04_state_matched_execution'))
sys.path.insert(0, str(ROOT / 'revisions/07_executor_search'))
sys.path.insert(0, str(R22))
sys.path.insert(0, str(REVISION))
from run_preflight import append, digest, rows
from state_check import PinnedScienceworldSession, state_signature, validate_jar
from mutations import mutate_program
from skilllineage.interactive_envs import AlfworldEpisode
from skilllineage.provenance import source_hash


def initial_signature(record):
    return state_signature(record['observations'][0], record['task_description'],
                           record['turns'][0]['admissible_actions'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=REVISION / 'config.json')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    artifact = json.loads(Path(config['spec_output']).read_text())
    if (artifact['status'] != 'operator_specs_frozen_before_mutation_outcomes'
            or artifact['generation_reads_mutation_outcomes']):
        raise ValueError('R24 operator specs are not frozen outcome-blind inputs')
    oracle = Path(config['oracle_output'])
    records = rows(oracle / 'trajectories.jsonl')
    lookup = {(row['environment'], row['task_id']): row for row in records}
    roster = json.loads(Path(config['roster_output']).read_text())
    authorized = {(row['environment'], row['task_id']) for row in roster['tasks']}
    planned = [(spec, lookup[(spec['environment'], task_id)])
               for spec in artifact['specs'] for task_id in spec['replay_task_ids']]
    if not {(spec['environment'], row['task_id']) for spec, row in planned} <= authorized:
        raise ValueError('R24 replay outside frozen roster')
    if args.validate_only:
        print(json.dumps({'status': 'validated_without_environment',
                          'specs': len(artifact['specs']), 'native_replays': len(planned),
                          'by_environment': dict(Counter(s['environment'] for s, _ in planned)),
                          'by_operator': dict(Counter(s['operator'] for s, _ in planned))}))
        return
    validate_jar(config['scienceworld_jar'])
    output = Path(config['mutation_output'])
    output.mkdir(parents=True, exist_ok=True)
    inputs = [args.config, Path(config['roster_output']), Path(config['spec_output']),
              REVISION / 'generate_specs.py', REVISION / 'mutations.py',
              REVISION / 'run_mutations.py', REVISION / 'audit_confirmation.py',
              REVISION / 'PROTOCOL.md', R22 / 'atoms.py', R22 / 'generate_specs.py',
              Path(config['scienceworld_jar']), oracle / 'run_spec.json',
              oracle / 'completion.json', oracle / 'trajectories.jsonl',
              ROOT / 'src/skilllineage/interactive_envs.py',
              ROOT / 'revisions/04_state_matched_execution/state_check.py',
              ROOT / 'revisions/07_executor_search/run_preflight.py']
    run_spec = {
        'status': 'reserved_operator_transfer_native_mutations', 'config': config,
        'original_source_sha256': source_hash(),
        'revision_inputs': {str(path.resolve().relative_to(ROOT)): digest(path) for path in inputs},
        'tasks': [{'environment': row['environment'], 'task_id': row['task_id']} for row in records],
        'planned_replays': [{'spec_id': spec['spec_id'], 'operator': spec['operator'],
                             'environment': spec['environment'], 'task_id': row['task_id']}
                            for spec, row in planned],
    }
    spec_path = output / 'run_spec.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != run_spec:
        raise ValueError('Frozen R24 mutation inputs changed')
    if not spec_path.exists():
        if list(output.glob('*.jsonl')):
            raise ValueError('Cold R24 run contains unowned evidence')
        spec_path.write_text(json.dumps(run_spec, ensure_ascii=False, indent=2) + '\n')
    outcome_path = output / 'outcomes.jsonl'
    outcomes = rows(outcome_path)
    completed = {(row['spec_id'], row['task_id']) for row in outcomes}
    expected = {(spec['spec_id'], row['task_id']) for spec, row in planned}
    if len(completed) != len(outcomes) or not completed <= expected:
        raise ValueError('Invalid saved R24 outcomes')
    science = PinnedScienceworldSession(max_steps=config['max_steps']['scienceworld'],
                                        jar=Path(config['scienceworld_jar']))
    try:
        for mutation_spec, record in planned:
            key = mutation_spec['spec_id'], record['task_id']
            if key in completed:
                continue
            started, episode = time.perf_counter(), None
            if mutation_spec['environment'] == 'scienceworld':
                science.configure(record['family'], record['variation'], 'easy')
                episode = science
            else:
                episode = AlfworldEpisode(Path(os.environ['ALFWORLD_DATA']) / record['task_id'],
                                          max_steps=config['max_steps']['alfworld'], expert=False)
            try:
                observation, objective, admissible = episode.reset()
                signature = state_signature(observation, objective, admissible)
                if signature != initial_signature(record):
                    raise RuntimeError('R24 mutation initial state mismatch')
                actions, event = mutate_program(record, mutation_spec)
                score, done, environment_steps, turns = 0.0, False, 0, []
                for program_index, action in enumerate(actions):
                    if done or environment_steps >= config['max_steps'][mutation_spec['environment']]:
                        break
                    if action is None:
                        turns.append({'program_index': program_index, 'action': None,
                                      'deleted': True, 'score': score, 'done': done})
                        continue
                    next_observation, score, done, next_actions = episode.step(action)
                    turns.append({'program_index': program_index, 'action': action,
                                  'listed_admissible': action in admissible,
                                  'observation': next_observation, 'score': score, 'done': done})
                    environment_steps += 1
                    observation, admissible = next_observation, next_actions
            finally:
                if mutation_spec['environment'] == 'alfworld' and episode is not None:
                    episode.close()
            outcome = {
                'spec_id': mutation_spec['spec_id'], 'base_spec_id': mutation_spec['base_spec_id'],
                'environment': mutation_spec['environment'], 'family': mutation_spec['family'],
                'predicate_kind': mutation_spec['predicate_kind'],
                'predicate_value': mutation_spec['predicate_value'],
                'operator': mutation_spec['operator'], 'task_id': record['task_id'],
                'healthy_success': True, 'healthy_steps': len(record['executed_actions']),
                'initial_state_match': True, 'initial_state_sha256': signature,
                'mutation_applied': True, 'mutation_event': event, 'turns': turns,
                'environment_steps': environment_steps, 'score': score, 'done': done,
                'success': score >= .999, 'killed': score < .999,
                'technical_error': None, 'elapsed_seconds': time.perf_counter() - started,
            }
            append(outcome_path, outcome)
            outcomes.append(outcome)
            completed.add(key)
            print(json.dumps({key: value for key, value in outcome.items()
                              if key not in ('turns', 'mutation_event')},
                             ensure_ascii=False), flush=True)
    finally:
        science.close()
    if completed != expected:
        raise ValueError('Incomplete R24 mutation coverage')
    detectable = {spec['spec_id'] for spec in artifact['specs']
                  if any(row['spec_id'] == spec['spec_id'] and row['killed'] for row in outcomes)}
    result = {
        'status': 'completed', 'operator_specs': len(artifact['specs']),
        'actual_native_replays': len(outcomes), 'killed_pairs': sum(row['killed'] for row in outcomes),
        'detectable_specs': len(detectable), 'technical_failures_counted_as_kills': 0,
        'initial_state_exact_matches': sum(row['initial_state_match'] for row in outcomes),
        'by_environment': dict(Counter(row['environment'] for row in outcomes)),
        'by_operator': dict(Counter(row['operator'] for row in outcomes)),
        'reserved_tasks_accessed': len(records), 'outcomes_sha256': digest(outcome_path),
    }
    (output / 'completion.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
