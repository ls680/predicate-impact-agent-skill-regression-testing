"""Use the path-confined R23 hash and roster audit for R24 artifacts."""
from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
source = ROOT / 'revisions/23_reserved_confirmation/audit_confirmation.py'
expected_source_sha256 = 'e8024658e8e0d5df9d9b28e03eca9ec79e6d79e53307c39686edd1e821da0f56'
if hashlib.sha256(source.read_bytes()).hexdigest() != expected_source_sha256:
    raise RuntimeError('Pinned R23 audit source changed')
module_spec = importlib.util.spec_from_file_location('r23_audit_confirmation', source)
module = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)
resolve = module.resolve


if __name__ == '__main__':
    module.main()
