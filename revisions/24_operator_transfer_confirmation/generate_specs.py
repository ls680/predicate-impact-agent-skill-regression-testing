"""Expand frozen R22 predicate specs into three outcome-blind operator classes."""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

REVISION = Path(__file__).resolve().parent
ROOT = REVISION.parents[1]
R22 = ROOT / 'revisions/22_predicate_impact_testing'
sys.path.insert(0, str(ROOT / 'revisions/07_executor_search'))
sys.path.insert(0, str(R22))
sys.path.insert(0, str(REVISION))
from run_preflight import digest, rows
from mutations import OPERATORS, applicable
from skilllineage.provenance import source_hash

module_spec = importlib.util.spec_from_file_location('r22_generate_specs', R22 / 'generate_specs.py')
r22_generate = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(r22_generate)


def main():
    config_path = REVISION / 'config.json'
    config = json.loads(config_path.read_text())
    if tuple(config['operators']) != OPERATORS:
        raise ValueError('Configured operators differ from frozen implementation')
    oracle = Path(config['oracle_output'])
    if json.loads((oracle / 'completion.json').read_text()).get('status') != 'completed':
        raise ValueError('R24 healthy collection is incomplete')
    all_records = rows(oracle / 'trajectories.jsonl')
    records = {environment: [row for row in all_records if row['environment'] == environment]
               for environment in config['expected_tasks']}
    lookup = {(row['environment'], row['task_id']): row for row in all_records}
    base_specs = r22_generate.build_specs(config, records)
    specs = []
    for base in base_specs:
        for operator in OPERATORS:
            replay = [task_id for task_id in base['support_task_ids']
                      if applicable(lookup[(base['environment'], task_id)], base, operator)]
            if not replay:
                continue
            payload = f"{base['spec_id']}|{operator}"
            specs.append({**base,
                          'base_spec_id': base['spec_id'],
                          'spec_id': hashlib.sha256(payload.encode()).hexdigest()[:20],
                          'operator': operator,
                          'replay_task_ids': replay,
                          'operator_support_count': len(replay)})
    inputs = [config_path, REVISION / 'generate_specs.py', REVISION / 'mutations.py',
              REVISION / 'PROTOCOL.md', R22 / 'generate_specs.py', R22 / 'atoms.py',
              Path(config['roster_output']), oracle / 'run_spec.json',
              oracle / 'completion.json', oracle / 'trajectories.jsonl']
    artifact = {
        'status': 'operator_specs_frozen_before_mutation_outcomes',
        'generation_reads_mutation_outcomes': False,
        'base_generation_rule_identical_to_r22': True,
        'config': config, 'base_spec_count': len(base_specs),
        'specs': specs, 'spec_count': len(specs),
        'by_operator': dict(Counter(spec['operator'] for spec in specs)),
        'by_environment': dict(Counter(spec['environment'] for spec in specs)),
        'original_source_sha256': source_hash(),
        'input_sha256': {str(path.resolve().relative_to(ROOT)): digest(path) for path in inputs},
    }
    output = Path(config['spec_output'])
    if output.exists() and json.loads(output.read_text()) != artifact:
        raise ValueError('Frozen R24 operator specs changed')
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': artifact['status'], 'base_specs': len(base_specs),
                      'operator_specs': len(specs),
                      'native_replays': sum(len(spec['replay_task_ids']) for spec in specs),
                      'by_operator': artifact['by_operator'],
                      'by_environment': artifact['by_environment']}))


if __name__ == '__main__':
    main()
