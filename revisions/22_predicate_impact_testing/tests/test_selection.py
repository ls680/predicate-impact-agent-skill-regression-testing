from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate import random_probability, upper_tail
from selection_methods import select_order


TASKS = [
    {'task_id': 'a', 'environment': 'alfworld', 'family': 'place', 'task_description': 'put apple',
     'healthy_steps': 6, 'actions': ['take apple 1 from desk 1'], 'atoms': [('take_object', 'apple')]},
    {'task_id': 'b', 'environment': 'alfworld', 'family': 'place', 'task_description': 'put mug',
     'healthy_steps': 2, 'actions': ['take mug 1 from desk 1'], 'atoms': [('take_object', 'mug')]},
    {'task_id': 'c', 'environment': 'alfworld', 'family': 'look', 'task_description': 'look',
     'healthy_steps': 1, 'actions': ['look'], 'atoms': []},
]
SPEC = {'spec_id': 's', 'environment': 'alfworld', 'family': 'place',
        'predicate_kind': 'take_object', 'predicate_value': 'apple',
        'support_task_ids': ['a']}


def test_predicate_impact_beats_shorter_uncovered_family_task_without_outcomes():
    assert [t['task_id'] for t in select_order('predicate_impact', TASKS, SPEC)] == ['a', 'b', 'c']


def test_family_random_retains_modified_skill_association():
    order = select_order('skill_family_random', TASKS, SPEC, seed=2)
    assert all(task['family'] == 'place' for task in order[:2])


def test_exact_conditional_probability():
    assert abs(random_probability(5, 1, 3) - .6) < 1e-12
    assert abs(upper_tail([.5, .5], 2) - .25) < 1e-12
