#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from skilllineage.llm_pilot import run_model_pilot


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", default="configs/model_pilot.json", type=Path
    )
    args = parser.parse_args()
    print(run_model_pilot(args.config))


if __name__ == "__main__":
    main()

