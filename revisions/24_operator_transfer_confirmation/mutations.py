"""Outcome-blind predicate mutation operators for transfer confirmation."""
from __future__ import annotations

from atoms import action_atom, matches

OPERATORS = ('delete_action', 'same_kind_argument_substitution', 'adjacent_order_swap')


def first_match(record, spec):
    return next((index for index, action in enumerate(record['executed_actions'])
                 if matches(spec['environment'], action, spec['predicate_kind'],
                            spec['predicate_value'])), None)


def substitution(record, spec, index=None):
    index = first_match(record, spec) if index is None else index
    if index is None or index >= len(record['turns']):
        return None
    original = record['executed_actions'][index]
    candidates = []
    for action in record['turns'][index]['admissible_actions']:
        atom = action_atom(spec['environment'], action)
        if atom and atom[0] == spec['predicate_kind'] and action != original:
            candidates.append(action)
    return sorted(set(candidates))[0] if candidates else None


def applicable(record, spec, operator):
    index = first_match(record, spec)
    if index is None:
        return False
    if operator == 'delete_action':
        return True
    if operator == 'same_kind_argument_substitution':
        return substitution(record, spec, index) is not None
    if operator == 'adjacent_order_swap':
        return index + 1 < len(record['executed_actions'])
    raise ValueError(f'Unknown operator: {operator}')


def mutate_program(record, spec):
    operator = spec['operator']
    if operator not in OPERATORS:
        raise ValueError(f'Unknown operator: {operator}')
    index = first_match(record, spec)
    if index is None or not applicable(record, spec, operator):
        raise ValueError('Mutation is not applicable to this healthy trace')
    actions = list(record['executed_actions'])
    original = actions[index]
    if operator == 'delete_action':
        actions[index] = None
        changed = {'program_index': index, 'operator': operator,
                   'original_action': original, 'mutated_action': None}
    elif operator == 'same_kind_argument_substitution':
        replacement = substitution(record, spec, index)
        actions[index] = replacement
        changed = {'program_index': index, 'operator': operator,
                   'original_action': original, 'mutated_action': replacement}
    else:
        following = actions[index + 1]
        actions[index], actions[index + 1] = following, original
        changed = {'program_index': index, 'operator': operator,
                   'original_action': original, 'mutated_action': following,
                   'swapped_with_index': index + 1, 'swapped_action': following}
    return actions, changed
