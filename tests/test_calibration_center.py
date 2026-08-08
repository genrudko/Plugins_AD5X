from __future__ import annotations

import configparser
import importlib.util
import pathlib
import re
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CC = ROOT / "calibration_center"
ENTRY = CC / "calibration_center.cfg"
INSTALLER = CC / "install.sh"
AUDIT = CC / "cc_audit.sh"
MODEL = CC / "model.py"

spec = importlib.util.spec_from_file_location("calibration_center_model", MODEL)
assert spec and spec.loader
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
spec.loader.exec_module(model)


class CalibrationMathTests(unittest.TestCase):
    def test_stable_series(self) -> None:
        result = model.evaluate_samples([0.101, 0.106, 0.099, 0.104, 0.102])
        self.assertAlmostEqual(result.median, 0.102)
        self.assertAlmostEqual(result.spread, 0.007)

    def test_unstable_series_fails_closed(self) -> None:
        with self.assertRaises(model.CalibrationRejected):
            model.evaluate_samples([0.100, 0.101, 0.099, 0.102, 0.145])

    def test_exactly_five_samples(self) -> None:
        with self.assertRaises(model.CalibrationRejected):
            model.evaluate_samples([0.1, 0.1, 0.1])

    def test_reference_delta_sign_and_limit(self) -> None:
        self.assertAlmostEqual(model.reference_delta(0.120, 0.100), 0.020)
        self.assertAlmostEqual(model.reference_delta(0.080, 0.100), -0.020)
        with self.assertRaises(model.CalibrationRejected):
            model.reference_delta(0.500, 0.100)

    def test_mesh_test_modes_do_not_double_apply_profile_delta(self) -> None:
        self.assertAlmostEqual(
            model.runtime_adjust(verified_bias=-0.170, auto_delta=0.025, mesh_test=3),
            -0.170,
        )
        self.assertAlmostEqual(
            model.runtime_adjust(verified_bias=-0.170, auto_delta=0.025, mesh_test=1),
            -0.145,
        )

    def test_verified_bias_is_separate_from_auto_delta(self) -> None:
        bias = model.verified_process_bias(
            current_offset=-0.130,
            base_runtime_offset=0.015,
            runtime_auto_delta=0.025,
        )
        self.assertAlmostEqual(bias, -0.170)
        self.assertAlmostEqual(
            model.initial_verified_process_bias(live_adjust=-0.170), -0.170
        )


class CalibrationConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.core = (CC / "cc_core.cfg").read_text(encoding="utf-8")
        cls.profiles = (CC / "cc_profiles.cfg").read_text(encoding="utf-8")
        cls.measure = (CC / "cc_measure.cfg").read_text(encoding="utf-8")
        cls.print_cfg = (CC / "cc_print.cfg").read_text(encoding="utf-8")
        cls.all_cfg = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(CC.glob("*.cfg"))
        )

    def test_entrypoint_includes_reviewable_modules(self) -> None:
        entry = ENTRY.read_text(encoding="utf-8")
        for filename in ("cc_core.cfg", "cc_profiles.cfg", "cc_measure.cfg", "cc_print.cfg"):
            self.assertIn(f"[include ./{filename}]", entry)

    def test_split_cfg_is_ini_parseable(self) -> None:
        sections: set[str] = set()
        for path in sorted(CC.glob("cc_*.cfg")):
            parser = configparser.RawConfigParser(strict=False, interpolation=None)
            parser.read_string(path.read_text(encoding="utf-8"))
            sections.update(parser.sections())
        for required in (
            "gcode_macro CALIBRATION_CENTER",
            "gcode_macro CC_CALIBRATE",
            "gcode_macro _CC_FINALIZE",
            "gcode_macro CC_APPLY_PROFILE",
            "gcode_macro CC_VERIFY_CURRENT",
            "gcode_macro CC_ROLLBACK",
        ):
            self.assertIn(required, sections)

    def test_exactly_five_probe_cycles(self) -> None:
        block = self.measure.split("[gcode_macro CC_CALIBRATE]", 1)[1].split(
            "[gcode_macro _CC_PREPARE_MEASUREMENTS]", 1
        )[0]
        self.assertEqual(
            re.findall(r"^\s*_CC_MEASURE INDEX=([1-5])\s*$", block, re.M),
            ["1", "2", "3", "4", "5"],
        )
        cycle = self.measure.split("[gcode_macro _CC_MEASURE]", 1)[1].split(
            "[gcode_macro _CC_CAPTURE]", 1
        )[0]
        self.assertLess(cycle.index("LOAD_CELL_TARE"), cycle.index("PROBE"))
        self.assertLess(cycle.index("PROBE"), cycle.index("_CC_CAPTURE"))

    def test_measurement_is_mesh_independent_and_restored(self) -> None:
        self.assertIn("BED_MESH_CLEAR FROM=CALIBRATION_CENTER", self.measure)
        self.assertIn("BED_MESH_PROFILE LOAD={mesh_name}", self.measure)
        self.assertIn("SAVE_GCODE_STATE NAME=cc_calibration", self.measure)
        self.assertIn("RESTORE_GCODE_STATE NAME=cc_calibration MOVE=0", self.measure)

    def test_reject_cleanup_precedes_error(self) -> None:
        finalize = self.measure.split("[gcode_macro _CC_FINALIZE]", 1)[1].split(
            "[gcode_macro _CC_RESTORE_MESH]", 1
        )[0]
        self.assertNotRegex(finalize, r"\{\s*action_raise_error")
        for error in ("_CC_ERROR_INCOMPLETE", "_CC_ERROR_UNSTABLE", "_CC_ERROR_DELTA"):
            self.assertRegex(finalize, rf"_CC_CLEANUP\s+{error}")
        cleanup = self.measure.split("[gcode_macro _CC_CLEANUP]", 1)[1].split(
            "[gcode_macro _CC_ERROR_INCOMPLETE]", 1
        )[0]
        self.assertLess(cleanup.index("TURN_OFF_HEATERS"), cleanup.index("_CC_RESTORE_MESH"))

    def test_profile_stays_unready_until_accepted_series(self) -> None:
        calibrate = self.measure.split("[gcode_macro CC_CALIBRATE]", 1)[1].split(
            "[gcode_macro _CC_PREPARE_MEASUREMENTS]", 1
        )[0]
        self.assertIn("VARIABLE=cc_p{slot}_needs_calibration VALUE=1", calibrate)
        finalize = self.measure.split("[gcode_macro _CC_FINALIZE]", 1)[1].split(
            "[gcode_macro _CC_RESTORE_MESH]", 1
        )[0]
        self.assertIn("VARIABLE=cc_p{slot}_needs_calibration VALUE=0", finalize)
        self.assertIn("spread > st.max_range", finalize)

    def test_profile_switch_requires_recalibration(self) -> None:
        select = self.profiles.split("[gcode_macro CC_PROFILE_SELECT]", 1)[1].split(
            "[gcode_macro CC_PROFILE_RENAME]", 1
        )[0]
        self.assertIn("old_slot != slot", select)
        self.assertIn("VARIABLE=cc_p{slot}_needs_calibration VALUE=1", select)

    def test_print_start_cancels_unready_profile(self) -> None:
        apply = self.print_cfg.split("[gcode_macro CC_APPLY_PROFILE]", 1)[1].split(
            "[gcode_macro CC_FIRST_LAYER_CONTROLS]", 1
        )[0]
        self.assertIn("needs == 1", apply)
        self.assertIn("CANCEL_PRINT", apply)
        self.assertLess(apply.index("needs == 1"), apply.index("_SET_GCODE_OFFSET_FAST"))

    def test_auto_and_user_verified_layers_are_separate(self) -> None:
        for token in (
            "_auto_ref",
            "_verified_ref",
            "_verified_bias",
            "_auto_delta",
            "_prev_verified_ref",
        ):
            self.assertIn(token, self.all_cfg)
        apply = self.print_cfg.split("[gcode_macro CC_APPLY_PROFILE]", 1)[1].split(
            "[gcode_macro CC_FIRST_LAYER_CONTROLS]", 1
        )[0]
        self.assertIn("mesh_test in [3, 4]", apply)
        self.assertIn("cc_auto = 0.0", apply)

    def test_first_verification_uses_deliberate_live_adjustment(self) -> None:
        verify = self.print_cfg.split("[gcode_macro CC_VERIFY_CURRENT]", 1)[1].split(
            "[gcode_macro CC_ROLLBACK]", 1
        )[0]
        self.assertIn("new_bias = st.live_adjust|float", verify)
        self.assertIn("verified_probe_format VALUE={auto_format}", verify)

    def test_forbidden_firmware_and_native_probe_storage_operations_absent(self) -> None:
        forbidden = re.compile(
            r"^\s*(?:Z_OFFSET_APPLY_PROBE|Z_OFFSET_APPLY_ENDSTOP|SAVE_CONFIG|UPDATE_MCU)(?:\s|$)",
            re.M,
        )
        self.assertIsNone(forbidden.search(self.all_cfg))
        self.assertNotIn("Adventurer5M.json", self.all_cfg)
        lower = self.all_cfg.lower()
        self.assertNotIn("/sys/bus/usb", lower)
        self.assertNotIn("flash_mcu", lower)

    def test_failsafe_turns_heaters_off(self) -> None:
        failsafe = self.measure.split("[delayed_gcode _CC_FAILSAFE]", 1)[1]
        self.assertIn("TURN_OFF_HEATERS", failsafe)
        self.assertIn("_CC_RESTORE_MESH", failsafe)


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = INSTALLER.read_text(encoding="utf-8")

    def test_posix_shell_syntax(self) -> None:
        for script in (INSTALLER, AUDIT):
            subprocess.run(["sh", "-n", str(script)], check=True)

    def test_mod_data_only_and_clean_upstream_guard(self) -> None:
        self.assertIn("/opt/config/mod_data/plugins/calibration_center", self.text)
        self.assertIn("/opt/config/base/klipper", self.text)
        self.assertIn("/opt/config/base/moonraker", self.text)
        self.assertIn("upstream уже DIRTY", self.text)
        self.assertNotIn("sed -i", self.text)
        self.assertNotIn("patch -p", self.text)

    def test_unknown_printer_state_fails_closed(self) -> None:
        self.assertIn("Moonraker недоступен; безопасное состояние принтера не подтверждено", self.text)
        self.assertIn("print_stats.state; установка остановлена fail-closed", self.text)

    def test_conflict_safe_user_start_hook_and_update_manager(self) -> None:
        self.assertIn("уже содержит пользовательский _USER_START_PRINT", self.text)
        self.assertIn("CC_APPLY_PROFILE", self.text)
        self.assertIn("[update_manager calibration_center]", self.text)

    def test_backup_rollback_and_state_preserving_uninstall(self) -> None:
        self.assertIn("snapshot_file", self.text)
        self.assertIn("restore_file", self.text)
        self.assertIn("trap", self.text)
        uninstall = self.text.split("uninstall_now()", 1)[1].split("status_now()", 1)[0]
        self.assertIn('rm -rf "$PLUGIN_DIR"', uninstall)
        self.assertNotIn('rm -rf "$STATE_DIR"', uninstall)


if __name__ == "__main__":
    unittest.main()
