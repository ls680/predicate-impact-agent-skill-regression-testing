from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import hashlib
import json
import os
from typing import Any


def _stable_select(
    values: list[Any], count: int, seed: str, *, offset: int = 0
) -> list[Any]:
    ranked = sorted(
        values,
        key=lambda value: hashlib.sha256(
            f"{seed}:{value}".encode("utf-8")
        ).hexdigest(),
    )
    return ranked[offset : offset + count]


def _task_description(observation: str) -> str:
    marker = "Your task is to:"
    if marker in observation:
        return observation[observation.index(marker) :].strip()
    return observation.strip()


class AlfworldEpisode:
    def __init__(self, gamefile: str | Path, *, max_steps: int, expert: bool = False):
        import textworld
        import textworld.gym
        from alfworld.agents.environment.alfred_tw_env import (
            AlfredDemangler,
            AlfredExpert,
            AlfredInfos,
        )

        self.textworld = textworld
        request_infos = textworld.EnvInfos(
            won=True,
            admissible_commands=True,
            extras=["gamefile"],
        )
        wrappers: list[Any] = [AlfredDemangler(shuffle=False), AlfredInfos]
        if expert:
            wrappers.append(AlfredExpert("handcoded"))
            request_infos.extras.append("expert_plan")
        env_id = textworld.gym.register_games(
            [str(gamefile)],
            request_infos,
            batch_size=1,
            asynchronous=False,
            max_episode_steps=max_steps,
            wrappers=wrappers,
        )
        self.env = textworld.gym.make(env_id)
        self.expert = expert
        self.info: dict[str, Any] = {}

    def reset(self) -> tuple[str, str, list[str]]:
        observations, self.info = self.env.reset()
        observation = observations[0]
        actions = list(self.info["admissible_commands"][0])
        return observation, _task_description(observation), actions

    def step(self, action: str) -> tuple[str, float, bool, list[str]]:
        observations, scores, dones, self.info = self.env.step([action])
        return (
            observations[0],
            float(scores[0]),
            bool(dones[0]),
            list(self.info["admissible_commands"][0]),
        )

    def expert_action(self) -> str | None:
        plan = self.info.get("extra.expert_plan", [[]])[0]
        return str(plan[0]) if plan else None

    def close(self) -> None:
        self.env.close()


class ScienceworldSession:
    def __init__(self, *, max_steps: int):
        from scienceworld import ScienceWorldEnv

        self.env = ScienceWorldEnv("", envStepLimit=max_steps)
        self.task_description = ""
        self.last_score = 0.0

    def configure(
        self,
        task_name: str,
        variation: int,
        simplifications: str = "easy",
        *,
        generate_gold_path: bool = False,
    ) -> None:
        self.env.load(
            task_name,
            variation,
            simplifications,
            generateGoldPath=generate_gold_path,
        )

    def reset(self) -> tuple[str, str, list[str]]:
        observation, info = self.env.reset()
        self.task_description = str(info["taskDesc"])
        self.last_score = float(info.get("score", 0.0)) / 100.0
        actions = list(self.env.get_valid_action_object_combinations())
        return observation, self.task_description, actions

    def step(self, action: str) -> tuple[str, float, bool, list[str]]:
        observation, _, done, info = self.env.step(action)
        self.last_score = float(info.get("score", info.get("reward", 0.0))) / 100.0
        actions = list(self.env.get_valid_action_object_combinations())
        return observation, self.last_score, bool(done), actions

    def gold_actions(self) -> list[str]:
        return [str(action) for action in self.env.get_gold_action_sequence()]

    def close(self) -> None:
        self.env.close()


def collect_alfworld_manifest(
    data_dir: str | Path,
    families: list[str],
    *,
    demos_per_family: int,
    dev_per_family: int,
    test_per_family: int,
    test_skip_per_family: int,
    seed: int,
) -> dict[str, Any]:
    data_dir = Path(data_dir).resolve()
    groups: dict[str, dict[str, list[Path]]] = {
        split: defaultdict(list)
        for split in ("train", "valid_seen", "valid_unseen")
    }
    for split in groups:
        split_dir = data_dir / "json_2.1.1" / split
        for gamefile in sorted(split_dir.rglob("game.tw-pddl")):
            trajectory_path = gamefile.with_name("traj_data.json")
            if not trajectory_path.exists():
                continue
            trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
            family = str(trajectory.get("task_type", ""))
            if family in families and "Sliced" not in str(gamefile) and "movable" not in str(gamefile):
                groups[split][family].append(gamefile)

    result: dict[str, Any] = {
        "demos": [],
        "dev": [],
        "test": [],
        "excluded_engineering_test": [],
    }
    split_spec = (
        ("train", "demos", demos_per_family),
        ("valid_seen", "dev", dev_per_family),
        ("valid_unseen", "test", test_per_family),
    )
    for source_split, target_split, count in split_spec:
        for family in families:
            selection_seed = f"{seed}:{source_split}:{family}"
            offset = test_skip_per_family if target_split == "test" else 0
            selected = _stable_select(
                groups[source_split][family], count, selection_seed, offset=offset
            )
            if len(selected) != count:
                raise RuntimeError(
                    f"ALFWorld {source_split}/{family} has {len(selected)} selected, expected {count}"
                )
            for gamefile in selected:
                result[target_split].append(
                    {
                        "task_id": str(gamefile.relative_to(data_dir)),
                        "family": family,
                        "gamefile": str(gamefile.relative_to(data_dir)),
                    }
                )
            if target_split == "test":
                for gamefile in _stable_select(
                    groups[source_split][family], offset, selection_seed
                ):
                    result["excluded_engineering_test"].append(
                        {
                            "task_id": str(gamefile.relative_to(data_dir)),
                            "family": family,
                            "reason": "used by a pre-freeze engineering run",
                        }
                    )
    return result


