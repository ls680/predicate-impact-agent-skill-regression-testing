"""Collect native healthy references on the pre-frozen reserved roster."""
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
sys.path.insert(0, str(ROOT / 'revisions/04_state_matched_execution'))
sys.path.insert(0, str(ROOT / 'revisions/07_executor_search'))
from run_preflight import append, digest, rows
from state_check import PinnedScienceworldSession, validate_jar
from skilllineage.interactive_envs import AlfworldEpisode
from skilllineage.provenance import source_hash


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=REVISION / 'config.json')
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    gate = json.loads(Path(config['development_gate']).read_text())
    if not gate['development_gate_passed'] or not gate['advance_to_reserved_confirmation']:
        raise ValueError('Development gate does not authorize confirmation')
    roster_path = Path(config['roster_output'])
    roster = json.loads(roster_path.read_text())
    if roster['status'] != 'roster_frozen_before_task_content_or_oracle_access':
        raise ValueError('Reserved roster is not frozen')
    tasks = roster['tasks']
    if args.validate_only:
        print(json.dumps({'status': 'validated_without_environment', 'tasks': len(tasks),
                          'by_environment': dict(Counter(t['environment'] for t in tasks))}))
        return
    validate_jar(config['scienceworld_jar'])
    data_root = Path(os.environ['ALFWORLD_DATA'])
    audited_tasks = []
    for task in tasks:
        audited = dict(task)
        if task['environment'] == 'alfworld':
            audited['gamefile_sha256'] = digest(data_root / task['task_id'])
        audited_tasks.append(audited)
    inputs = [args.config, roster_path, REVISION / 'freeze_roster.py',
              REVISION / 'collect_oracles.py', REVISION / 'audit_confirmation.py',
              REVISION / 'PROTOCOL.md', Path(config['development_gate']),
              Path(config['exposure_snapshot']), Path(config['scienceworld_jar']),
              ROOT / 'src/skilllineage/interactive_envs.py',
              ROOT / 'revisions/04_state_matched_execution/state_check.py',
              ROOT / 'revisions/07_executor_search/run_preflight.py']
    spec = {
        'status': config['status'], 'config': config, 'tasks': audited_tasks,
        'original_source_sha256': source_hash(),
        'revision_inputs': {str(p.resolve().relative_to(ROOT)): digest(p) for p in inputs},
    }
    output = Path(config['oracle_output'])
    output.mkdir(parents=True, exist_ok=True)
    spec_path = output / 'run_spec.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec:
        raise ValueError('Frozen confirmation oracle inputs changed')
    if not spec_path.exists():
        if list(output.glob('*.jsonl')):
            raise ValueError('Cold confirmation collection contains unowned evidence')
        spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
    saved = rows(output / 'trajectories.jsonl')
    completed = {(r['environment'], r['task_id']) for r in saved}
    expected = {(r['environment'], r['task_id']) for r in tasks}
    if len(completed) != len(saved) or not completed <= expected:
        raise ValueError('Invalid saved confirmation oracle records')
    science = PinnedScienceworldSession(max_steps=config['max_steps']['scienceworld'],
                                        jar=Path(config['scienceworld_jar']))
    try:
        for task in tasks:
            key = task['environment'], task['task_id']
            if key in completed:
                continue
            started = time.perf_counter()
            episode = None
            actions, turns, observations, error = [], [], [], None
            objective, score, done = '', 0.0, False
            try:
                if task['environment'] == 'alfworld':
                    episode = AlfworldEpisode(data_root / task['task_id'],
                                              max_steps=config['max_steps']['alfworld'], expert=True)
                else:
                    science.env.load(task['family'], task['variation'], 'easy', generateGoldPath=True)
                    if task['variation'] not in list(science.env.get_variations_test()):
                        raise ValueError('Reserved ScienceWorld variation is not official TEST')
                    episode = science
                observation, objective, admissible = episode.reset()
                observations.append(observation)
                gold = (list(science.env.get_gold_action_sequence())
                        if task['environment'] == 'scienceworld' else None)
                for index in range(config['max_steps'][task['environment']]):
                    action = (episode.expert_action() if task['environment'] == 'alfworld'
                              else (gold[index] if index < len(gold) else None))
                    if not action:
                        error = 'Expert/gold actions exhausted before confirmed success'
                        break
                    next_observation, score, done, next_actions = episode.step(action)
                    turns.append({'turn': index, 'action': action, 'admissible_actions': admissible,
                                  'listed_admissible': action in admissible,
                                  'observation': next_observation, 'score': score, 'done': done})
                    actions.append(action)
                    observations.append(next_observation)
                    observation, admissible = next_observation, next_actions
                    if done:
                        break
                if score < .999:
                    error = error or 'Reference did not reach confirmed success within fixed budget'
            except Exception as failure:
                error = type(failure).__name__ + ': ' + str(failure)
            finally:
                if task['environment'] == 'alfworld' and episode is not None:
                    episode.close()
            record = {
                **task, 'split': 'reserved_confirmation', 'task_description': objective,
                'executed_actions': actions, 'observations': observations, 'turns': turns,
                'score': score, 'success': score >= .999, 'done': done, 'error': error,
                'oracle_access_scope': 'frozen_reserved_confirmation_only',
                'unlisted_reference_actions': sum(not turn['listed_admissible'] for turn in turns),
                'elapsed_seconds': time.perf_counter() - started,
            }
            append(output / 'trajectories.jsonl', record)
            completed.add(key)
            print(json.dumps({k: v for k, v in record.items()
                              if k not in ('turns', 'observations', 'executed_actions')},
                             ensure_ascii=False), flush=True)
    finally:
        science.close()
    records = rows(output / 'trajectories.jsonl')
    if {(r['environment'], r['task_id']) for r in records} != expected or len(records) != len(expected):
        raise ValueError('Incomplete reserved oracle collection')
    result = {
        'status': 'completed', 'tasks': len(records),
        'successful_references': sum(r['success'] and not r['error'] for r in records),
        'failed_references': sum(not (r['success'] and not r['error']) for r in records),
        'by_environment': dict(Counter(r['environment'] for r in records)),
        'by_environment_success': dict(Counter(r['environment'] for r in records
                                               if r['success'] and not r['error'])),
        'by_family_success': {'/'.join(key): value for key, value in Counter(
            (r['environment'], r['family']) for r in records if r['success'] and not r['error']).items()},
        'unlisted_reference_actions': sum(r['unlisted_reference_actions'] for r in records),
        'reserved_tasks_accessed': len(records),
        'trajectories_sha256': digest(output / 'trajectories.jsonl'),
    }
    (output / 'completion.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
