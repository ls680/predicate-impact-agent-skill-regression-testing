from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from freeze_roster import select


def test_second_roster_excludes_first_and_is_deterministic():
    tasks = [{'environment': 'e', 'family': 'f', 'task_id': str(i),
              'compatible_with_original_scope': True} for i in range(5)]
    previous = {'tasks': [tasks[0]]}
    config = {'selection_counts': {'e': {'f': 3}}, 'expected_tasks': {'e': 3},
              'selection_seed': 'fixed'}
    chosen = select({'reserved_test_pool': tasks}, previous, config)
    assert len(chosen) == 3
    assert tasks[0] not in chosen
    assert chosen == select({'reserved_test_pool': list(reversed(tasks))}, previous, config)
