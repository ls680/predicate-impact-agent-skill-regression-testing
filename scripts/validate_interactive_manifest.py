#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter
from pathlib import Path
import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", default="data/processed/interactive_manifest.json", type=Path
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected = manifest["counts_per_family"]
    for environment in ("alfworld", "scienceworld"):
        seen: set[str] = set()
        families: set[str] | None = None
        for split in ("demos", "dev", "test"):
            entries = manifest[environment][split]
            counts = Counter(entry["family"] for entry in entries)
            split_families = set(counts)
            families = split_families if families is None else families
            if split_families != families:
                raise SystemExit(f"{environment}: family mismatch in {split}")
            expected_count = expected[split]
            if any(count != expected_count for count in counts.values()):
                raise SystemExit(
                    f"{environment}: unexpected per-family count in {split}: {counts}"
                )
            identifiers = {entry["task_id"] for entry in entries}
            if seen & identifiers:
                raise SystemExit(f"{environment}: split leakage detected in {split}")
            seen |= identifiers
            if split == "demos":
                for entry in entries:
                    if not entry.get("actions"):
                        raise SystemExit(f"{environment}: empty demo {entry['task_id']}")
                    if any("ERROR:" in action for action in entry["actions"]):
                        raise SystemExit(f"{environment}: invalid gold demo {entry['task_id']}")
        excluded = {
            entry["task_id"]
            for entry in manifest[environment].get("excluded_engineering_test", [])
        }
        test_ids = {entry["task_id"] for entry in manifest[environment]["test"]}
        if excluded & test_ids:
            raise SystemExit(f"{environment}: engineering-test leakage detected")
        expected_excluded = (
            len(families or set())
            * manifest.get("excluded_engineering_test_per_family", 0)
        )
        if len(excluded) != expected_excluded:
            raise SystemExit(
                f"{environment}: expected {expected_excluded} excluded engineering "
                f"tasks, found {len(excluded)}"
            )
        print(f"{environment}: {len(families or [])} families, {len(seen)} unique tasks")


if __name__ == "__main__":
    main()
