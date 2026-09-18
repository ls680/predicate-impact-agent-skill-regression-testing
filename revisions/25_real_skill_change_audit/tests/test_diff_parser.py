from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_history import edit_flags, parse_zero_context


def test_structural_edit_flags():
    diff = '''@@ -1,2 +1,2 @@
- run tool --old value
- verify output
+ run tool --new value
+ verify output
'''
    flags = edit_flags(parse_zero_context(diff))
    assert flags['deletion_present']
    assert flags['mixed_replacement_hunk']
    assert flags['similar_line_replacement_candidate']
    assert flags['line_relocation_candidate']
