#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import json
import os
import time

from skilllineage.interactive_envs import (
    collect_alfworld_demonstrations,
    collect_alfworld_manifest,
    collect_scienceworld_manifest,
    environment_versions,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--families", default="data/raw/interactive_families.json")
    parser.add_argument("--output", default="data/processed/interactive_manifest.json")
    parser.add_argument("--alfworld-data", default=os.environ.get("ALFWORLD_DATA"))
    parser.add_argument("--demos-per-family", type=int, default=3)
    parser.add_argument("--dev-per-family", type=int, default=5)
    parser.add_argument("--test-per-family", type=int, default=8)
    parser.add_argument("--test-skip-per-family", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260904)
    args = parser.parse_args()
    if not args.alfworld_data:
        parser.error("--alfworld-data or ALFWORLD_DATA is required")

    families = json.loads(Path(args.families).read_text(encoding="utf-8"))
    alfworld = collect_alfworld_manifest(
        args.alfworld_data,
        families["alfworld"]["families"],
        demos_per_family=args.demos_per_family,
        dev_per_family=args.dev_per_family,
        test_per_family=args.test_per_family,
        test_skip_per_family=args.test_skip_per_family,
        seed=args.seed,
    )
    alfworld["demos"], alfworld["rejected_demo_candidates"] = (
        collect_alfworld_demonstrations(
            alfworld["demos"],
            args.alfworld_data,
            max_steps=50,
            target_per_family=args.demos_per_family,
        )
    )
    scienceworld = collect_scienceworld_manifest(
        families["scienceworld"]["families"],
        demos_per_family=args.demos_per_family,
        dev_per_family=args.dev_per_family,
        test_per_family=args.test_per_family,
        test_skip_per_family=args.test_skip_per_family,
        seed=args.seed,
        max_steps=80,
    )
    manifest = {
        "created_unix": time.time(),
        "seed": args.seed,
        "selection": "SHA-256 rank within official split and task family",
        "counts_per_family": {
            "demos": args.demos_per_family,
            "dev": args.dev_per_family,
            "test": args.test_per_family,
        },
        "excluded_engineering_test_per_family": args.test_skip_per_family,
        "environment_versions": environment_versions(),
        "alfworld": alfworld,
        "scienceworld": scienceworld,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
