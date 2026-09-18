#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


METHOD_ORDER = [
    "none",
    "source_only",
    "semantic",
    "full_lineage",
    "full_lineage_replay",
    "skilllineage",
    "oracle_selective",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--table-dir", default="results/tables", type=Path)
    parser.add_argument("--figure-dir", default="results/figures", type=Path)
    args = parser.parse_args()
    args.table_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_csv(args.input)
    summary = (
        frame.groupby("method", as_index=False)
        .agg(
            task_utility_mean=("task_utility", "mean"),
            task_utility_std=("task_utility", "std"),
            recovery_ratio_mean=("recovery_ratio", "mean"),
            impact_f1_mean=("impact_f1", "mean"),
            collateral_loss_mean=("collateral_loss", "mean"),
            active_fraction_mean=("active_fraction", "mean"),
            counterfactual_replays_mean=("counterfactual_replays", "mean"),
        )
    )
    summary["method"] = pd.Categorical(
        summary["method"], categories=METHOD_ORDER, ordered=True
    )
    summary = summary.sort_values("method")
    summary.to_csv(args.table_dir / "simulation_summary.csv", index=False)

    depth = (
        frame.groupby(["depth", "method"], as_index=False)["task_utility"]
        .mean()
    )
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    for method in METHOD_ORDER:
        subset = depth[depth["method"] == method]
        ax.plot(subset["depth"], subset["task_utility"], marker="o", label=method)
    ax.set_xlabel("Lineage depth")
    ax.set_ylabel("Post-recovery task utility")
    ax.set_ylim(0, 0.9)
    ax.grid(alpha=0.25)
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(args.figure_dir / "utility_by_depth.pdf")
    fig.savefig(args.figure_dir / "utility_by_depth.png", dpi=180)
    plt.close(fig)

    missing = (
        frame.groupby(["missing_edge_rate", "method"], as_index=False)[
            ["impact_recall", "task_utility"]
        ]
        .mean()
    )
    missing.to_csv(args.table_dir / "missing_edge_sensitivity.csv", index=False)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
