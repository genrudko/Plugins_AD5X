import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / 'integrations/flook32/scripts/migrate_cfg.py'
spec = importlib.util.spec_from_file_location('flook_cfg_migrate', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ConfigMigrationTests(unittest.TestCase):
    def run_case(self, content):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'flook32.cfg'
            p.write_bytes(content)
            result = mod.migrate(p)
            return result, p.read_bytes()

    def test_hides_only_flook32_chamber_sensor(self):
        src = (b'[flook32]\n\n[temperature_sensor chamber]\n'
               b'sensor_type: flook32\nreport_interval: 10\n')
        result, out = self.run_case(src)
        self.assertEqual(result, 'migrated')
        self.assertIn(b'[temperature_sensor _flook32_chamber]\n', out)
        self.assertNotIn(b'[temperature_sensor chamber]\n', out)
        self.assertIn(b'report_interval: 10\n', out)

    def test_preserves_crlf(self):
        src = (b'[flook32]\r\n\r\n[temperature_sensor chamber]\r\n'
               b'sensor_type: flook32\r\n')
        result, out = self.run_case(src)
        self.assertEqual(result, 'migrated')
        self.assertIn(b'[temperature_sensor _flook32_chamber]\r\n', out)
        self.assertNotIn(b'\n', out.replace(b'\r\n', b''))

    def test_does_not_touch_unrelated_chamber_sensor(self):
        src = b'[temperature_sensor chamber]\nsensor_type: Generic 3950\n'
        result, out = self.run_case(src)
        self.assertEqual(result, 'not-applicable')
        self.assertEqual(out, src)

    def test_is_idempotent(self):
        src = b'[temperature_sensor _flook32_chamber]\nsensor_type: flook32\n'
        result, out = self.run_case(src)
        self.assertEqual(result, 'already-hidden')
        self.assertEqual(out, src)

    def test_rejects_ambiguous_sections(self):
        src = (b'[temperature_sensor chamber]\nsensor_type: flook32\n'
               b'[temperature_sensor chamber]\nsensor_type: flook32\n')
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'flook32.cfg'
            p.write_bytes(src)
            with self.assertRaisesRegex(RuntimeError, 'multiple'):
                mod.migrate(p)


if __name__ == '__main__':
    unittest.main()
