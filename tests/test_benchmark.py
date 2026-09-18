from skilllineage.benchmark import BenchmarkConfig, generate_scenario


def test_scenario_has_known_and_observed_lineages() -> None:
    scenario = generate_scenario(
        BenchmarkConfig(depth=3, branching_factor=2, missing_edge_rate=0.3, seed=7)
    )
    assert scenario.source_id in scenario.nodes
    assert len(scenario.nodes) == 2 * (1 + 2 + 4 + 8)
    assert len(scenario.tasks) == len(scenario.nodes)
    assert scenario.descendants(scenario.source_id, observed=False)
    assert scenario.descendants(scenario.source_id, observed=True) <= scenario.descendants(
        scenario.source_id, observed=False
    )


def test_contamination_is_not_identical_to_structural_descent() -> None:
    scenario = generate_scenario(
        BenchmarkConfig(
            depth=4,
            branching_factor=3,
            propagation_probability=0.5,
            seed=11,
        )
    )
    descendants = scenario.descendants(scenario.source_id, observed=False)
    affected = {
        node_id for node_id, node in scenario.nodes.items() if node.contaminated
    }
    assert affected - {scenario.source_id} <= descendants
    assert descendants - affected
