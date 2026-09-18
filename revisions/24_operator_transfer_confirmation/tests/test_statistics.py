from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'revisions/22_predicate_impact_testing'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate import random_probability, upper_tail


def test_exact_probability_helpers():
    assert abs(random_probability(8, 1, 3) - .375) < 1e-12
    assert abs(upper_tail([.5, .5], 2) - .25) < 1e-12
