"""Run the audited R23 healthy-reference collector with R24-local frozen inputs."""
from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path

REVISION = Path(__file__).resolve().parent
ROOT = REVISION.parents[1]
source = ROOT / 'revisions/23_reserved_confirmation/collect_oracles.py'
expected_source_sha256 = '9a541fe2088cd01945056901d76dceaa1c6c952d1c968b0f1f01771bd5315d41'
if hashlib.sha256(source.read_bytes()).hexdigest() != expected_source_sha256:
    raise RuntimeError('Pinned R23 collector source changed')
module_spec = importlib.util.spec_from_file_location('r23_collect_oracles', source)
module = importlib.util.module_from_spec(module_spec)
module_spec.loader.exec_module(module)
module.REVISION = REVISION
module.ROOT = ROOT


if __name__ == '__main__':
    module.main()
