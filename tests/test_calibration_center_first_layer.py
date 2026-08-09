from __future__ import annotations

import pathlib
import re
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CC = ROOT / "calibration_center"
PRINT_CFG = CC / "cc_print.cfg"
TRANSIENT_CFG = CC / "cc_transient_z.cfg"
CORE_CFG = CC / "cc_core.cfg"
AUDIT = CC / "cc_audit.sh"


class FirstLayerUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = PRINT_CFG.read_text(encoding="utf-8")
        cls.transient = TRANSIENT_CFG.read_text(encoding="utf-8")
        cls.core = CORE_CFG.read_text(encoding="utf-8")

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

    def test_live_controls_show_global_profile_and_test_layers(self) -> None:
        controls = self.text.split("[gcode_macro CC_FIRST_LAYER_CONTROLS]", 1)[1].split(
            "[gcode_macro CC_FIRST_LAYER_PRESET]", 1
        )[0]
        self.assertIn("Глобальный Z-Mod:", controls)
        self.assertIn("CC профиль:", controls)
        self.assertIn("test ΔZ:", controls)
        self.assertIn("не изменяет", controls)
        self.assertIn("±0.10 mm", controls)

    def test_live_button_delegates_to_transient_step_and_reopens_prompt(self) -> None:
        live = self.text.split("[gcode_macro CC_LIVE_Z]", 1)[1].split(
            "[gcode_macro CC_FIRST_LAYER_TEST_REVIEW]", 1
        )[0]
        self.assertIn("_CC_FIRST_LAYER_TRANSIENT_STEP DELTA={delta}", live)
        self.assertLess(
            live.index("_CC_FIRST_LAYER_TRANSIENT_STEP"),
            live.index("CC_FIRST_LAYER_CONTROLS"),
        )
        self.assertNotIn("_SET_GCODE_OFFSET_FAST", live)

    def test_transient_step_uses_g92_and_immediate_relative_z_move(self) -> None:
        step = self.transient.split("[gcode_macro _CC_FIRST_LAYER_TRANSIENT_STEP]", 1)[1].split(
            "[gcode_macro _CC_FIRST_LAYER_RESTORE_RUNTIME]", 1
        )[0]
        self.assertIn("G92 Z={z - delta}", step)
        self.assertIn("G91", step)
        self.assertIn("G1 Z{delta} F300", step)
        self.assertIn("G90", step)
        self.assertIn("new_live < -down_limit or new_live > 0.100", step)
        self.assertIn("VARIABLE=live_adjust VALUE={new_live}", step)

    def test_review_pause_and_origin_restore_are_explicit(self) -> None:
        review = self.text.split("[gcode_macro CC_FIRST_LAYER_TEST_REVIEW]", 1)[1].split(
            "[gcode_macro CC_VERIFY_CURRENT]", 1
        )[0]
        self.assertIn("VARIABLE=first_layer_review VALUE=1", review)
        self.assertIn("PAUSE", review)
        self.assertIn("CC_FIRST_LAYER_CONTROLS", review)

        restore = self.transient.split("[gcode_macro _CC_FIRST_LAYER_RESTORE_RUNTIME]", 1)[1].split(
            "[delayed_gcode _CC_FIRST_LAYER_WATCHDOG]", 1
        )[0]
        self.assertIn("G92 Z={z + live}", restore)
        self.assertIn("VARIABLE=live_adjust VALUE=0.0", restore)
        self.assertNotIn("SET_GCODE_OFFSET", restore)

        for macro in ("CC_FIRST_LAYER_ACCEPT", "CC_FIRST_LAYER_ABORT", "CC_FIRST_LAYER_TEST_FILE_END"):
            block = self.text.split(f"[gcode_macro {macro}]", 1)[1]
            if macro != "CC_FIRST_LAYER_TEST_FILE_END":
                block = block.split("[gcode_macro", 1)[0]
            self.assertIn("_CC_FIRST_LAYER_RESTORE_RUNTIME", block)

    def test_only_review_pause_can_save_user_verified(self) -> None:
        verify = self.text.split("[gcode_macro CC_VERIFY_CURRENT]", 1)[1].split(
            "[gcode_macro CC_FIRST_LAYER_ACCEPT]", 1
        )[0]
        self.assertIn("builtin_review", verify)
        self.assertIn("print_state == 'paused'", verify)
        self.assertIn("if not builtin_review", verify)
        self.assertIn("new_bias = st.live_adjust|float", verify)
        self.assertIn("new_bias = old_bias + st.live_adjust|float", verify)
        self.assertIn("verified_global_z VALUE={global_z}", verify)

    def test_helix_critical_buttons_use_short_labels(self) -> None:
        self.assertIn("action:prompt_button Первый слой|CC_FIRST_LAYER_CONTROLS", self.core)
        self.assertNotIn("action:prompt_button Проверка первого слоя|", self.core)
        for label in ("Сохранить|CC_FIRST_LAYER_ACCEPT", "Без сохранения|CC_FIRST_LAYER_ABORT"):
            self.assertIn(label, self.text)


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

    def _geometry(self, text: str) -> tuple[float, float, float]:
        match = re.search(
            r"layer_height=([0-9.]+) line_width=([0-9.]+) line_spacing=([0-9.]+)",
            text,
        )
        self.assertIsNotNone(match)
        assert match is not None
        return tuple(float(value) for value in match.groups())

    def test_generator_creates_slicer_like_solid_job_for_04_nozzle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = self._generate(pathlib.Path(tmp))
            text = path.read_text(encoding="utf-8")

        self.assertIn("START_PRINT EXTRUDER_TEMP=210.0 BED_TEMP=60.0", text)
        self.assertNotIn("SKIP_LEVELING", text)
        self.assertIn("CC_FIRST_LAYER_TEST_BEGIN MATERIAL=PLA", text)
        self.assertIn("SET_PRINT_STATS_INFO TOTAL_LAYER=1 CURRENT_LAYER=1", text)
        self.assertIn("G1 Z0.200 F600", text)
        self.assertIn("M220 S100", text)
        self.assertIn("M221 S100", text)
        self.assertIn("M83", text)
        self.assertLess(text.index("CC_FIRST_LAYER_TEST_REVIEW"), text.index("CC_FIRST_LAYER_TEST_FILE_END"))
        self.assertTrue(text.rstrip().endswith("END_PRINT"))

        layer, width, spacing = self._geometry(text)
        self.assertAlmostEqual(layer, 0.200, places=3)
        self.assertAlmostEqual(width, 0.448, places=3)
        self.assertAlmostEqual(spacing, 0.405, places=3)
        self.assertLess(spacing, width)

        x_extrusion = [line for line in text.splitlines() if line.startswith("G1 X") and " E" in line]
        y_connectors = [line for line in text.splitlines() if line.startswith("G1 Y") and " E" in line]
        self.assertGreater(len(x_extrusion), 40)
        self.assertEqual(len(y_connectors), len(x_extrusion) - 1)

    def test_generator_scales_geometry_for_08_nozzle(self) -> None:
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
        layer, width, spacing = self._geometry(text)
        self.assertAlmostEqual(layer, 0.400, places=3)
        self.assertAlmostEqual(width, 0.896, places=3)
        self.assertAlmostEqual(spacing, 0.810, places=3)
        self.assertLess(spacing, width)
        extrusion_lines = [line for line in text.splitlines() if line.startswith("G1 X") and " E" in line]
        self.assertGreater(len(extrusion_lines), 20)
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
