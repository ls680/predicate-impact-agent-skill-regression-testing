from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate import metric, random_probability, upper_tail


def test_exact_probability_helpers():
    assert abs(random_probability(8, 1, 3) - .375) < 1e-12
    assert abs(upper_tail([.5, .5], 2) - .25) < 1e-12


def test_metric_reports_absolute_lift():
    specs = [{'spec_id': 's', 'environment': 'e', 'family': 'f'}]
    tasks = {'e': [{'task_id': str(i), 'family': 'f'} for i in range(8)]}
    killed = {'s': {str(i): i == 0 for i in range(8)}}
    rows = {'s': {'task_budget_curve': {'3': {'detected': True}}}}
    result = metric(specs, tasks, killed, rows, 3)
    assert result['detection_rate'] == 1.0
    assert abs(result['absolute_lift'] - .625) < 1e-12
