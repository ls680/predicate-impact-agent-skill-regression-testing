import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_confirmation import resolve


def test_audit_path_resolution_stays_in_root(tmp_path):
    path = tmp_path / 'x'
    path.write_text('x')
    assert resolve('x', tmp_path) == path
