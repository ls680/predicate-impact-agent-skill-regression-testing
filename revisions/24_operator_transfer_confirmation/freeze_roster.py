"""Freeze the second, content-blind roster after excluding all R23 tasks."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

REVISION = Path(__file__).resolve().parent
ROOT = REVISION.parents[1]
sys.path.insert(0, str(ROOT / 'revisions/07_executor_search'))
from run_preflight import digest
from skilllineage.provenance import source_hash


def rank(task, seed):
    payload = f"{seed}:{task['environment']}:{task['family']}:{task['task_id']}"
    return hashlib.sha256(payload.encode()).hexdigest()


def select(snapshot, previous, config):
    used = {(task['environment'], task['task_id']) for task in previous['tasks']}
    selected = []
    for environment, family_counts in config['selection_counts'].items():
        for family, count in family_counts.items():
            candidates = [task for task in snapshot['reserved_test_pool']
                          if task['environment'] == environment and task['family'] == family
                          and task['compatible_with_original_scope']
                          and (environment, task['task_id']) not in used]
            chosen = sorted(candidates, key=lambda task: rank(task, config['selection_seed']))[:count]
            if len(chosen) != count:
                raise ValueError(f'Insufficient untouched tasks for {environment}/{family}')
            selected.extend(chosen)
    keys = [(task['environment'], task['task_id']) for task in selected]
    if len(keys) != len(set(keys)) or set(keys) & used:
        raise ValueError('R24 roster duplicates or overlaps R23')
    for environment, expected in config['expected_tasks'].items():
        if sum(task['environment'] == environment for task in selected) != expected:
            raise ValueError('Frozen environment sample count mismatch')
    return selected


def main():
    config_path = REVISION / 'config.json'
    config = json.loads(config_path.read_text())
    gate_path = Path(config['confirmation_gate'])
    gate = json.loads(gate_path.read_text())
    if not gate['confirmatory_gate_passed']:
        raise ValueError('R23 did not authorize operator-transfer confirmation')
    snapshot_path = Path(config['exposure_snapshot'])
    previous_path = Path(config['previous_roster'])
    snapshot, previous = json.loads(snapshot_path.read_text()), json.loads(previous_path.read_text())
    tasks = select(snapshot, previous, config)
    inputs = [config_path, REVISION / 'freeze_roster.py', REVISION / 'PROTOCOL.md',
              gate_path, gate_path.parent / 'run_spec.json',
              gate_path.parent / 'confirmation_audit.json', snapshot_path, previous_path]
    artifact = {
        'status': 'roster_frozen_before_task_content_or_oracle_access',
        'selection_uses_only': ['environment', 'family', 'task_id',
                                'compatible_with_original_scope', 'R23 exclusion'],
        'selection_seed': config['selection_seed'], 'tasks': tasks,
        'task_count': len(tasks), 'by_environment': dict(Counter(t['environment'] for t in tasks)),
        'overlap_with_r23': 0, 'original_source_sha256': source_hash(),
        'input_sha256': {str(path.resolve().relative_to(ROOT)): digest(path) for path in inputs},
    }
    output = Path(config['roster_output'])
    if output.exists() and json.loads(output.read_text()) != artifact:
        raise ValueError('Frozen R24 roster changed')
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': artifact['status'], 'tasks': len(tasks),
                      'by_environment': artifact['by_environment'],
                      'families': len(set((t['environment'], t['family']) for t in tasks))}))


if __name__ == '__main__':
    main()
