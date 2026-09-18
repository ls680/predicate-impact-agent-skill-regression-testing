#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json

from huggingface_hub import snapshot_download


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("configs", nargs="+")
    args = parser.parse_args()
    for config_path in args.configs:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        path = snapshot_download(
            repo_id=config["model_id"],
            revision=config["model_revision"],
            ignore_patterns=["consolidated.safetensors", "*.pth", "*.gguf"],
        )
        print(f"{config['model_id']}@{config['model_revision']} -> {path}", flush=True)


if __name__ == "__main__":
    main()
