#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import binomtest, wilcoxon


BASELINES = [
    "none",
    "source_only",
    "semantic",
    "semantic_replay",
    "full_lineage",
    "full_lineage_replay",
    "random_matched",
]
PAIR_KEYS = ["model", "environment", "task_id"]
METHODS = BASELINES + ["skilllineage", "oracle_selective"]


def validate_results(frame: pd.DataFrame) -> None:
    required = set(PAIR_KEYS) | {
        "family",
        "method",
        "success",
        "normalized_score",
        "steps",
        "invalid_outputs",
        "latency_sec",
        "skill_replays",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing result columns: {sorted(missing)}")
    if frame.duplicated(PAIR_KEYS + ["method"]).any():
        raise ValueError("Duplicate model/environment/task/method result rows")
    expected = set(METHODS)
    for key, group in frame.groupby(PAIR_KEYS):
        methods = set(group["method"])
        if methods != expected:
            raise ValueError(
                f"Incomplete method coverage for {key}: "
                f"expected {sorted(expected)}, got {sorted(methods)}"
            )
    task_counts = frame.groupby(["model", "environment", "method"])["task_id"].size()
    if task_counts.nunique() != 1:
        raise ValueError(f"Unequal task coverage: {task_counts.to_dict()}")


def stratified_bootstrap(
    paired: pd.DataFrame,
    column: str,
    *,
    draws: int,
    seed: int,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    strata = [group[column].to_numpy() for _, group in paired.groupby(["model", "environment"])]
    samples = np.empty(draws)
    for draw in range(draws):
        values = [rng.choice(stratum, size=len(stratum), replace=True) for stratum in strata]
        samples[draw] = np.concatenate(values).mean()
    return tuple(float(value) for value in np.quantile(samples, [0.025, 0.975]))


def holm_adjust(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = np.empty(len(p_values), dtype=float)
    running = 0.0
    total = len(p_values)
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (total - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted.tolist()


def paired_test(values: np.ndarray) -> tuple[float, float]:
    nonzero = values[np.abs(values) > 1e-12]
    if len(nonzero) == 0:
        return 0.0, 1.0
    result = wilcoxon(values, zero_method="pratt", method="approx")
    return float(result.statistic), float(result.pvalue)


def ordinary_bootstrap(
    values: np.ndarray, *, draws: int, seed: int
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    samples = rng.choice(values, size=(draws, len(values)), replace=True).mean(axis=1)
    return tuple(float(value) for value in np.quantile(samples, [0.025, 0.975]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dirs", nargs="+", required=True, type=Path)
    parser.add_argument("--table-dir", default="results/tables", type=Path)
    parser.add_argument("--figure-dir", default="results/figures", type=Path)
    parser.add_argument("--bootstrap-draws", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=20260904)
    args = parser.parse_args()
    args.table_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    decisions = []
    observed_models: set[str] = set()
    for path in args.run_dirs:
        run_frame = pd.read_csv(path / "method_results.csv")
        run_models = set(run_frame["model"])
        overlap = observed_models & run_models
        if overlap:
            raise ValueError(f"Model appears in multiple run directories: {sorted(overlap)}")
        observed_models |= run_models
        frames.append(run_frame)
        decision_frame = pd.read_csv(path / "recovery_decisions.csv")
        if len(run_models) != 1:
            raise ValueError(f"Expected one model per run directory: {path}")
        decision_frame.insert(0, "model", next(iter(run_models)))
        decisions.append(decision_frame)
    frame = pd.concat(frames, ignore_index=True)
    validate_results(frame)
    frame.to_csv(args.table_dir / "interactive_all_results.csv", index=False)
    pd.concat(decisions, ignore_index=True).to_csv(
        args.table_dir / "interactive_recovery_decisions.csv", index=False
    )

    summary = (
        frame.groupby(["environment", "model", "method"], as_index=False)
        .agg(
            task_count=("task_id", "size"),
            success_rate=("success", "mean"),
            normalized_score=("normalized_score", "mean"),
            mean_steps=("steps", "mean"),
            invalid_output_rate=("invalid_outputs", lambda values: values.sum() / max(1, frame.loc[values.index, "steps"].sum())),
            mean_episode_latency_sec=("latency_sec", "mean"),
        )
    )
    summary.to_csv(args.table_dir / "interactive_summary.csv", index=False)

    by_family = (
        frame.groupby(["environment", "family", "method"], as_index=False)
        .agg(
            task_model_pairs=("task_id", "size"),
            success_rate=("success", "mean"),
            normalized_score=("normalized_score", "mean"),
        )
    )
    by_family.to_csv(args.table_dir / "interactive_by_family.csv", index=False)

    replay = (
        frame.groupby(["model", "environment", "method", "family"], as_index=False)["skill_replays"]
        .max()
        .groupby(["model", "environment", "method"], as_index=False)["skill_replays"]
        .sum()
    )
    replay.to_csv(args.table_dir / "interactive_replay_cost.csv", index=False)

    proposed = frame[frame["method"] == "skilllineage"]
    comparisons = []
    raw_p_values = []
    for index, baseline_name in enumerate(BASELINES):
        baseline = frame[frame["method"] == baseline_name]
        paired = proposed.merge(
            baseline,
            on=PAIR_KEYS,
            suffixes=("_skilllineage", "_baseline"),
            validate="one_to_one",
        )
        paired["score_delta"] = (
            paired["normalized_score_skilllineage"]
            - paired["normalized_score_baseline"]
        )
        paired["success_delta"] = (
            paired["success_skilllineage"].astype(float)
            - paired["success_baseline"].astype(float)
        )
        ci_low, ci_high = stratified_bootstrap(
            paired,
            "score_delta",
            draws=args.bootstrap_draws,
            seed=args.seed + index,
        )
        statistic, p_value = paired_test(paired["score_delta"].to_numpy())
        discordant_positive = int((paired["success_delta"] > 0).sum())
        discordant_negative = int((paired["success_delta"] < 0).sum())
        discordant = discordant_positive + discordant_negative
        mcnemar_p = (
            float(binomtest(discordant_positive, discordant, 0.5).pvalue)
            if discordant
            else 1.0
        )
        raw_p_values.append(p_value)
        comparisons.append(
            {
                "baseline": baseline_name,
                "n_pairs": len(paired),
                "score_delta_mean": paired["score_delta"].mean(),
                "score_delta_ci_low": ci_low,
                "score_delta_ci_high": ci_high,
                "wilcoxon_statistic": statistic,
                "p_value": p_value,
                "success_gain_pairs": discordant_positive,
                "success_loss_pairs": discordant_negative,
                "mcnemar_exact_p": mcnemar_p,
            }
        )
    for row, adjusted in zip(comparisons, holm_adjust(raw_p_values), strict=True):
        row["p_value_holm"] = adjusted
    comparison_frame = pd.DataFrame(comparisons)
    comparison_frame.to_csv(args.table_dir / "interactive_pairwise.csv", index=False)

    stratum_rows = []
    for baseline_index, baseline_name in enumerate(BASELINES):
        baseline = frame[frame["method"] == baseline_name]
        paired = proposed.merge(
            baseline,
            on=PAIR_KEYS,
            suffixes=("_skilllineage", "_baseline"),
            validate="one_to_one",
        )
        paired["score_delta"] = (
            paired["normalized_score_skilllineage"]
            - paired["normalized_score_baseline"]
        )
        paired["success_delta"] = (
            paired["success_skilllineage"].astype(float)
            - paired["success_baseline"].astype(float)
        )
        for stratum_index, ((model, environment), group) in enumerate(
            paired.groupby(["model", "environment"])
        ):
            values = group["score_delta"].to_numpy()
            ci_low, ci_high = ordinary_bootstrap(
                values,
                draws=args.bootstrap_draws,
                seed=args.seed + 100 * baseline_index + stratum_index,
            )
            stratum_rows.append(
                {
                    "model": model,
                    "environment": environment,
                    "baseline": baseline_name,
                    "n_pairs": len(group),
                    "score_delta_mean": values.mean(),
                    "score_delta_ci_low": ci_low,
                    "score_delta_ci_high": ci_high,
                    "success_delta_mean": group["success_delta"].mean(),
                }
            )
    pd.DataFrame(stratum_rows).to_csv(
        args.table_dir / "interactive_pairwise_strata.csv", index=False
    )

    method_order = [
        "none",
        "source_only",
        "semantic",
        "semantic_replay",
        "full_lineage",
        "full_lineage_replay",
        "random_matched",
        "skilllineage",
        "oracle_selective",
    ]
    environments = sorted(frame["environment"].unique())
    fig, axes = plt.subplots(1, len(environments), figsize=(11.5, 4.0), sharey=True)
    if len(environments) == 1:
        axes = [axes]
    for ax, environment in zip(axes, environments, strict=True):
        subset = frame[frame["environment"] == environment]
        means = subset.groupby("method")["normalized_score"].mean().reindex(method_order)
        x = np.arange(len(method_order))
        ax.bar(x, means, color="#4878a8", alpha=0.85)
        for model, group in subset.groupby("model"):
            model_means = group.groupby("method")["normalized_score"].mean().reindex(method_order)
            ax.scatter(x, model_means, s=20, label=model, zorder=3)
        ax.set_title(environment)
        ax.set_xticks(x, [name.replace("_", "\n") for name in method_order], fontsize=7)
        ax.set_ylim(0, 1.0)
        ax.grid(axis="y", alpha=0.25)
    axes[0].set_ylabel("Normalized task score")
    axes[-1].legend(fontsize=7, loc="upper right")
    fig.tight_layout()
    fig.savefig(args.figure_dir / "interactive_main.pdf")
    fig.savefig(args.figure_dir / "interactive_main.png", dpi=180)
    plt.close(fig)

    print(summary.to_string(index=False))
    print(comparison_frame.to_string(index=False))
    print(replay.to_string(index=False))


if __name__ == "__main__":
    main()
