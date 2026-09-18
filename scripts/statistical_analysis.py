#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon


PAIR_KEYS = [
    "seed",
    "depth",
    "branching_factor",
    "propagation_probability",
    "missing_edge_rate",
]
BASELINES = [
    "none",
    "source_only",
    "semantic",
    "full_lineage",
    "full_lineage_replay",
]


def bootstrap_mean_interval(
    values: np.ndarray, *, draws: int, seed: int
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    sampled = rng.choice(values, size=(draws, len(values)), replace=True)
    means = sampled.mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def holm_adjust(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running = 0.0
    total = len(p_values)
    for rank, index in enumerate(order):
        candidate = min(1.0, (total - rank) * p_values[index])
        running = max(running, candidate)
        adjusted[index] = running
    return adjusted.tolist()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--bootstrap-draws", default=10_000, type=int)
    parser.add_argument("--seed", default=20260904, type=int)
    args = parser.parse_args()

    frame = pd.read_csv(args.input)
    proposed = frame[frame["method"] == "skilllineage"]
    rows: list[dict[str, float | int | str]] = []
    raw_p_values: list[float] = []
    for index, baseline_name in enumerate(BASELINES):
        baseline = frame[frame["method"] == baseline_name]
        paired = proposed.merge(
            baseline,
            on=PAIR_KEYS,
            suffixes=("_skilllineage", "_baseline"),
            validate="one_to_one",
        )
        utility_delta = (
            paired["task_utility_skilllineage"]
            - paired["task_utility_baseline"]
        ).to_numpy()
        ci_low, ci_high = bootstrap_mean_interval(
            utility_delta,
            draws=args.bootstrap_draws,
            seed=args.seed + index,
        )
        test = wilcoxon(
            utility_delta,
            alternative="two-sided",
            zero_method="zsplit",
            method="approx",
        )
        raw_p_values.append(float(test.pvalue))
        baseline_replays = paired["counterfactual_replays_baseline"].mean()
        proposed_replays = paired["counterfactual_replays_skilllineage"].mean()
        replay_reduction = (
            1.0 - proposed_replays / baseline_replays
            if baseline_replays > 0
            else float("nan")
        )
        rows.append(
            {
                "baseline": baseline_name,
                "n_pairs": len(paired),
                "utility_delta_mean": utility_delta.mean(),
                "utility_delta_ci_low": ci_low,
                "utility_delta_ci_high": ci_high,
                "utility_delta_median": np.median(utility_delta),
                "wilcoxon_statistic": float(test.statistic),
                "p_value": float(test.pvalue),
                "skilllineage_replays_mean": proposed_replays,
                "baseline_replays_mean": baseline_replays,
                "replay_reduction": replay_reduction,
            }
        )

    adjusted = holm_adjust(raw_p_values)
    for row, value in zip(rows, adjusted, strict=True):
        row["p_value_holm"] = value

    output = pd.DataFrame(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(args.output, index=False)
    print(output.to_string(index=False))


if __name__ == "__main__":
    main()