def collect_alfworld_demonstrations(
    entries: list[dict[str, Any]],
    data_dir: str | Path,
    max_steps: int,
    target_per_family: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    data_dir = Path(data_dir)
    demonstrations: list[dict[str, Any]] = []
    for entry in entries:
        trajectory_path = (data_dir / entry["gamefile"]).with_name("traj_data.json")
        trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
        annotations = trajectory["turk_annotations"]["anns"][0]
        task_description = str(annotations["task_desc"])
        actions = []
        for item in trajectory["plan"]["high_pddl"]:
            discrete = item["discrete_action"]
            name = str(discrete["action"])
            args = [str(value) for value in discrete.get("args", [])]
            actions.append(f"{name}({', '.join(args)})")
        observations = [task_description] + [
            str(value) for value in annotations.get("high_descs", [])
        ]
        demonstrations.append(
            {
                **entry,
                "task_description": task_description,
                "actions": actions,
                "observations": observations,
                "evidence_source": "official ALFRED high-level successful plan",
            }
        )
    counts: dict[str, int] = defaultdict(int)
    for demonstration in demonstrations:
        counts[demonstration["family"]] += 1
    missing = {
        family: target_per_family - counts[family]
        for family in {entry["family"] for entry in entries}
        if counts[family] < target_per_family
    }
    if missing:
        raise RuntimeError(f"Not enough ALFWorld demonstrations: {missing}")
    return demonstrations, []


def collect_scienceworld_manifest(
    families: list[str],
    *,
    demos_per_family: int,
    dev_per_family: int,
    test_per_family: int,
    test_skip_per_family: int,
    seed: int,
    max_steps: int,
) -> dict[str, Any]:
    session = ScienceworldSession(max_steps=max_steps)
    result: dict[str, Any] = {
        "demos": [],
        "dev": [],
        "test": [],
        "excluded_engineering_test": [],
    }
    split_methods = {
        "demos": session.env.get_variations_train,
        "dev": session.env.get_variations_dev,
        "test": session.env.get_variations_test,
    }
    split_counts = {
        "demos": demos_per_family,
        "dev": dev_per_family,
        "test": test_per_family,
    }
    for family in families:
        for split, method in split_methods.items():
            session.env.load(family, 0, "easy")
            variations = [int(value) for value in method()]
            selection_seed = f"{seed}:{split}:{family}"
            offset = test_skip_per_family if split == "test" else 0
            selected = _stable_select(
                variations, split_counts[split], selection_seed, offset=offset
            )
            if len(selected) != split_counts[split]:
                raise RuntimeError(
                    f"ScienceWorld {split}/{family} has too few variations"
                )
            for variation in selected:
                result[split].append(
                    {
                        "task_id": f"{family}:{variation}",
                        "family": family,
                        "variation": variation,
                        "simplifications": "easy",
                    }
                )
            if split == "test":
                for variation in _stable_select(
                    variations, offset, selection_seed
                ):
                    result["excluded_engineering_test"].append(
                        {
                            "task_id": f"{family}:{variation}",
                            "family": family,
                            "reason": "used by a pre-freeze engineering run",
                        }
                    )

    demos: list[dict[str, Any]] = []
    for entry in result["demos"]:
        session.configure(
            entry["family"],
            entry["variation"],
            entry["simplifications"],
            generate_gold_path=True,
        )
        observation, task_description, _ = session.reset()
        actions = session.gold_actions()
        observations = [observation]
        for action in actions:
            observation, _, done, _ = session.step(action)
            observations.append(observation)
            if done:
                break
        demos.append(
            {
                **entry,
                "task_description": task_description,
                "actions": actions,
                "observations": observations,
            }
        )
    result["demos"] = demos
    session.close()
    return result


def environment_versions() -> dict[str, str]:
    from importlib.metadata import version

    return {
        "alfworld": version("alfworld"),
        "textworld": version("textworld"),
        "scienceworld": version("scienceworld"),
    }
