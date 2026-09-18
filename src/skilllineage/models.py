from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillNode:
    """One immutable skill version in an evolution lineage."""

    node_id: str
    capability_id: str
    round_index: int
    parents: tuple[str, ...]
    observed_parents: tuple[str, ...]
    edge_weights: dict[str, float]
    clean_steps: tuple[str, ...]
    current_steps: tuple[str, ...]
    source_defects: frozenset[str] = field(default_factory=frozenset)
    probe_signal: float = 0.0
    has_prior_version: bool = False

    @property
    def contaminated(self) -> bool:
        return bool(self.source_defects)


@dataclass(frozen=True)
class Task:
    task_id: str
    capability_id: str
    target_node_id: str
    difficulty: float

