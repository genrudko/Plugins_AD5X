from __future__ import annotations

import configparser
import importlib.util
import pathlib
import re
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CC = ROOT / "calibration_center"
CFG = CC / "calibration_center.cfg"
INSTALLER = CC / "install.sh"
AUDIT = CC / "cc_audit.sh"
MODEL = CC / "model.py"

spec = importlib.util.spec_from_file_location("calibration_center_model", MODEL)
assert spec and spec.loader
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class CalibrationMathTests(unittest.TestCase):
    def test_stable_five_probe_series_is_accepted(self) -> None:
        result = model.evaluate_samples(
            [0.101, 0.106, 0.099, 0.104, 0.102], max_range=0.030
        )
        self.assertAlmostEqual(result.median, 0.102)
        self.assertAlmostEqual(result.spread, 0.007)

    def test_unstable_series_fails_closed(self) -> None:
        with self.assertRaises(model.CalibrationRejected):
            model.evaluate_samples(
                [0.100, 0.101, 0.099, 0.102, 0.145], max_range=0.030
            )

    def test_exactly_five_measurements_are_required(self) -> None:
        with self.assertRaises(model.CalibrationRejected):
            model.evaluate_samples([0.1, 0.1, 0.1], max_range=0.030)

    def test_reference_delta_matches_upstream_sign(self) -> None:
        self.assertAlmostEqual(
            model.reference_delta(0.120, 0.100, max_delta=0.300), 0.020
        )
        self.assertAlmostEqual(
            model.reference_delta(0.080, 0.100, max_delta=0.300), -0.020
        )

    def test_large_reference_jump_is_rejected(self) -> None:
        with self.assertRaises(model.CalibrationRejected):
            model.reference_delta(0.500, 0.100, max_delta=0.300)

    def test_mesh_test_3_4_does_not_double_apply_auto_delta(self) -> None:
        self.assertAlmostEqual(
            model.runtime_adjust(
                verified_bias=-0.170, auto_delta=0.025, mesh_test=3
            ),
            -0.170,
        )
        self.assertAlmostEqual(
            model.runtime_adjust(
                verified_bias=-0.170, auto_delta=0.025, mesh_test=4
            ),
            -0.170,
        )

    def test_mesh_test_1_2_layers_last_calibration_delta(self) -> None:
        self.assertAlmostEqual(
            model.runtime_adjust(
                verified_bias=-0.170, auto_delta=0.025, mesh_test=1
            ),
            -0.145,
        )

    def test_verified_bias_is_separate_from_runtime_auto_delta(self) -> None:
        bias = model.verified_process_bias(
            current_offset=-0.130,
            base_runtime_offset=0.015,
            runtime_auto_delta=0.025,
        )
        self.assertAlmostEqual(bias, -0.170)

    def test_initial_profile_bias_is_deliberate_live_adjustment(self) -> None:
        self.assertAlmostEqual(
            model.initial_verified_process_bias(live_adjust=-0.170), -0.170
        )


class CalibrationConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = CFG.read_text(encoding="utf-8")

    def test_cfg_parses_as_klipper_style_ini(self) -> None:
        parser = configparser.RawConfigParser(strict=False, interpolation=None)
        parser.read_string(self.text)
        required = {
            "gcode_macro CALIBRATION_CENTER",
            "gcode_macro CC_CALIBRATE",
            "gcode_macro _CC_MEASURE",
            "gcode_macro _CC_CAPTURE",
            "gcode_macro _CC_FINALIZE",
            "gcode_macro CC_APPLY_PROFILE",
            "gcode_macro CC_VERIFY_CURRENT",
            "gcode_macro CC_ROLLBACK",
        }
        self.assertTrue(required.issubset(set(parser.sections())))

    def test_automatic_path_runs_five_measurements(self) -> None:
        block = self.text.split("[gcode_macro CC_CALIBRATE]", 1)[1].split(
            "[gcode_macro _CC_PREPARE_MEASUREMENTS]", 1
        )[0]
        calls = re.findall(r"^\s*_CC_MEASURE INDEX=([1-5])\s*$", block, re.M)
        self.assertEqual(calls, ["1", "2", "3", "4", "5"])

    def test_each_measurement_tares_before_probe(self) -> None:
        block = self.text.split("[gcode_macro _CC_MEASURE]", 1)[1].split(
            "[gcode_macro _CC_CAPTURE]", 1
        )[0]
        self.assertLess(block.index("LOAD_CELL_TARE"), block.index("PROBE"))
        self.assertLess(block.index("PROBE"), block.index("_CC_CAPTURE"))

    def test_unstable_result_is_rejected_before_auto_ref_save(self) -> None:
        block = self.text.split("[gcode_macro _CC_FINALIZE]", 1)[1].split(
            "[delayed_gcode _CC_FAILSAFE]", 1
        )[0]
        self.assertIn("spread > st.max_range", block)
        self.assertIn("calibration_reject", block)
        self.assertIn("VARIABLE=cc_p{slot}_auto_ref", block)
        self.assertLess(block.index("spread > st.max_range"), block.index("VARIABLE=cc_p{slot}_auto_ref"))

    def test_profile_model_keeps_auto_and_verified_separate(self) -> None:
        for token in (
            "_auto_ref",
            "_verified_ref",
            "_verified_bias",
            "_auto_delta",
            "_prev_verified_ref",
            "_prev_verified_bias",
        ):
            self.assertIn(token, self.text)

    def test_stock_calibration_storage_is_not_written(self) -> None:
        forbidden_commands = re.compile(
            r"^\s*(?:Z_OFFSET_APPLY_PROBE|Z_OFFSET_APPLY_ENDSTOP|SAVE_CONFIG|UPDATE_MCU)(?:\s|$)",
            re.M,
        )
        self.assertIsNone(forbidden_commands.search(self.text))
        self.assertNotIn("Adventurer5M.json", self.text)

    def test_no_usb_reset_or_firmware_flash(self) -> None:
        operational = self.text.lower()
        self.assertNotIn("/sys/bus/usb", operational)
        self.assertNotIn("unbind", operational)
        self.assertNotIn("bind", operational)
        self.assertNotIn("flash_mcu", operational)

    def test_print_busy_guards_exist(self) -> None:
        self.assertGreaterEqual(self.text.count("['printing', 'paused']"), 4)

    def test_failsafe_turns_heaters_off(self) -> None:
        block = self.text.split("[delayed_gcode _CC_FAILSAFE]", 1)[1].split(
            "[gcode_macro CC_APPLY_PROFILE]", 1
        )[0]
        self.assertIn("TURN_OFF_HEATERS", block)


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = INSTALLER.read_text(encoding="utf-8")

    def test_shell_scripts_have_valid_posix_shell_syntax(self) -> None:
        for script in (INSTALLER, AUDIT):
            subprocess.run(["sh", "-n", str(script)], check=True)

    def test_installer_uses_mod_data_not_upstream_patches(self) -> None:
        self.assertIn("/opt/config/mod_data/plugins/calibration_center", self.text)
        self.assertIn("/opt/config/mod_data/plugins.cfg", self.text)
        self.assertNotIn("sed -i", self.text)
        self.assertNotIn("patch -p", self.text)

    def test_installer_checks_all_upstream_repositories_clean(self) -> None:
        self.assertIn("/opt/config/mod", self.text)
        self.assertIn("/opt/config/base/klipper", self.text)
        self.assertIn("/opt/config/base/moonraker", self.text)
        self.assertIn("upstream уже DIRTY", self.text)

    def test_user_start_hook_is_conflict_safe(self) -> None:
        self.assertIn("CALIBRATION_CENTER_START_HOOK_BEGIN", self.text)
        self.assertIn("уже содержит пользовательский _USER_START_PRINT", self.text)
        self.assertIn("CC_APPLY_PROFILE", self.text)

    def test_install_has_backup_and_rollback_trap(self) -> None:
        self.assertIn("snapshot_file", self.text)
        self.assertIn("restore_file", self.text)
        self.assertIn("trap", self.text)

    def test_update_manager_is_independent(self) -> None:
        self.assertIn("[update_manager calibration_center]", self.text)
        self.assertIn("path: $PLUGIN_DIR", self.text)

    def test_uninstall_does_not_delete_profile_state(self) -> None:
        uninstall = self.text.split("uninstall_now()", 1)[1].split(
            "status_now()", 1
        )[0]
        self.assertIn('rm -rf "$PLUGIN_DIR"', uninstall)
        self.assertNotIn('rm -rf "$STATE_DIR"', uninstall)


if __name__ == "__main__":
    unittest.main()
