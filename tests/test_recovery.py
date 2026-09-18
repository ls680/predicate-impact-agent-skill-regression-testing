from skilllineage.benchmark import BenchmarkConfig, generate_scenario
from skilllineage.metrics import evaluate
from skilllineage.recovery import recover


def _metrics(method: str):
    scenario = generate_scenario(
        BenchmarkConfig(
            depth=5,
            branching_factor=3,
            propagation_probability=0.7,
            seed=3,
        )
    )
    result = recover(scenario, method, seed=3)
    return scenario, result, evaluate(
        scenario,
        result,
        base_success=0.32,
        clean_skill_success=0.86,
        contaminated_skill_success=0.14,
    )


def test_source_only_leaves_affected_descendants() -> None:
    scenario, result, _ = _metrics("source_only")
    assert result.states[scenario.source_id] == "removed"
    assert any(
        result.states[node_id] == "contaminated"
        for node_id in scenario.descendants(scenario.source_id, observed=False)
    )


def test_full_lineage_has_collateral_loss() -> None:
    _, _, metrics = _metrics("full_lineage")
    assert metrics.collateral_loss > 0
    assert metrics.active_fraction < 1


def test_full_lineage_replay_is_a_stronger_but_costlier_baseline() -> None:
    _, result, metrics = _metrics("full_lineage_replay")
    assert result.counterfactual_replays > 0
    assert metrics.task_utility > metrics.contaminated_library_utility


def test_oracle_recovers_clean_utility() -> None:
    _, _, metrics = _metrics("oracle_selective")
    assert metrics.task_utility == metrics.clean_library_utility
    assert metrics.impact_precision == 1
    assert metrics.impact_recall == 1
