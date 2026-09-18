#!/usr/bin/env python3
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import os
import platform
import time
from typing import Any

import numpy as np

from skilllineage.interactive import (
    SKILL_SYSTEM_PROMPT,
    LocalChatModel,
    authoring_prompt,
    logical_skill_replays,
    matched_action_permutation,
    ngram_cosine,
    normalized_skill_text,
    parse_json_object,
    run_episode,
)
from skilllineage.interactive_envs import AlfworldEpisode, ScienceworldSession
from skilllineage.provenance import source_hash
from skilllineage.run_spec import ensure_run_spec


def stable_seed(*values: object) -> int:
    digest = hashlib.sha256(":".join(map(str, values)).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")
        handle.flush()


def subset_per_family(entries: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit < 0:
        return []
    if limit == 0:
        return entries
    counts: dict[str, int] = defaultdict(int)
    selected = []
    for entry in entries:
        if counts[entry["family"]] < limit:
            selected.append(entry)
            counts[entry["family"]] += 1
    return selected


def author_skills(
    model: LocalChatModel,
    config: dict[str, Any],
    manifest: dict[str, Any],
    families: dict[str, Any],
    output_dir: Path,
) -> tuple[dict[tuple[str, str, str], str], list[dict[str, Any]]]:
    path = output_dir / "skill_versions.jsonl"
    records = read_jsonl(path)
    existing = {
        (row["environment"], row["family"], row["condition"], row["depth"]): row
        for row in records
    }
    skills: dict[tuple[str, str, str], str] = {}
    for environment in ("alfworld", "scienceworld"):
        demos_by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for demo in manifest[environment]["demos"]:
            demos_by_family[demo["family"]].append(demo)
        for family in families[environment]["families"]:
            for condition in ("factual", "counterfactual"):
                parent = families[environment]["verified_source"]
                for depth in range(1, config["lineage_depth"] + 1):
                    key = (environment, family, condition, depth)
                    if key in existing:
                        parent = existing[key]["skill_text"]
                        continue
                    demo = demos_by_family[family][depth - 1]
                    prompt = authoring_prompt(
                        environment=environment,
                        family=family,
                        parent_skill=parent,
                        demonstration=demo,
                        depth=depth,
                    )
                    response = model.respond(
                        SKILL_SYSTEM_PROMPT,
                        prompt,
                        max_new_tokens=config["max_new_tokens_skill"],
                        seed=stable_seed(config["seed"], *key),
                    )
                    initial_response = None
                    json_repaired = (
                        parse_json_object(response.text, allow_repair=False) is None
                        and parse_json_object(response.text) is not None
                    )
                    if parse_json_object(response.text) is None:
                        initial_response = response
                        response = model.respond(
                            "Return exactly one valid JSON object and no markdown.",
                            "Repair only the JSON syntax and shorten repeated wording. "
                            "Preserve the draft's policy meaning and required schema.\n\n"
                            + response.text,
                            max_new_tokens=config["max_new_tokens_skill"],
                            seed=stable_seed(config["seed"], *key, "json_repair"),
                        )
                        if parse_json_object(response.text) is None:
                            failure_path = output_dir / "unparseable_skill.json"
                            failure_path.write_text(
                                json.dumps(
                                    {
                                        "key": key,
                                        "initial": initial_response.text,
                                        "repair": response.text,
                                    },
                                    indent=2,
                                ),
                                encoding="utf-8",
                            )
                            raise RuntimeError(
                                f"Unparseable skill JSON after repair for "
                                f"{environment}/{family}/{condition}/v{depth}"
                            )
                        json_repaired = (
                            parse_json_object(response.text, allow_repair=False) is None
                        )
                    skill_text = normalized_skill_text(response.text)
                    incident_injected = condition == "factual" and depth == 1
                    if incident_injected:
                        incident = families[environment]["defective_source"]
                        marker = "Principles:\n"
                        if marker in skill_text:
                            skill_text = skill_text.replace(
                                marker, marker + f"- {incident}\n", 1
                            )
                        else:
                            skill_text = f"Principles:\n- {incident}\n" + skill_text
                    record = {
                        "environment": environment,
                        "family": family,
                        "condition": condition,
                        "depth": depth,
                        "model_id": config["model_id"],
                        "model_revision": config["model_revision"],
                        "parent_sha256": hashlib.sha256(parent.encode()).hexdigest(),
                        "evidence_task_id": demo["task_id"],
                        "prompt_sha256": (
                            initial_response.prompt_sha256
                            if initial_response is not None
                            else response.prompt_sha256
                        ),
                        "repair_prompt_sha256": (
                            response.prompt_sha256
                            if initial_response is not None
                            else None
                        ),
                        "initial_raw_output": (
                            initial_response.text if initial_response is not None else None
                        ),
                        "raw_output": response.text,
                        "skill_text": skill_text,
                        "skill_sha256": hashlib.sha256(skill_text.encode()).hexdigest(),
                        "latency_sec": response.latency_sec
                        + (
                            initial_response.latency_sec
                            if initial_response is not None
                            else 0.0
                        ),
                        "input_tokens": response.input_tokens
                        + (
                            initial_response.input_tokens
                            if initial_response is not None
                            else 0
                        ),
                        "output_tokens": response.output_tokens
                        + (
                            initial_response.output_tokens
                            if initial_response is not None
                            else 0
                        ),
                        "generation_attempts": 2 if initial_response is not None else 1,
                        "parse_ok": True,
                        "json_repaired": json_repaired,
                        "incident_injected": incident_injected,
                    }
                    append_jsonl(path, record)
                    records.append(record)
                    existing[key] = record
                    parent = skill_text
                    print(
                        f"authored {environment}/{family}/{condition}/v{depth}",
                        flush=True,
                    )
                skills[(environment, family, condition)] = parent
    return skills, records


def run_task(
    *,
    model: LocalChatModel,
    config: dict[str, Any],
    entry: dict[str, Any],
    environment: str,
    split: str,
    condition: str,
    skill: str,
    science_session: ScienceworldSession | None,
) -> dict[str, Any]:
    if environment == "alfworld":
        data_dir = os.environ.get("ALFWORLD_DATA")
        if not data_dir:
            raise RuntimeError("ALFWORLD_DATA is not set")
        episode = AlfworldEpisode(
            Path(data_dir) / entry["gamefile"],
            max_steps=config["alfworld_max_steps"],
        )
        try:
            result = run_episode(
                model=model,
                environment=environment,
                split=split,
                task_id=entry["task_id"],
                family=entry["family"],
                skill_condition=condition,
                skill=skill,
                reset=episode.reset,
                step=episode.step,
                max_steps=config["alfworld_max_steps"],
                max_new_tokens=config["max_new_tokens_action"],
                history_turns=config["history_turns"],
                seed=stable_seed(config["seed"], environment, split, entry["task_id"], condition),
            )
        finally:
            episode.close()
    else:
        if science_session is None:
            raise RuntimeError("ScienceWorld session is missing")
        science_session.configure(
            entry["family"], entry["variation"], entry["simplifications"]
        )
        result = run_episode(
            model=model,
            environment=environment,
            split=split,
            task_id=entry["task_id"],
            family=entry["family"],
            skill_condition=condition,
            skill=skill,
            reset=science_session.reset,
            step=science_session.step,
            max_steps=config["scienceworld_max_steps"],
            max_new_tokens=config["max_new_tokens_action"],
            history_turns=config["history_turns"],
            seed=stable_seed(config["seed"], environment, split, entry["task_id"], condition),
        )
    return result.to_dict()


def evaluate_conditions(
    model: LocalChatModel,
    config: dict[str, Any],
    manifest: dict[str, Any],
    skills: dict[tuple[str, str, str], str],
    output_dir: Path,
    *,
    dev_limit: int,
    test_limit: int,
) -> list[dict[str, Any]]:
    path = output_dir / "episodes.jsonl"
    records = read_jsonl(path)
    completed = {
        (row["environment"], row["split"], row["task_id"], row["skill_condition"])
        for row in records
    }
    science_session = ScienceworldSession(max_steps=config["scienceworld_max_steps"])
    try:
        for split, limit in (("dev", dev_limit), ("test", test_limit)):
            for environment in ("alfworld", "scienceworld"):
                entries = subset_per_family(manifest[environment][split], limit)
                for entry in entries:
                    for condition in ("factual", "counterfactual", "none"):
                        key = (environment, split, entry["task_id"], condition)
                        if key in completed:
                            continue
                        skill = "" if condition == "none" else skills[
                            (environment, entry["family"], condition)
                        ]
                        record = run_task(
                            model=model,
                            config=config,
                            entry=entry,
                            environment=environment,
                            split=split,
                            condition=condition,
                            skill=skill,
                            science_session=science_session,
                        )
                        append_jsonl(path, record)
                        records.append(record)
                        completed.add(key)
                        print(
                            f"episode {environment}/{split}/{entry['task_id']}/{condition}: "
                            f"score={record['normalized_score']:.3f}, steps={record['steps']}",
                            flush=True,
                        )
    finally:
        science_session.close()
    return records


def build_decisions(
    records: list[dict[str, Any]],
    skills: dict[tuple[str, str, str], str],
    families: dict[str, Any],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        if row["split"] == "dev":
            grouped[(row["environment"], row["family"], row["skill_condition"])].append(row)
    decisions = []
    path_score = config["parent_influence"] ** max(
        0, config["lineage_depth"] - 1
    )
    for environment in ("alfworld", "scienceworld"):
        source = families[environment]["defective_source"]
        for family in families[environment]["families"]:
            by_condition = {
                condition: grouped[(environment, family, condition)]
                for condition in ("factual", "counterfactual", "none")
            }
            means = {
                condition: float(
                    np.mean([row["normalized_score"] for row in rows])
                )
                if rows
                else 0.0
                for condition, rows in by_condition.items()
            }
            violation = {
                condition: float(
                    np.mean([row["diagnostic_violation"] for row in rows])
                )
                if rows
                else 1.0
                for condition, rows in by_condition.items()
            }
            factual_deficit = max(0.0, means["none"] - means["factual"])
            probe_score = max(violation["factual"], factual_deficit)
            lineage_score = 0.45 * math.sqrt(path_score) + 0.55 * probe_score
            selected = lineage_score >= config["screening_threshold"]
            promotes = selected and (
                (
                    means["counterfactual"] >= means["factual"] + 0.02
                    and violation["counterfactual"] <= violation["factual"]
                )
                or (
                    violation["counterfactual"] < violation["factual"]
                    and means["counterfactual"] >= means["factual"] - 0.05
                )
            )
            action = "retain"
            if selected:
                action = "replace" if promotes else "quarantine"
            similarity = ngram_cosine(
                source, skills[(environment, family, "factual")]
            )
            decisions.append(
                {
                    "environment": environment,
                    "family": family,
                    "path_score": path_score,
                    "probe_score": probe_score,
                    "lineage_score": lineage_score,
                    "selected": selected,
                    "action": action,
                    "semantic_similarity": similarity,
                    "semantic_delete": similarity >= config["semantic_threshold"],
                    "factual_dev_score": means["factual"],
                    "counterfactual_dev_score": means["counterfactual"],
                    "no_skill_dev_score": means["none"],
                    "factual_violation_rate": violation["factual"],
                    "counterfactual_violation_rate": violation["counterfactual"],
                }
            )
    return decisions


def materialize_methods(
    records: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    config: dict[str, Any],
    output_dir: Path,
) -> Path:
    test = {
        (row["environment"], row["task_id"], row["skill_condition"]): row
        for row in records
        if row["split"] == "test"
    }
    decision_map = {
        (row["environment"], row["family"]): row for row in decisions
    }
    random_actions = matched_action_permutation(
        decisions, seed=config["seed"], label=config["model_short_name"]
    )
    rows: list[dict[str, Any]] = []
    tasks = sorted({(key[0], key[1]) for key in test})
    for environment, task_id in tasks:
        factual = test[(environment, task_id, "factual")]
        counterfactual = test[(environment, task_id, "counterfactual")]
        no_skill = test[(environment, task_id, "none")]
        family = factual["family"]
        decision = decision_map[(environment, family)]
        def apply_action(action: str) -> dict[str, Any]:
            if action == "replace":
                return counterfactual
            if action in {"quarantine", "delete"}:
                return no_skill
            return factual

        proposed = apply_action(decision["action"])
        semantic_delete_action = "delete" if decision["semantic_delete"] else "retain"
        semantic_replay_action = "replace" if decision["semantic_delete"] else "retain"
        random_action = random_actions[(environment, family)]
        oracle = max(
            (factual, counterfactual, no_skill),
            key=lambda row: (row["normalized_score"], -row["steps"]),
        )
        methods = {
            "none": (factual, False, "no_intervention"),
            "source_only": (factual, False, "delete_source"),
            "semantic": (
                apply_action(semantic_delete_action),
                decision["semantic_delete"],
                semantic_delete_action,
            ),
            "semantic_replay": (
                apply_action(semantic_replay_action),
                decision["semantic_delete"],
                semantic_replay_action,
            ),
            "full_lineage": (no_skill, True, "delete"),
            "full_lineage_replay": (counterfactual, True, "replace"),
            "random_matched": (
                apply_action(random_action),
                random_action != "retain",
                random_action,
            ),
            "skilllineage": (proposed, decision["selected"], decision["action"]),
            "oracle_selective": (
                oracle,
                oracle["skill_condition"] != "factual",
                "oracle",
            ),
        }
        for method, (source, selected, recovery_action) in methods.items():
            rows.append(
                {
                    "model": config["model_short_name"],
                    "environment": environment,
                    "task_id": task_id,
                    "family": family,
                    "method": method,
                    "source_condition": source["skill_condition"],
                    "success": source["success"],
                    "normalized_score": source["normalized_score"],
                    "steps": source["steps"],
                    "invalid_outputs": source["invalid_outputs"],
                    "latency_sec": source["latency_sec"],
                    "selected_family": selected,
                    "recovery_action": recovery_action,
                    "skill_replays": logical_skill_replays(
                        method, recovery_action, config["lineage_depth"]
                    ),
                }
            )
    output = output_dir / "method_results.csv"
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with (output_dir / "recovery_decisions.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(decisions[0]))
        writer.writeheader()
        writer.writerows(decisions)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--dev-limit-per-family", type=int, default=0)
    parser.add_argument("--test-limit-per-family", type=int, default=0)
    parser.add_argument("--author-only", action="store_true")
    parser.add_argument("--dev-only", action="store_true")
    args = parser.parse_args()
    config_path = Path(args.config)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if args.output_dir:
        config["output_dir"] = args.output_dir
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(config["manifest_path"])
    families_path = Path(config["families_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    families = json.loads(families_path.read_text(encoding="utf-8"))
    run_spec = ensure_run_spec(
        output_dir, config_path, manifest_path, families_path, config
    )

    started = time.time()
    model = LocalChatModel(
        config["model_id"],
        revision=config["model_revision"],
        local_files_only=config.get("local_files_only", True),
    )
    skills, skill_records = author_skills(
        model, config, manifest, families, output_dir
    )
    if args.author_only:
        print(
            f"authored {len(skill_records)} versions in {output_dir}", flush=True
        )
        return
    episodes = evaluate_conditions(
        model,
        config,
        manifest,
        skills,
        output_dir,
        dev_limit=args.dev_limit_per_family,
        test_limit=-1 if args.dev_only else args.test_limit_per_family,
    )
    decisions = build_decisions(episodes, skills, families, config)
    if args.dev_only:
        with (output_dir / "recovery_decisions.csv").open(
            "w", newline="", encoding="utf-8"
        ) as handle:
            writer = csv.DictWriter(handle, fieldnames=list(decisions[0]))
            writer.writeheader()
            writer.writerows(decisions)
        print(output_dir / "recovery_decisions.csv", flush=True)
        return
    result_path = materialize_methods(episodes, decisions, config, output_dir)

    torch = model.torch
    metadata = {
        "created_unix": time.time(),
        "elapsed_sec": time.time() - started,
        "run_spec": run_spec,
        "config": config,
        "config_path": str(config_path),
        "source_sha256": source_hash(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "model_dtype": str(model.model.dtype),
        "model_parameter_count": sum(p.numel() for p in model.model.parameters()),
        "peak_cuda_memory_gb": (
            torch.cuda.max_memory_reserved() / 1024**3
            if torch.cuda.is_available()
            else None
        ),
        "skill_versions": len(skill_records),
        "episodes": len(episodes),
        "dev_limit_per_family": args.dev_limit_per_family,
        "test_limit_per_family": args.test_limit_per_family,
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2), encoding="utf-8"
    )
    print(result_path, flush=True)


if __name__ == "__main__":
    main()
