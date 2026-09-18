#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--table-dir", default="results/tables", type=Path)
    parser.add_argument("--figure-dir", default="results/figures", type=Path)
    args = parser.parse_args()
    args.table_dir.mkdir(parents=True, exist_ok=True)
    args.figure_dir.mkdir(parents=True, exist_ok=True)

    pairs = pd.read_csv(args.input_dir / "pair_results.csv")
    summary = pd.read_csv(args.input_dir / "summary.csv")
    summary.to_csv(args.table_dir / "model_pilot_summary.csv", index=False)

    by_depth = (
        pairs.groupby("depth", as_index=False)
        .agg(
            factual_pass_rate=("factual_pass", "mean"),
            counterfactual_pass_rate=("counterfactual_pass", "mean"),
            inherited_failure_rate=("inherited_failure", "mean"),
            causal_recovery_rate=("causal_recovery", "mean"),
            pair_count=("case_id", "size"),
        )
    )
    by_depth.to_csv(args.table_dir / "model_pilot_by_depth.csv", index=False)

    fig, ax = plt.subplots(figsize=(6.2, 3.8))
    ax.plot(
        by_depth["depth"],
        by_depth["factual_pass_rate"],
        marker="o",
        label="Factual contaminated lineage",
    )
    ax.plot(
        by_depth["depth"],
        by_depth["counterfactual_pass_rate"],
        marker="s",
        label="Counterfactual clean lineage",
    )
    ax.set_xlabel("Lineage depth")
    ax.set_ylabel("Verifier pass rate")
    ax.set_ylim(0, 1.05)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(args.figure_dir / "model_pilot_by_depth.pdf")
    fig.savefig(args.figure_dir / "model_pilot_by_depth.png", dpi=180)
    plt.close(fig)
    print(summary.to_string(index=False))
    print(by_depth.to_string(index=False))


if __name__ == "__main__":
    main()
