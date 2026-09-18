from __future__ import annotations

from dataclasses import dataclass
import random

from .models import SkillNode, Task


DEFECT_ALIASES = (
    "skip_validation",
    "trust_unverified_output",
    "bypass_guard_check",
    "commit_before_validation",
    "accept_without_verification",
)


@dataclass(frozen=True)
class BenchmarkConfig:
    depth: int = 4
    branching_factor: int = 3
    propagation_probability: float = 0.65
    missing_edge_rate: float = 0.0
    seed: int = 0


@dataclass(frozen=True)
class Scenario:
    nodes: dict[str, SkillNode]
    tasks: tuple[Task, ...]
    source_id: str

    def children(self, observed: bool = True) -> dict[str, list[str]]:
        result = {node_id: [] for node_id in self.nodes}
        for node in self.nodes.values():
            parents = node.observed_parents if observed else node.parents
            for parent in parents:
                result.setdefault(parent, []).append(node.node_id)
        return result

    def descendants(self, source_id: str, observed: bool = True) -> set[str]:
        children = self.children(observed=observed)
        found: set[str] = set()
        stack = list(children.get(source_id, []))
        while stack:
            node_id = stack.pop()
            if node_id in found:
                continue
            found.add(node_id)
            stack.extend(children.get(node_id, []))
        return found


def _clean_steps(capability_id: str) -> tuple[str, ...]:
    return (
        f"prepare_{capability_id}",
        f"transform_{capability_id}",
        f"validate_{capability_id}",
        f"commit_{capability_id}",
        f"verify_{capability_id}",
    )


def _contaminate(
    clean_steps: tuple[str, ...], alias: str
) -> tuple[str, ...]:
    steps = list(clean_steps)
    steps[2] = alias
    if alias == "commit_before_validation":
        steps[2], steps[3] = steps[3], steps[2]
    return tuple(steps)


def generate_scenario(config: BenchmarkConfig) -> Scenario:
    """Generate a branching lineage with known but partially observed causality."""

    rng = random.Random(config.seed)
    nodes: dict[str, SkillNode] = {}
    source_id = "skill_shared_validate_r0_bad"
    source_steps = _clean_steps("shared")
    nodes[source_id] = SkillNode(
        node_id=source_id,
        capability_id="shared",
        round_index=0,
        parents=(),
        observed_parents=(),
        edge_weights={},
        clean_steps=source_steps,
        current_steps=_contaminate(source_steps, DEFECT_ALIASES[0]),
        source_defects=frozenset({source_id}),
        probe_signal=min(1.0, max(0.0, rng.betavariate(7, 2))),
        has_prior_version=True,
    )

    frontier = [source_id]
    task_index = 0
    tasks: list[Task] = [
        Task("task_source", "shared", source_id, difficulty=0.75)
    ]

    background_source_id = "skill_background_shared"
    nodes[background_source_id] = SkillNode(
        node_id=background_source_id,
        capability_id="background_shared",
        round_index=0,
        parents=(),
        observed_parents=(),
        edge_weights={},
        clean_steps=_clean_steps("background_shared"),
        current_steps=_clean_steps("background_shared"),
        probe_signal=rng.betavariate(2, 7),
        has_prior_version=True,
    )
    tasks.append(
        Task(
            "task_background_source",
            "background_shared",
            background_source_id,
            difficulty=0.6,
        )
    )

    for round_index in range(1, config.depth + 1):
        next_frontier: list[str] = []
        for parent_index, primary_parent in enumerate(frontier):
            for branch_index in range(config.branching_factor):
                capability_id = f"r{round_index}_p{parent_index}_b{branch_index}"
                node_id = f"skill_{capability_id}"
                clean_steps = _clean_steps(capability_id)

                # Every node is structurally descended from the source path, but
                # only a subset copies its defective reasoning.
                primary = nodes[primary_parent]
                edge_weight = rng.uniform(0.25, 0.98)
                inherits = primary.contaminated and (
                    rng.random()
                    < config.propagation_probability * (0.55 + 0.55 * edge_weight)
                )
                defect_sources = primary.source_defects if inherits else frozenset()
                current_steps = clean_steps
                if inherits:
                    alias_index = min(round_index, len(DEFECT_ALIASES) - 1)
                    if rng.random() < 0.35:
                        alias_index = rng.randrange(len(DEFECT_ALIASES))
                    current_steps = _contaminate(
                        clean_steps, DEFECT_ALIASES[alias_index]
                    )

                parents = (primary_parent,)
                observed_parents = (
                    () if rng.random() < config.missing_edge_rate else parents
                )
                if inherits:
                    probe_signal = rng.betavariate(6, 2)
                else:
                    probe_signal = rng.betavariate(2, 7)

                nodes[node_id] = SkillNode(
                    node_id=node_id,
                    capability_id=capability_id,
                    round_index=round_index,
                    parents=parents,
                    observed_parents=observed_parents,
                    edge_weights={primary_parent: edge_weight},
                    clean_steps=clean_steps,
                    current_steps=current_steps,
                    source_defects=frozenset(defect_sources),
                    probe_signal=probe_signal,
                    has_prior_version=rng.random() < 0.6,
                )
                tasks.append(
                    Task(
                        task_id=f"task_{task_index:05d}",
                        capability_id=capability_id,
                        target_node_id=node_id,
                        difficulty=rng.uniform(0.35, 0.95),
                    )
                )

                # A same-scale, independent clean capability controls for the
                # utility retained outside the suspect lineage.
                background_id = f"skill_background_{capability_id}"
                background_capability = f"background_{capability_id}"
                background_steps = _clean_steps(background_capability)
                nodes[background_id] = SkillNode(
                    node_id=background_id,
                    capability_id=background_capability,
                    round_index=round_index,
                    parents=(),
                    observed_parents=(),
                    edge_weights={},
                    clean_steps=background_steps,
                    current_steps=background_steps,
                    probe_signal=rng.betavariate(2, 7),
                    has_prior_version=rng.random() < 0.6,
                )
                tasks.append(
                    Task(
                        task_id=f"task_background_{task_index:05d}",
                        capability_id=background_capability,
                        target_node_id=background_id,
                        difficulty=rng.uniform(0.35, 0.95),
                    )
                )
                task_index += 1
                next_frontier.append(node_id)
        frontier = next_frontier

    return Scenario(nodes=nodes, tasks=tuple(tasks), source_id=source_id)
