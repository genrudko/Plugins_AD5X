from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CC = ROOT / "calibration_center"
PRINT_CFG = CC / "cc_print.cfg"
AUDIT = CC / "cc_audit.sh"


class FirstLayerUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PRINT_CFG.read_text(encoding="utf-8")

    def test_beginner_material_presets_are_exposed(self) -> None:
        for material in ("PLA", "PETG", "ABS", "ASA", "TPU"):
            self.assertIn(f"CC_FIRST_LAYER_PRESET MATERIAL={material}", self.text)
        for token in (
            "material == 'PLA'",
            "nozzle_temp = 210",
            "bed_temp = 60",
            "material == 'PETG'",
            "nozzle_temp = 240",
            "bed_temp = 75",
            "material == 'ABS'",
            "material == 'ASA'",
            "nozzle_temp = 250",
            "bed_temp = 100",
            "material == 'TPU'",
            "nozzle_temp = 225",
            "bed_temp = 50",
        ):
            self.assertIn(token, self.text)

    def test_built_in_test_uses_real_virtual_sd_print_path(self) -> None:
        block = self.text.split("[gcode_macro CC_FIRST_LAYER_TEST]", 1)[1].split(
            "[gcode_macro CC_FIRST_LAYER_TEST_BEGIN]", 1
        )[0]
        self.assertIn("printer.configfile.settings.virtual_sdcard.path", block)
        self.assertIn("printer.bed_mesh.profile_name", block)
        self.assertIn("CMD=calibration_center_first_layer", block)
        self.assertIn('SDCARD_PRINT_FILE FILENAME="Calibration_Center_First_Layer.gcode"', block)
        self.assertIn("state not in [1, 2]", block)
        self.assertIn("NOZZLE_TEMP вне диапазона 170..280 C", block)
        self.assertIn("BED_TEMP вне диапазона 0..110 C", block)

    def test_generated_test_has_live_controls_and_explicit_accept_abort(self) -> None:
        for token in (
            "CC_FIRST_LAYER_TEST_BEGIN",
            "CC_LIVE_Z DELTA=-0.01",
            "CC_LIVE_Z DELTA=0.01",
            "CC_FIRST_LAYER_ACCEPT",
            "CC_FIRST_LAYER_ABORT",
            "first_layer_verified VALUE=1",
        ):
            self.assertIn(token, self.text)


class FirstLayerGeneratorTests(unittest.TestCase):
    def _generate(
        self,
        directory: pathlib.Path,
        material: str = "PLA",
        nozzle_temp: str = "210",
        bed_temp: str = "60",
        nozzle: str = "0.4",
    ) -> pathlib.Path:
        subprocess.run(
            [
                "sh",
                str(AUDIT),
                "generate-first-layer",
                str(directory),
                material,
                nozzle_temp,
                bed_temp,
                nozzle,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        return directory / "Calibration_Center_First_Layer.gcode"

    def test_generator_creates_real_start_print_job_for_04_nozzle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._generate(pathlib.Path(tmp))
            text = path.read_text(encoding="utf-8")

        self.assertIn("START_PRINT EXTRUDER_TEMP=210.0 BED_TEMP=60.0 SKIP_LEVELING=True", text)
        self.assertIn("CC_FIRST_LAYER_TEST_BEGIN MATERIAL=PLA", text)
        self.assertIn("SET_PRINT_STATS_INFO TOTAL_LAYER=1 CURRENT_LAYER=1", text)
        self.assertIn("G1 Z0.200 F600", text)
        self.assertIn("M83", text)
        self.assertIn("CC_FIRST_LAYER_TEST_FILE_END", text)
        self.assertTrue(text.rstrip().endswith("END_PRINT"))
        extrusion_lines = [line for line in text.splitlines() if " E" in line and line.startswith("G1 X")]
        self.assertGreater(len(extrusion_lines), 30)

    def test_generator_scales_layer_height_for_08_nozzle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._generate(
                pathlib.Path(tmp),
                material="ASA",
                nozzle_temp="250",
                bed_temp="100",
                nozzle="0.8",
            )
            text = path.read_text(encoding="utf-8")

        self.assertIn("material=ASA nozzle=0.800", text)
        self.assertIn("G1 Z0.400 F600", text)
        extrusion_lines = [line for line in text.splitlines() if " E" in line and line.startswith("G1 X")]
        self.assertGreater(len(extrusion_lines), 15)
        self.assertLess(len(extrusion_lines), 30)

    def test_generator_rejects_unsafe_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    "sh",
                    str(AUDIT),
                    "generate-first-layer",
                    tmp,
                    "PLA",
                    "500",
                    "60",
                    "0.4",
                ],
                capture_output=True,
                text=True,
            )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("outside 170..280", proc.stderr)


if __name__ == "__main__":
    unittest.main()
