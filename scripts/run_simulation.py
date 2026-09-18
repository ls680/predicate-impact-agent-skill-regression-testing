#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from skilllineage.experiment import run_simulation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="configs/simulation.json", type=Path
    )
    args = parser.parse_args()
    output = run_simulation(args.config)
    print(output)


if __name__ == "__main__":
    main()

