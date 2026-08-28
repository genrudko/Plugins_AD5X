import importlib.util
import unittest
from pathlib import Path

PATCHER = Path(__file__).parents[1] / 'integrations/flook32/firmware/apply_moonraker_status_fix.py'
spec = importlib.util.spec_from_file_location('flook32_fw_patch', PATCHER)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class FirmwarePatchTests(unittest.TestCase):
    def test_patch_preserves_crlf_and_removes_only_gate(self):
        data = (b'before\r\n' + mod.OLD_COMMENT + b'\r\n' + mod.OLD_GATE + b'\r\nafter\r\n')
        patched = mod.patch_bytes(data)
        self.assertEqual(patched.count(b'\r\n'), data.count(b'\r\n'))
        self.assertNotIn(mod.OLD_GATE, patched)
        self.assertIn(mod.NEW_COMMENT, patched)
        self.assertIn(mod.NEW_LINE, patched)

    def test_patch_fails_if_upstream_anchor_changes(self):
        with self.assertRaisesRegex(ValueError, 'anchor changed'):
            mod.patch_bytes(b'upstream changed')

if __name__ == '__main__': unittest.main()
