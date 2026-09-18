from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from analyze import corrupt_coverage, quantile


def test_coverage_corruption_extremes_and_determinism():
    spec = {'spec_id': 's', 'support_task_ids': ['a']}
    family = [{'task_id': 'a'}, {'task_id': 'b'}]
    assert corrupt_coverage(spec, family, 0, 0, 7) == {'a'}
    assert corrupt_coverage(spec, family, 1, 1, 7) == {'b'}
    assert corrupt_coverage(spec, family, .2, .3, 9) == corrupt_coverage(
        spec, list(reversed(family)), .2, .3, 9)
    assert quantile([0, 1], .5) == .5
