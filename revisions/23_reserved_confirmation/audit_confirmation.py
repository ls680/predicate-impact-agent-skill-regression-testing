"""Audit hashes and exact authorized roster for a reserved confirmation run."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def resolve(path, root):
    candidate = Path(path)
    if candidate.is_absolute():
        marker = '/papers/01_skilllineage/'
        candidate = root / str(candidate).split(marker, 1)[1] if marker in str(candidate) else candidate
    else:
        candidate = root / candidate
    candidate = candidate.resolve()
    candidate.relative_to(root)
    return candidate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    spec = json.loads((args.run / 'run_spec.json').read_text())
    config = spec['config']
    roster = json.loads(Path(config['roster_output']).read_text())
    authorized = {(task['environment'], task['task_id']) for task in roster['tasks']}
    executed = {(task['environment'], task['task_id']) for task in spec['tasks']}
    if not executed <= authorized:
        raise ValueError('Confirmation run contains task outside frozen reserved roster')
    for path, expected in spec['revision_inputs'].items():
        if hashlib.sha256(resolve(path, root).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Confirmation input mismatch: {path}')
    from skilllineage.provenance import source_hash
    if source_hash() != spec['original_source_sha256']:
        raise ValueError('Original implementation changed')
    result = {'all_input_hashes_match': True, 'original_source_unchanged': True,
              'all_accessed_tasks_in_frozen_reserved_roster': True,
              'authorized_roster_tasks': len(authorized), 'run_tasks': len(executed),
              'run': str(args.run)}
    (args.run / 'confirmation_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
