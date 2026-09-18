from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'revisions/22_predicate_impact_testing'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mutations import applicable, mutate_program


def record():
    return {'executed_actions': ['take apple 1 from table 1', 'move apple 1 to bowl 1'],
            'turns': [
                {'admissible_actions': ['take apple 1 from table 1',
                                        'take pear 1 from table 1']},
                {'admissible_actions': ['move apple 1 to bowl 1',
                                        'move apple 1 to plate 1']} ]}


def spec(operator):
    return {'environment': 'alfworld', 'predicate_kind': 'take_object',
            'predicate_value': 'apple', 'operator': operator}


def test_all_three_operators_are_outcome_blind_and_distinct():
    row = record()
    for operator in ('delete_action', 'same_kind_argument_substitution',
                     'adjacent_order_swap'):
        current = spec(operator)
        assert applicable(row, current, operator)
        actions, event = mutate_program(row, current)
        assert actions != row['executed_actions']
        assert event['operator'] == operator
