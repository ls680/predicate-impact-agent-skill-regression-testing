"""Generate sparse predicate mutation specifications without reading outcomes."""
from __future__ import annotations

from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import sys

REVISION = Path(__file__).resolve().parent
ROOT = REVISION.parents[1]
sys.path.insert(0, str(ROOT / 'revisions/07_executor_search'))
from run_preflight import digest, rows
from atoms import ALLOWED_KINDS, trace_atoms
from skilllineage.provenance import source_hash


def build_specs(config, records_by_environment):
    specs = []
    for environment in sorted(records_by_environment):
        successful = [r for r in records_by_environment[environment]
                      if r['success'] and not r['error']]
        families = sorted({r['family'] for r in successful})
        for family in families:
            group = [r for r in successful if r['family'] == family]
            support = defaultdict(list)
            for record in group:
                for kind, value in trace_atoms(environment, record['executed_actions']):
                    if kind in ALLOWED_KINDS[environment]:
                        support[(kind, value)].append(record['task_id'])
            maximum = max(config['minimum_family_support'],
                          math.floor(len(group) * config['maximum_family_support_fraction']))
            by_kind = defaultdict(list)
            for (kind, value), task_ids in support.items():
                if config['minimum_family_support'] <= len(task_ids) <= maximum:
                    by_kind[kind].append((len(task_ids), value, sorted(task_ids)))
            for kind in ALLOWED_KINDS[environment]:
                ordered = sorted(by_kind[kind], key=lambda item: (item[1], item[0]))
                singletons = [item for item in ordered if item[0] == 1][
                    :config['maximum_singleton_specs_per_family_and_kind']]
                multitask = [item for item in ordered if item[0] > 1][
                    :config['maximum_multitask_specs_per_family_and_kind']]
                candidates = singletons + multitask
                for count, value, task_ids in candidates:
                    payload = f'{environment}|{family}|{kind}|{value}'
                    specs.append({
                        'spec_id': hashlib.sha256(payload.encode()).hexdigest()[:20],
                        'environment': environment, 'family': family,
                        'predicate_kind': kind, 'predicate_value': value,
                        'family_healthy_tasks': len(group), 'support_count': count,
                        'support_task_ids': task_ids,
                    })
    if len({s['spec_id'] for s in specs}) != len(specs):
        raise ValueError('Predicate specification collision')
    return specs


def main():
    config_path = REVISION / 'config.json'
    config = json.loads(config_path.read_text())
    records = {environment: rows(path + '/trajectories.jsonl')
               for environment, path in config['healthy_runs'].items()}
    for environment, group in records.items():
        if len(group) != config['expected_tasks'][environment]:
            raise ValueError('Healthy input count differs from frozen expectation')
    specs = build_specs(config, records)
    output = Path(config['spec_output'])
    inputs = [config_path, REVISION / 'generate_specs.py', REVISION / 'atoms.py',
              REVISION / 'PROTOCOL.md', Path(config['exposure_snapshot'])]
    for path in config['healthy_runs'].values():
        inputs.extend([Path(path) / name for name in
                       ('run_spec.json', 'completion.json', 'trajectories.jsonl')])
    artifact = {
        'status': config['status'], 'generation_reads_mutation_outcomes': False,
        'supersedes_nonexecuted_draft': 'predicate_specs_draft_singleton_heavy.json',
        'config': config, 'specs': specs, 'spec_count': len(specs),
        'original_source_sha256': source_hash(),
        'input_sha256': {str(p.resolve().relative_to(ROOT)): digest(p) for p in inputs},
    }
    if output.exists() and json.loads(output.read_text()) != artifact:
        raise ValueError('Frozen predicate specification artifact changed')
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + '\n')
    summary = defaultdict(int)
    for spec in specs:
        summary[(spec['environment'], spec['family'], spec['predicate_kind'])] += 1
    print(json.dumps({'specs': len(specs), 'by_environment': {
        environment: sum(s['environment'] == environment for s in specs)
        for environment in sorted(records)}, 'by_family_kind': {
        '/'.join(key): value for key, value in sorted(summary.items())}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
