"""Freeze a content-blind balanced roster from the sealed reserved inventory."""
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


def select(snapshot, config):
    tasks = snapshot['reserved_test_pool']
    selected = []
    for environment, per_family in config['tasks_per_family'].items():
        families = sorted({task['family'] for task in tasks if task['environment'] == environment})
        for family in families:
            candidates = [task for task in tasks if task['environment'] == environment
                          and task['family'] == family and task['compatible_with_original_scope']]
            chosen = sorted(candidates, key=lambda task: rank(task, config['selection_seed']))[:per_family]
            if len(chosen) != per_family:
                raise ValueError(f'Insufficient reserved tasks for {environment}/{family}')
            selected.extend(chosen)
    for environment, expected in config['expected_tasks'].items():
        if sum(task['environment'] == environment for task in selected) != expected:
            raise ValueError('Frozen environment sample count mismatch')
    keys = [(task['environment'], task['task_id']) for task in selected]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate task in reserved roster')
    return selected


def main():
    config_path = REVISION / 'config.json'
    config = json.loads(config_path.read_text())
    gate_path = Path(config['development_gate'])
    gate = json.loads(gate_path.read_text())
    if not gate['development_gate_passed'] or not gate['advance_to_reserved_confirmation']:
        raise ValueError('R22 did not authorize reserved confirmation')
    snapshot_path = Path(config['exposure_snapshot'])
    snapshot = json.loads(snapshot_path.read_text())
    tasks = select(snapshot, config)
    inputs = [config_path, REVISION / 'freeze_roster.py', REVISION / 'PROTOCOL.md',
              gate_path, gate_path.parent / 'run_spec.json', gate_path.parent / 'source_audit.json',
              snapshot_path]
    artifact = {
        'status': 'roster_frozen_before_task_content_or_oracle_access',
        'selection_uses_only': ['environment', 'family', 'task_id', 'compatible_with_original_scope'],
        'selection_seed': config['selection_seed'], 'tasks': tasks,
        'task_count': len(tasks), 'by_environment': dict(Counter(t['environment'] for t in tasks)),
        'original_source_sha256': source_hash(),
        'input_sha256': {str(p.resolve().relative_to(ROOT)): digest(p) for p in inputs},
    }
    output = Path(config['roster_output'])
    if output.exists() and json.loads(output.read_text()) != artifact:
        raise ValueError('Frozen reserved roster changed')
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': artifact['status'], 'tasks': len(tasks),
                      'by_environment': artifact['by_environment'],
                      'families': len(set((t['environment'], t['family']) for t in tasks))}))


if __name__ == '__main__':
    main()
