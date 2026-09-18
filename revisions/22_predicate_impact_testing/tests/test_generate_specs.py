from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from generate_specs import build_specs


def record(task, actions):
    return {'task_id': task, 'family': 'f', 'success': True, 'error': None,
            'executed_actions': actions}


def test_generation_uses_coverage_bounds_and_deterministic_cap():
    records = {'alfworld': [
        record('a', ['take apple 1 from desk 1']),
        record('b', ['take apple 2 from table 1']),
        record('c', ['take pear 1 from desk 1']),
        record('d', ['take mug 1 from desk 1']),
    ]}
    config = {'minimum_family_support': 1, 'maximum_family_support_fraction': .5,
              'maximum_singleton_specs_per_family_and_kind': 1,
              'maximum_multitask_specs_per_family_and_kind': 1}
    specs = build_specs(config, records)
    assert [(s['predicate_value'], s['support_count']) for s in specs] == [
        ('mug', 1), ('apple', 2)]
