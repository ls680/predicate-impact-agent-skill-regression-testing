from __future__ import annotations

from dataclasses import dataclass
import math
import random
import time

from .benchmark import Scenario


@dataclass(frozen=True)
class RecoveryResult:
    method: str
    selected: frozenset[str]
    states: dict[str, str]
    runtime_ms: float
    counterfactual_replays: int = 0


def _token_set(steps: tuple[str, ...]) -> set[str]:
    return {step.lower().replace("-", "_") for step in steps}


def _semantic_candidates(scenario: Scenario, threshold: float = 0.10) -> set[str]:
    source_tokens = _token_set(scenario.nodes[scenario.source_id].current_steps)
    candidates = {scenario.source_id}
    for node_id, node in scenario.nodes.items():
        if node_id == scenario.source_id:
            continue
        tokens = _token_set(node.current_steps)
        union = source_tokens | tokens
        score = len(source_tokens & tokens) / len(union) if union else 0.0
        if score >= threshold:
            candidates.add(node_id)
    return candidates


def _path_influence(scenario: Scenario) -> dict[str, float]:
    """Maximum product influence over observed source-to-node paths."""

    scores = {node_id: 0.0 for node_id in scenario.nodes}
    scores[scenario.source_id] = 1.0
    ordered = sorted(scenario.nodes.values(), key=lambda node: node.round_index)
    for node in ordered:
        if node.node_id == scenario.source_id:
            continue
        best = 0.0
        for parent in node.observed_parents:
            best = max(best, scores.get(parent, 0.0) * node.edge_weights[parent])
        scores[node.node_id] = best
    return scores


def _skilllineage_candidates(
    scenario: Scenario, threshold: float
) -> tuple[set[str], int]:
    influence = _path_influence(scenario)
    selected = {scenario.source_id}
    replays = 0
    for node_id in scenario.descendants(scenario.source_id, observed=True):
        node = scenario.nodes[node_id]
        # The probe approximates the factual-versus-counterfactual verifier
        # delta; path influence is a screening prior, not proof of causality.
        score = 0.45 * math.sqrt(influence[node_id]) + 0.55 * node.probe_signal
        if score >= threshold:
            selected.add(node_id)
            replays += 1
    return selected, replays


def recover(
    scenario: Scenario,
    method: str,
    *,
    seed: int,
    threshold: float = 0.55,
    repair_success: float = 0.92,
    false_positive_damage: float = 0.15,
) -> RecoveryResult:
    """Apply one post-hoc recovery policy to a contaminated scenario."""

    started = time.perf_counter()
    rng = random.Random(seed + 10_000)
    true_affected = {
        node_id for node_id, node in scenario.nodes.items() if node.contaminated
    }
    counterfactual_replays = 0

    if method == "none":
        selected: set[str] = set()
    elif method == "source_only":
        selected = {scenario.source_id}
    elif method == "semantic":
        selected = _semantic_candidates(scenario)
    elif method == "full_lineage":
        selected = {scenario.source_id} | scenario.descendants(
            scenario.source_id, observed=True
        )
    elif method == "full_lineage_replay":
        selected = {scenario.source_id} | scenario.descendants(
            scenario.source_id, observed=True
        )
        counterfactual_replays = max(0, len(selected) - 1)
    elif method == "skilllineage":
        selected, counterfactual_replays = _skilllineage_candidates(
            scenario, threshold
        )
    elif method == "oracle_selective":
        selected = set(true_affected)
    else:
        raise ValueError(f"Unknown recovery method: {method}")

    states: dict[str, str] = {}
    for node_id, node in scenario.nodes.items():
        if node_id not in selected:
            states[node_id] = "contaminated" if node.contaminated else "clean"
            continue

        if method in {"source_only", "semantic", "full_lineage"}:
            states[node_id] = "removed"
        elif method == "oracle_selective":
            states[node_id] = "clean"
        else:
            if node.contaminated:
                states[node_id] = (
                    "clean" if rng.random() < repair_success else "removed"
                )
            else:
                if method == "full_lineage_replay":
                    states[node_id] = "clean"
                    continue
                states[node_id] = (
                    "removed"
                    if rng.random() < false_positive_damage
                    else "clean"
                )

    runtime_ms = (time.perf_counter() - started) * 1_000
    return RecoveryResult(
        method=method,
        selected=frozenset(selected),
        states=states,
        runtime_ms=runtime_ms,
        counterfactual_replays=counterfactual_replays,
    )
