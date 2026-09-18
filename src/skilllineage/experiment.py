from __future__ import annotations

from itertools import product
from pathlib import Path
import json
import platform
import subprocess
import time

import pandas as pd

from .benchmark import BenchmarkConfig, generate_scenario
from .metrics import evaluate
from .provenance import source_hash
from .recovery import recover


def _git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "uncommitted"


def run_simulation(config_path: str | Path) -> Path:
    config_path = Path(config_path)
    config = json.loads(config_path.read_text(encoding="utf-8"))
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    grid = product(
        range(config["seeds"]),
        config["depths"],
        config["branching_factors"],
        config["propagation_probabilities"],
        config["missing_edge_rates"],
    )
    for seed, depth, branching, propagation, missing_edges in grid:
        scenario = generate_scenario(
            BenchmarkConfig(
                depth=depth,
                branching_factor=branching,
                propagation_probability=propagation,
                missing_edge_rate=missing_edges,
                seed=seed,
            )
        )
        for method_index, method in enumerate(config["methods"]):
            result = recover(
                scenario,
                method,
                seed=seed * 100 + method_index,
                threshold=config["skilllineage_threshold"],
                repair_success=config["counterfactual_repair_success"],
                false_positive_damage=config[
                    "counterfactual_false_positive_damage"
                ],
            )
            metrics = evaluate(
                scenario,
                result,
                base_success=config["base_success"],
                clean_skill_success=config["clean_skill_success"],
                contaminated_skill_success=config[
                    "contaminated_skill_success"
                ],
            )
            rows.append(
                {
                    "seed": seed,
                    "depth": depth,
                    "branching_factor": branching,
                    "propagation_probability": propagation,
                    "missing_edge_rate": missing_edges,
                    "method": method,
                    "node_count": len(scenario.nodes),
                    **metrics.to_dict(),
                }
            )

    frame = pd.DataFrame(rows)
    output_path = output_dir / "results.csv"
    frame.to_csv(output_path, index=False)
    metadata = {
        "created_unix": time.time(),
        "config": config,
        "config_path": str(config_path),
        "git_commit": _git_commit(),
        "source_sha256": source_hash(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "rows": len(frame),
    }
    (output_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
    )
    return output_path
