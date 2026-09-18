from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from run_mutations import initial_signature


def test_initial_signature_requires_auditable_start():
    record = {'task_id': 'x', 'observations': ['room'], 'task_description': 'goal',
              'turns': [{'admissible_actions': ['look']}]}
    assert initial_signature(record) == initial_signature(record)
    try:
        initial_signature({**record, 'turns': []})
    except ValueError:
        pass
    else:
        raise AssertionError('Missing initial actions must fail')
