from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def local_input(path, root):
    candidate = Path(path)
    if candidate.is_absolute():
        marker = '/papers/01_skilllineage/'
        if marker in str(candidate):
            candidate = root / str(candidate).split(marker, 1)[1]
        else:
            candidate = root / candidate.relative_to(root)
    else:
        candidate = root / candidate
    candidate = candidate.resolve()
    candidate.relative_to(root.resolve())
    return candidate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    args = parser.parse_args()
    root = Path.cwd().resolve()
    spec = json.loads((args.run / 'run_spec.json').read_text())
    from skilllineage.provenance import source_hash
    if source_hash() != spec['original_source_sha256']:
        raise ValueError('Frozen original implementation changed')
    inputs = spec.get('revision_inputs', spec.get('inputs'))
    if not inputs:
        raise ValueError('No recorded revision input hashes')
    for path, expected in inputs.items():
        local = local_input(path, root)
        if hashlib.sha256(local.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Input/source mismatch: {path}')
    exposure_path = spec['config'].get('exposure_snapshot', 'research/validation/exposure_snapshot_20260905.json')
    exposure = json.loads(Path(exposure_path).read_text())
    reserved = {(row['environment'], row['task_id']) for row in exposure['reserved_test_pool']}
    if 'tasks' in spec:
        tasks = {(row['environment'], row['task_id']) for row in spec['tasks']}
    else:
        checkpoints = json.loads(Path(spec['config']['checkpoints']).read_text())
        tasks = {('alfworld', row['task_id']) for row in checkpoints['records']}
    if reserved & tasks:
        raise ValueError('Reserved independent task used in development')
    result = {'all_input_hashes_match': True, 'original_source_unchanged': True,
              'no_reserved_tests_executed': True, 'checked_revision_inputs': len(inputs),
              'run': str(args.run)}
    (args.run / 'source_audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
