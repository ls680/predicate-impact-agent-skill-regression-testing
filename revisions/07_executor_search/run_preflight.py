"""Offline action decisions from archived OLD DEV states; no environment use."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import time

from controllers import CONTROLLERS, select_action
from skilllineage.interactive import LocalChatModel
from skilllineage.provenance import source_hash

REVISION = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def append(path, record):
    with Path(path).open('a') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def select_cases(config):
    if config['split'] != 'dev':
        raise ValueError('Preflight is restricted to old development data')
    reserved = {(row['environment'], row['task_id']) for row in
                json.loads(Path(config['exposure_snapshot']).read_text())['reserved_test_pool']}
    cases = []
    for environment, source in config['sources'].items():
        for episode in rows(source):
            if episode['condition'] != 'factual' or episode['environment'] != environment:
                continue
            if episode['split'] != 'dev' or (environment, episode['task_id']) in reserved:
                raise ValueError('Non-development or reserved task in action preflight')
            turns = episode['turns']
            if not turns:
                raise ValueError('Source episode has no visible decision state')
            selected = {0: ['first']}
            invalid = next((i for i, turn in enumerate(turns) if turn['invalid_output']), None)
            if invalid is not None:
                selected.setdefault(invalid, []).append('first_invalid')
            loop = next((i for i in range(4, len(turns))
                         if len({turn['action'] for turn in turns[i-4:i]}) <= 2
                         and len({turn['score'] for turn in turns[i-4:i]}) == 1), None)
            if loop is not None:
                selected.setdefault(loop, []).append('first_four_turn_loop')
            for index, reasons in sorted(selected.items()):
                case = {
                    'environment': environment, 'family': episode['family'],
                    'task_id': episode['task_id'], 'split': 'dev', 'turn': index,
                    'selection_reasons': reasons, 'source': source,
                    'objective': episode['task_description'],
                    'observation': episode['initial_observation'] if index == 0 else turns[index-1]['observation'],
                    'initial_observation': episode['initial_observation'],
                    'history': [[turn['action'], turn['observation']] for turn in turns[:index]],
                    'actions': turns[index]['admissible_actions'],
                    'skill_sha256': episode['skill_sha256'],
                }
                case['case_id'] = hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest()
                cases.append(case)
    if not cases or len({case['case_id'] for case in cases}) != len(cases):
        raise ValueError('Empty or duplicate preflight cases')
    return cases


def analyze(output):
    spec = json.loads((output / 'run_spec.json').read_text())
    records = rows(output / 'decisions.jsonl')
    cases, controllers = spec['cases'], spec['config']['controllers']
    expected = {(case['case_id'], controller) for case in cases for controller in controllers}
    keys = [(row['case_id'], row['controller']) for row in records]
    if len(keys) != len(set(keys)) or set(keys) != expected:
        raise ValueError('Incomplete or duplicate decision coverage')
    grouped = defaultdict(list)
    for row in records:
        grouped[row['controller']].append(row)
    summary = {}
    for controller, group in grouped.items():
        summary[controller] = {
            'decisions': len(group), 'invalid': sum(not row['valid'] for row in group),
            'explicit_focus_mismatches': sum(row['focus_mismatch'] is True for row in group),
            'focus_decisions_with_exact_binding': sum(row['focus_mismatch'] is not None for row in group),
            'recent_repeats_not_necessarily_errors': sum(row['repeated_recent_action'] for row in group),
            'model_calls': sum(len(row['calls']) for row in group),
            'input_tokens': sum(row['input_tokens'] for row in group),
            'output_tokens': sum(row['output_tokens'] for row in group),
            'latency_sec': sum(row['latency_sec'] for row in group),
        }
    result = {
        'status': 'completed', 'evidence': 'old_development_offline_action_preflight',
        'cases': len(cases), 'tasks': len(spec['tasks']), 'summary': summary,
        'new_environment_interactions': 0,
        'task_success_gain_measured': False,
        'advance_to_independent_test': False,
        'warning': 'Legality and explicit binding are only interface checks, not task success. '
                   'Several cases share each task and cannot be treated as independent task outcomes.',
    }
    (output / 'analysis.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=REVISION / 'pilot_config.json')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--analyze-only', action='store_true')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    if config['controllers'] != list(CONTROLLERS):
        raise ValueError('Registered six-controller roster changed')
    output = Path(config['output_dir'])
    output.mkdir(parents=True, exist_ok=True)
    if args.analyze_only:
        print(json.dumps(analyze(output), ensure_ascii=False))
        return
    base = json.loads(Path(config['base_config']).read_text())
    cases = select_cases(config)
    versions = Path(config['base_run']) / 'skill_versions.jsonl'
    inputs = [args.config, Path(config['base_config']), versions,
              Path(config['exposure_snapshot']), REVISION / 'controllers.py',
              REVISION / 'run_preflight.py', Path('revisions/02_evidence_gated_repair/repair.py'),
              *map(Path, config['sources'].values())]
    spec = {
        'config': config, 'base_config': base, 'original_source_sha256': source_hash(),
        'revision_inputs': {str(path.resolve().relative_to(REVISION.parents[1])): digest(path)
                            for path in inputs},
        'cases': cases,
        'tasks': [dict(environment=environment, task_id=task_id, split='dev')
                  for environment, task_id in sorted({(case['environment'], case['task_id']) for case in cases})],
    }
    spec_path = output / 'run_spec.json'
    if spec_path.exists() and json.loads(spec_path.read_text()) != spec:
        raise ValueError('Frozen preflight inputs/configuration changed; use a new revision')
    spec_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'prepared_cases': len(cases), 'tasks': len(spec['tasks']),
                      'decisions': len(cases) * len(CONTROLLERS)}), flush=True)
    if args.prepare_only:
        return
    skills = {(row['environment'], row['family']): row['skill_text']
              for row in rows(versions) if row['condition'] == 'factual'
              and row['depth'] == base['lineage_depth']}
    completed = {(row['case_id'], row['controller']) for row in rows(output / 'decisions.jsonl')}
    model = LocalChatModel(base['model_id'], revision=base['model_revision'],
                           local_files_only=base['local_files_only'])
    started = time.perf_counter()
    for index, case in enumerate(cases):
        skill = skills[(case['environment'], case['family'])]
        if hashlib.sha256(skill.encode()).hexdigest() != case['skill_sha256']:
            raise ValueError('Source skill does not match archived factual state')
        shift = index % len(CONTROLLERS)
        for controller in CONTROLLERS[shift:] + CONTROLLERS[:shift]:
            key = (case['case_id'], controller)
            if key in completed:
                continue
            record = select_action(
                model, controller, case, skill, seed=config['seed'] + index,
                action_budget=config['max_new_tokens_action'], plan_budget=config['max_new_tokens_plan'])
            record.update(case_id=case['case_id'], environment=case['environment'],
                          task_id=case['task_id'], turn=case['turn'], split='dev')
            append(output / 'decisions.jsonl', record)
            completed.add(key)
            print(json.dumps({key: value for key, value in record.items()
                              if key not in ('calls', 'contract')}), flush=True)
    result = analyze(output)
    result.update(elapsed_seconds_this_process=time.perf_counter() - started,
                  peak_cuda_memory_gib=model.torch.cuda.max_memory_reserved() / 1024**3)
    (output / 'completion.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
