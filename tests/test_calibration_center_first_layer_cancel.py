from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CC = ROOT / "calibration_center"
ENTRY = CC / "calibration_center.cfg"
WATCHDOG = CC / "cc_first_layer_watchdog.cfg"
AUDIT = CC / "cc_audit.sh"


class FirstLayerExternalCancelSafetyTests(unittest.TestCase):
    def test_watchdog_is_included_but_not_idle_armed(self) -> None:
        entry = ENTRY.read_text(encoding="utf-8")
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("[include ./cc_first_layer_watchdog.cfg]", entry)
        self.assertIn("[delayed_gcode _CC_FIRST_LAYER_WATCHDOG]", watchdog)
        self.assertNotIn("initial_duration:", watchdog)

    def test_generated_job_arms_watchdog_only_after_test_begin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                ["sh", str(AUDIT), "generate-first-layer", tmp, "PLA", "210", "60", "0.4"],
                check=True,
                capture_output=True,
                text=True,
            )
            text = (pathlib.Path(tmp) / "Calibration_Center_First_Layer.gcode").read_text(
                encoding="utf-8"
            )

        begin = text.index("CC_FIRST_LAYER_TEST_BEGIN")
        arm = text.index("UPDATE_DELAYED_GCODE ID=_CC_FIRST_LAYER_WATCHDOG DURATION=2")
        layer = text.index("SET_PRINT_STATS_INFO TOTAL_LAYER=1 CURRENT_LAYER=1")
        self.assertLess(begin, arm)
        self.assertLess(arm, layer)

    def test_external_cancel_restores_only_temporary_live_delta(self) -> None:
        watchdog = WATCHDOG.read_text(encoding="utf-8")
        self.assertIn("first_layer_active|int == 1", watchdog)
        self.assertIn("print_state in ['printing', 'paused']", watchdog)
        self.assertIn("UPDATE_DELAYED_GCODE ID=_CC_FIRST_LAYER_WATCHDOG DURATION=2", watchdog)
        self.assertIn("_CC_FIRST_LAYER_RESTORE_RUNTIME", watchdog)
        self.assertIn("VARIABLE=first_layer_active VALUE=0", watchdog)
        self.assertIn("VARIABLE=first_layer_verified VALUE=0", watchdog)
        self.assertIn("VARIABLE=first_layer_review VALUE=0", watchdog)
        self.assertNotIn("CANCEL_PRINT", watchdog)
        self.assertNotIn("SAVE_VARIABLE", watchdog)


if __name__ == "__main__":
    unittest.main()
