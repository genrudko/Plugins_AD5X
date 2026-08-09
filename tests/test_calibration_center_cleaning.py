from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CC = ROOT / "calibration_center"


class CalibrationCenterCleaningRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.core = (CC / "cc_core.cfg").read_text(encoding="utf-8")
        cls.measure = (CC / "cc_measure.cfg").read_text(encoding="utf-8")

    def test_final_low_temperature_rubber_wipe_precedes_measurements(self) -> None:
        block = self.measure.split("[gcode_macro CC_CALIBRATE]", 1)[1].split(
            "[gcode_macro _CC_PREPARE_MEASUREMENTS]", 1
        )[0]
        self.assertIn("_ORIG_CLEAR_NOZZLE", block)
        self.assertIn("TEMPERATURE_WAIT SENSOR=extruder", block)
        self.assertNotIn("_START_PRECLEAR BED={bed_temp} EXTRUDER={measure_temp}", block)
        self.assertIn("G1 Z20 F600", block)
        self.assertIn("_GOTO_TRASH", block)
        self.assertIn("_CLEAR_REZINA CLEAR_NOZ=1", block)
        self.assertIn("_CC_MEASURE INDEX=1", block)
        self.assertLess(block.index("_ORIG_CLEAR_NOZZLE"), block.index("_CLEAR_REZINA CLEAR_NOZ=1"))
        self.assertLess(block.index("_CLEAR_REZINA CLEAR_NOZ=1"), block.index("_CC_MEASURE INDEX=1"))
        self.assertIn("final_rubber_wipe", block)

    def test_unset_repeatability_is_not_rendered_as_9999_mm(self) -> None:
        self.assertIn("quality >= 9000.0", self.core)
        self.assertIn("принятая повторяемость: нет данных", self.core)


if __name__ == "__main__":
    unittest.main()
