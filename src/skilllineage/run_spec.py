from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import hashlib
import json
import platform
import time
from typing import Any

from skilllineage.provenance import source_hash


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_versions() -> dict[str, str]:
    packages = (
        "torch",
        "transformers",
        "accelerate",
        "alfworld",
        "textworld",
        "scienceworld",
        "json-repair",
    )
    values = {}
    for package in packages:
        try:
            values[package] = version(package)
        except PackageNotFoundError:
            values[package] = "not-installed"
    return values


def ensure_run_spec(
    output_dir: Path,
    config_path: Path,
    manifest_path: Path,
    families_path: Path,
    config: dict[str, Any],
) -> dict[str, Any]:
    expected = {
        "schema_version": 1,
        "source_sha256": source_hash(),
        "config_file_sha256": file_sha256(config_path),
        "manifest_sha256": file_sha256(manifest_path),
        "families_sha256": file_sha256(families_path),
        "effective_config": config,
        "package_versions": package_versions(),
        "python": platform.python_version(),
    }
    path = output_dir / "run_spec.json"
    if path.exists():
        recorded = json.loads(path.read_text(encoding="utf-8"))
        mismatches = {
            key: {"recorded": recorded.get(key), "current": value}
            for key, value in expected.items()
            if recorded.get(key) != value
        }
        if mismatches:
            raise RuntimeError(
                "Refusing to resume an immutable run with changed inputs: "
                + json.dumps(mismatches, sort_keys=True)
            )
        return recorded
    spec = {**expected, "created_unix": time.time()}
    path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    return spec
