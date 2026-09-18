from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from freeze_roster import rank, select


def test_roster_is_balanced_and_content_blind():
    tasks = [{'environment': env, 'family': family, 'task_id': f'{env}-{family}-{i}',
              'compatible_with_original_scope': True, 'official_split': 'test', 'variation': i}
             for env in ('alfworld', 'scienceworld') for family in ('a', 'b') for i in range(4)]
    config = {'tasks_per_family': {'alfworld': 2, 'scienceworld': 2},
              'expected_tasks': {'alfworld': 4, 'scienceworld': 4}, 'selection_seed': 'fixed'}
    chosen = select({'reserved_test_pool': tasks}, config)
    assert len(chosen) == 8
    assert [x['task_id'] for x in chosen] == [x['task_id'] for x in select(
        {'reserved_test_pool': list(reversed(tasks))}, config)]
    assert rank(tasks[0], 'fixed') == rank(tasks[0], 'fixed')
