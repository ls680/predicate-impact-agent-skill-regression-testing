from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from atoms import PredicateDeletion, action_atom, trace_atoms


def test_scienceworld_atoms_normalize_aliases_and_instances():
    assert action_atom('scienceworld', 'focus on soap in inventory') == ('focus_object', 'soap')
    assert action_atom('scienceworld', 'activate stove 2') == ('activate_device', 'stove')
    assert action_atom('scienceworld', 'move cup to green box') == ('box_destination', 'green box')


def test_alfworld_atoms_preserve_semantic_argument_classes():
    assert action_atom('alfworld', 'take butter knife 2 from drawer 1') == ('take_object', 'butter knife')
    assert action_atom('alfworld', 'heat apple 1 with microwave 1') == ('transform_device', 'microwave')
    assert action_atom('alfworld', 'move apple 1 to diningtable 2') == ('place_destination', 'diningtable')


def test_predicate_deletion_only_changes_first_matching_action():
    spec = {'environment': 'alfworld', 'predicate_kind': 'open_target',
            'predicate_value': 'drawer'}
    mutation = PredicateDeletion(spec)
    assert mutation.transform('open cabinet 1')[0] == 'open cabinet 1'
    assert mutation.transform('open drawer 2')[0] is None
    assert mutation.transform('open drawer 3')[0] == 'open drawer 3'
    assert mutation.applied


def test_trace_atoms_are_binary_coverage_not_frequency():
    actions = ['open drawer 1', 'close drawer 1', 'open drawer 2']
    assert trace_atoms('alfworld', actions) == {('open_target', 'drawer')}
