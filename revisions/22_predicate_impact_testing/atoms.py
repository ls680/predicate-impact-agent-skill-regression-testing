"""Fixed action-to-predicate parser for sparse skill-update impact analysis."""
from __future__ import annotations

import re


ALLOWED_KINDS = {
    'scienceworld': ('focus_object', 'activate_device', 'pickup_object', 'box_destination'),
    'alfworld': ('take_object', 'place_destination', 'transform_device', 'open_target', 'use_device'),
}


def normalize_entity(value):
    value = value.replace(' in inventory', '').strip().lower()
    return re.sub(r'\s+\d+$', '', value)


def action_atom(environment, action):
    action = action.strip().lower()
    if environment == 'scienceworld':
        if action.startswith('focus on '):
            return 'focus_object', normalize_entity(action[len('focus on '):])
        if action.startswith('activate '):
            return 'activate_device', normalize_entity(action[len('activate '):])
        if action.startswith('pick up '):
            value = action[len('pick up '):].split(' from ', 1)[0]
            return 'pickup_object', normalize_entity(value)
        match = re.match(r'^move .+ to ([a-z]+ box)$', action)
        if match:
            return 'box_destination', normalize_entity(match.group(1))
    elif environment == 'alfworld':
        if action.startswith('take ') and ' from ' in action:
            return 'take_object', normalize_entity(action[5:].split(' from ', 1)[0])
        if action.startswith('move ') and ' to ' in action:
            return 'place_destination', normalize_entity(action.rsplit(' to ', 1)[1])
        match = re.match(r'^(clean|heat|cool) .+ with (.+)$', action)
        if match:
            return 'transform_device', normalize_entity(match.group(2))
        if action.startswith('open '):
            return 'open_target', normalize_entity(action[5:])
        if action.startswith('use '):
            return 'use_device', normalize_entity(action[4:])
    else:
        raise ValueError('Unsupported environment')
    return None


def trace_atoms(environment, actions):
    return {atom for action in actions if (atom := action_atom(environment, action)) is not None}


def matches(environment, action, kind, value):
    return action_atom(environment, action) == (kind, value)


class PredicateDeletion:
    def __init__(self, spec):
        self.spec, self.applied = spec, False

    def transform(self, action):
        if not self.applied and matches(self.spec['environment'], action,
                                        self.spec['predicate_kind'], self.spec['predicate_value']):
            self.applied = True
            return None, True, {'operator': 'delete_matching_predicate_action',
                                'original': action}
        return action, False, None
