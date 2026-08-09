from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "calibration_center" / "install.sh"


class CalibrationCenterRuntimePreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = INSTALLER.read_text(encoding="utf-8")
        cls.compat = cls.text.split("compatibility_check()", 1)[1].split(
            "check_user_hook_conflict()", 1
        )[0]

    def test_compatibility_uses_loaded_klipper_runtime(self) -> None:
        self.assertIn("/printer/objects/query?configfile", self.compat)
        self.assertIn("/printer/gcode/help", self.compat)
        self.assertIn("RUNTIME_CONFIG", self.compat)
        self.assertIn("GCODE_HELP", self.compat)

    def test_compatibility_does_not_treat_zmod_git_checkout_as_loaded_cfg(self) -> None:
        self.assertNotIn('BASE="/opt/config/mod"', self.compat)
        self.assertNotIn("grep -R -q", self.compat)

    def test_required_runtime_contract_is_fail_closed(self) -> None:
        for token in (
            "gcode_macro _user_start_print",
            "gcode_macro _orig_clear_nozzle",
            "_GOTO_TRASH",
            "_CLEAR_REZINA",
            "gcode_macro _set_gcode_offset_fast",
            "LOAD_CELL_TARE",
            "gcode_macro _client_variable",
        ):
            self.assertIn(token, self.compat)
        self.assertNotIn('require_runtime_token "_START_PRECLEAR"', self.compat)
        self.assertNotIn("gcode_macro _pre_clear_nozzle", self.compat)
        self.assertIn("gcode_macro _g28", self.compat)
        self.assertIn("gcode_macro _home", self.compat)
        self.assertIn("fail \"Z-Mod runtime:", self.compat)


if __name__ == "__main__":
    unittest.main()
