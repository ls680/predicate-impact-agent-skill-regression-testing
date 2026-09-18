from __future__ import annotations

from dataclasses import asdict, dataclass

from .benchmark import Scenario
from .recovery import RecoveryResult


@dataclass(frozen=True)
class Metrics:
    task_utility: float
    clean_library_utility: float
    contaminated_library_utility: float
    recovery_ratio: float
    impact_precision: float
    impact_recall: float
    impact_f1: float
    collateral_loss: float
    active_fraction: float
    selected_count: int
    affected_count: int
    counterfactual_replays: int
    runtime_ms: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _utility(
    scenario: Scenario,
    states: dict[str, str],
    *,
    base_success: float,
    clean_skill_success: float,
    contaminated_skill_success: float,
) -> float:
    total_weight = 0.0
    weighted_score = 0.0
    for task in scenario.tasks:
        weight = 0.5 + task.difficulty
        state = states[task.target_node_id]
        if state == "clean":
            probability = clean_skill_success
        elif state == "contaminated":
            probability = contaminated_skill_success
        else:
            probability = base_success * (1.15 - 0.5 * task.difficulty)
        weighted_score += weight * probability
        total_weight += weight
    return weighted_score / total_weight


def evaluate(
    scenario: Scenario,
    result: RecoveryResult,
    *,
    base_success: float,
    clean_skill_success: float,
    contaminated_skill_success: float,
) -> Metrics:
    clean_states = {node_id: "clean" for node_id in scenario.nodes}
    contaminated_states = {
        node_id: ("contaminated" if node.contaminated else "clean")
        for node_id, node in scenario.nodes.items()
    }
    clean_utility = _utility(
        scenario,
        clean_states,
        base_success=base_success,
        clean_skill_success=clean_skill_success,
        contaminated_skill_success=contaminated_skill_success,
    )
    contaminated_utility = _utility(
        scenario,
        contaminated_states,
        base_success=base_success,
        clean_skill_success=clean_skill_success,
        contaminated_skill_success=contaminated_skill_success,
    )
    utility = _utility(
        scenario,
        result.states,
        base_success=base_success,
        clean_skill_success=clean_skill_success,
        contaminated_skill_success=contaminated_skill_success,
    )
    denominator = clean_utility - contaminated_utility
    recovery_ratio = (
        (utility - contaminated_utility) / denominator if denominator > 0 else 0.0
    )

    affected = {
        node_id for node_id, node in scenario.nodes.items() if node.contaminated
    }
    true_positive = len(result.selected & affected)
    precision = true_positive / len(result.selected) if result.selected else 0.0
    recall = true_positive / len(affected) if affected else 1.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision + recall > 0
        else 0.0
    )

    unaffected = set(scenario.nodes) - affected
    collateral = sum(
        1 for node_id in unaffected if result.states[node_id] != "clean"
    ) / max(1, len(unaffected))
    active = sum(state != "removed" for state in result.states.values())

    return Metrics(
        task_utility=utility,
        clean_library_utility=clean_utility,
        contaminated_library_utility=contaminated_utility,
        recovery_ratio=recovery_ratio,
        impact_precision=precision,
        impact_recall=recall,
        impact_f1=f1,
        collateral_loss=collateral,
        active_fraction=active / len(result.states),
        selected_count=len(result.selected),
        affected_count=len(affected),
        counterfactual_replays=result.counterfactual_replays,
        runtime_ms=result.runtime_ms,
    )

