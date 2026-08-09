from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CC = ROOT / "calibration_center"
ENTRY = CC / "calibration_center.cfg"
TRANSIENT = CC / "cc_transient_z.cfg"
AUDIT = CC / "cc_audit.sh"


class FirstLayerExternalCancelSafetyTests(unittest.TestCase):
    def test_transient_layer_is_included_and_watchdogs_are_not_idle_armed(self) -> None:
        entry = ENTRY.read_text(encoding="utf-8")
        transient = TRANSIENT.read_text(encoding="utf-8")
        self.assertIn("[include ./cc_transient_z.cfg]", entry)
        self.assertIn("[delayed_gcode _CC_FIRST_LAYER_WATCHDOG]", transient)
        self.assertIn("[delayed_gcode _CC_PROFILE_ORIGIN_WATCHDOG]", transient)
        self.assertNotIn("initial_duration:", transient)

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

    def test_external_cancel_restores_only_g92_test_origin(self) -> None:
        transient = TRANSIENT.read_text(encoding="utf-8")
        watchdog = transient.split("[delayed_gcode _CC_FIRST_LAYER_WATCHDOG]", 1)[1]
        self.assertIn("first_layer_active|int == 1", watchdog)
        self.assertIn("print_state in ['printing', 'paused']", watchdog)
        self.assertIn("UPDATE_DELAYED_GCODE ID=_CC_FIRST_LAYER_WATCHDOG DURATION=2", watchdog)
        self.assertIn("_CC_FIRST_LAYER_RESTORE_RUNTIME", watchdog)
        self.assertIn("VARIABLE=first_layer_active VALUE=0", watchdog)
        self.assertIn("VARIABLE=first_layer_verified VALUE=0", watchdog)
        self.assertIn("VARIABLE=first_layer_review VALUE=0", watchdog)
        self.assertNotIn("CANCEL_PRINT", watchdog)
        self.assertNotIn("SAVE_VARIABLE", watchdog)

        restore = transient.split("[gcode_macro _CC_FIRST_LAYER_RESTORE_RUNTIME]", 1)[1].split(
            "[delayed_gcode _CC_FIRST_LAYER_WATCHDOG]", 1
        )[0]
        self.assertIn("G92 Z={z + live}", restore)
        self.assertNotIn("SET_GCODE_OFFSET", restore)

    def test_profile_origin_cleanup_is_event_scoped(self) -> None:
        transient = TRANSIENT.read_text(encoding="utf-8")
        watchdog = transient.split("[delayed_gcode _CC_PROFILE_ORIGIN_WATCHDOG]", 1)[1].split(
            "[gcode_macro _CC_FIRST_LAYER_TRANSIENT_STEP]", 1
        )[0]
        self.assertIn("profile_origin_adjust", watchdog)
        self.assertIn("print_state in ['printing', 'paused']", watchdog)
        self.assertIn("DURATION=5", watchdog)
        self.assertIn("_CC_PROFILE_TRANSIENT_RESTORE", watchdog)
        self.assertNotIn("initial_duration", watchdog)


if __name__ == "__main__":
    unittest.main()
