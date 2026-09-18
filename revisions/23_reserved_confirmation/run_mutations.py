"""Native predicate-mutation replay on the frozen reserved confirmation roster."""
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
from run_preflight import append, digest, rows
from state_check import PinnedScienceworldSession, state_signature, validate_jar
from atoms import PredicateDeletion, trace_atoms
from skilllineage.interactive_envs import AlfworldEpisode
from skilllineage.provenance import source_hash


def initial_signature(record):
    if not record['observations'] or not record['turns']:
        raise ValueError(f"Reserved healthy reference lacks initial state: {record['task_id']}")
    return state_signature(record['observations'][0], record['task_description'],
                           record['turns'][0]['admissible_actions'])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=REVISION / 'config.json')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    artifact = json.loads(Path(config['spec_output']).read_text())
    if (artifact['status'] != 'reserved_predicate_specs_frozen_before_mutation_outcomes'
            or artifact['generation_reads_mutation_outcomes']):
        raise ValueError('Reserved predicate specs are not frozen outcome-blind inputs')
    oracle = Path(config['oracle_output'])
    records = rows(oracle / 'trajectories.jsonl')
    lookup = {(r['environment'], r['task_id']): r for r in records}
    roster = json.loads(Path(config['roster_output']).read_text())
    authorized = {(r['environment'], r['task_id']) for r in roster['tasks']}
    planned = []
    for spec in artifact['specs']:
        actual = sorted(r['task_id'] for r in records if r['environment'] == spec['environment']
                        and r['family'] == spec['family'] and r['success'] and not r['error']
                        and (spec['predicate_kind'], spec['predicate_value']) in
                        trace_atoms(spec['environment'], r['executed_actions']))
        if actual != spec['support_task_ids']:
            raise ValueError('Reserved predicate support changed')
        planned.extend((spec, lookup[(spec['environment'], task_id)])
                       for task_id in spec['support_task_ids'])
    if not {(s['environment'], r['task_id']) for s, r in planned} <= authorized:
        raise ValueError('Mutation replay outside reserved roster')
    if args.validate_only:
        print(json.dumps({'status': 'validated_without_environment',
                          'specs': len(artifact['specs']), 'native_replays': len(planned),
                          'by_environment': dict(Counter(s['environment'] for s, _ in planned))}))
        return
    validate_jar(config['scienceworld_jar'])
    output = Path(config['mutation_output'])
    output.mkdir(parents=True, exist_ok=True)
    inputs = [args.config, Path(config['roster_output']), Path(config['spec_output']),
              REVISION / 'generate_specs.py', REVISION / 'run_mutations.py',
              REVISION / 'audit_confirmation.py', REVISION / 'PROTOCOL.md',
              R22 / 'atoms.py', R22 / 'generate_specs.py', Path(config['scienceworld_jar']),
              oracle / 'run_spec.json', oracle / 'completion.json', oracle / 'trajectories.jsonl',
              ROOT / 'src/skilllineage/interactive_envs.py',
              ROOT / 'revisions/04_state_matched_execution/state_check.py',
              ROOT / 'revisions/07_executor_search/run_preflight.py']
    spec_record = {
        'status': 'reserved_predicate_native_mutations', 'config': config,
        'original_source_sha256': source_hash(),
        'revision_inputs': {str(p.resolve().relative_to(ROOT)): digest(p) for p in inputs},
        'tasks': [{'environment': r['environment'], 'task_id': r['task_id']} for r in records],
        'planned_replays': [{'spec_id': s['spec_id'], 'environment': s['environment'],
                             'task_id': r['task_id']} for s, r in planned],
    }
    spec_path = output / 'run_spec.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec_record:
        raise ValueError('Frozen reserved mutation inputs changed')
    if not spec_path.exists():
        if list(output.glob('*.jsonl')):
            raise ValueError('Cold reserved mutation run contains unowned evidence')
        spec_path.write_text(json.dumps(spec_record, ensure_ascii=False, indent=2) + '\n')
    outcome_path = output / 'outcomes.jsonl'
    outcomes = rows(outcome_path)
    completed = {(r['spec_id'], r['task_id']) for r in outcomes}
    expected = {(s['spec_id'], r['task_id']) for s, r in planned}
    if len(completed) != len(outcomes) or not completed <= expected:
        raise ValueError('Invalid saved reserved mutation outcomes')
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
                science.configure(record['family'], record['variation'], 'easy')
                episode = science
            else:
                episode = AlfworldEpisode(Path(os.environ['ALFWORLD_DATA']) / record['task_id'],
                                          max_steps=config['max_steps']['alfworld'], expert=False)
            try:
                observation, objective, admissible = episode.reset()
                signature = state_signature(observation, objective, admissible)
                if signature != initial_signature(record):
                    raise RuntimeError('Reserved mutation initial state mismatch')
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
                    raise RuntimeError('Applicable reserved mutation was not applied')
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
    if completed != expected:
        raise ValueError('Incomplete reserved mutation coverage')
    detectable = {s['spec_id'] for s in artifact['specs']
                  if any(r['spec_id'] == s['spec_id'] and r['killed'] for r in outcomes)}
    result = {
        'status': 'completed', 'predicate_specs': len(artifact['specs']),
        'actual_native_replays': len(outcomes), 'killed_pairs': sum(r['killed'] for r in outcomes),
        'detectable_specs': len(detectable), 'technical_failures_counted_as_kills': 0,
        'initial_state_exact_matches': sum(r['initial_state_match'] for r in outcomes),
        'by_environment': dict(Counter(r['environment'] for r in outcomes)),
        'reserved_tasks_accessed': len({(r['environment'], r['task_id']) for r in records}),
        'outcomes_sha256': digest(outcome_path),
    }
    (output / 'completion.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
