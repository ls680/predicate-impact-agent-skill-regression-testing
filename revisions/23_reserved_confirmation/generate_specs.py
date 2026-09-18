"""Apply the unchanged R22 predicate-specification rule to reserved healthy traces."""
from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

REVISION = Path(__file__).resolve().parent
ROOT = REVISION.parents[1]
R22 = ROOT / 'revisions/22_predicate_impact_testing'
sys.path.insert(0, str(ROOT / 'revisions/07_executor_search'))
sys.path.insert(0, str(R22))
from run_preflight import digest, rows
from skilllineage.provenance import source_hash

module_spec = importlib.util.spec_from_file_location('r22_generate_specs', R22 / 'generate_specs.py')
r22_generate = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(r22_generate)
build_specs = r22_generate.build_specs


def main():
    config = json.loads((REVISION / 'config.json').read_text())
    development = json.loads((R22 / 'config.json').read_text())
    keys = ('minimum_family_support', 'maximum_family_support_fraction',
            'maximum_singleton_specs_per_family_and_kind',
            'maximum_multitask_specs_per_family_and_kind')
    if any(config[key] != development[key] for key in keys):
        raise ValueError('Reserved predicate generation differs from R22')
    oracle = Path(config['oracle_output'])
    if (not (oracle / 'completion.json').exists() or
            json.loads((oracle / 'completion.json').read_text()).get('status') != 'completed'):
        raise ValueError('Reserved healthy collection is incomplete')
    all_records = rows(oracle / 'trajectories.jsonl')
    records = {environment: [r for r in all_records if r['environment'] == environment]
               for environment in config['expected_tasks']}
    specs = build_specs(config, records)
    inputs = [REVISION / 'config.json', REVISION / 'generate_specs.py', REVISION / 'PROTOCOL.md',
              R22 / 'generate_specs.py', R22 / 'atoms.py', R22 / 'config.json',
              Path(config['roster_output']), oracle / 'run_spec.json',
              oracle / 'completion.json', oracle / 'trajectories.jsonl']
    artifact = {
        'status': 'reserved_predicate_specs_frozen_before_mutation_outcomes',
        'generation_reads_mutation_outcomes': False,
        'generation_rule_identical_to_r22': True, 'config': config,
        'specs': specs, 'spec_count': len(specs),
        'by_environment': dict(Counter(spec['environment'] for spec in specs)),
        'original_source_sha256': source_hash(),
        'input_sha256': {str(p.resolve().relative_to(ROOT)): digest(p) for p in inputs},
    }
    output = Path(config['spec_output'])
    if output.exists() and json.loads(output.read_text()) != artifact:
        raise ValueError('Frozen reserved predicate specs changed')
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'status': artifact['status'], 'specs': len(specs),
                      'native_replays': sum(s['support_count'] for s in specs),
                      'by_environment': artifact['by_environment']}))


if __name__ == '__main__':
    main()
