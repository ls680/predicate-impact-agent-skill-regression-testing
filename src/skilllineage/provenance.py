from __future__ import annotations

import hashlib
from pathlib import Path


def source_hash() -> str:
    """Hash source, scripts, and configurations used by an experiment."""

    project_root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    files: list[Path] = []
    for relative_root in ("src", "scripts", "configs"):
        files.extend(
            path
            for path in (project_root / relative_root).rglob("*")
            if (
                path.is_file()
                and "__pycache__" not in path.parts
                and not any(part.endswith(".egg-info") for part in path.parts)
                and path.suffix in {".json", ".py", ".sh", ".yaml", ".yml"}
            )
        )
    for path in sorted(files):
        digest.update(path.relative_to(project_root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()
