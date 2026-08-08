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
CFG_FILES = sorted(CC.glob("*.cfg"))
INSTALLER = CC / "install.sh"
AUDIT = CC / "cc_audit.sh"
MODEL = CC / "model.py"

spec = importlib.util.spec_from_file_location("calibration_center_model", MODEL)
assert spec and spec.loader
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
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

    def test_mesh_test_3_4_does_not_double_apply_profile_delta(self) -> None:
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
        cls.text = "\n\n".join(path.read_text(encoding="utf-8") for path in CFG_FILES)
        cls.measure = (CC / "cc_measure.cfg").read_text(encoding="utf-8")
        cls.print_cfg = (CC / "cc_print.cfg").read_text(encoding="utf-8")
        cls.profiles = (CC / "cc_profiles.cfg").read_text(encoding="utf-8")

    def test_entrypoint_includes_split_modules(self) -> None:
        entry = ENTRY.read_text(encoding="utf-8")
        for filename in (
            "cc_core.cfg",
            "cc_profiles.cfg",
            "cc_measure.cfg",
            "cc_print.cfg",
        ):
            self.assertIn(f"[include ./{filename}]", entry)

    def test_each_functional_cfg_parses_as_klipper_style_ini(self) -> None:
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
        sections: set[str] = set()
        for path in sorted(CC.glob("cc_*.cfg")):
            parser = configparser.RawConfigParser(strict=False, interpolation=None)
            parser.read_string(path.read_text(encoding="utf-8"))
            sections.update(parser.sections())
        self.assertTrue(required.issubset(sections))

    def test_automatic_path_runs_five_measurements(self) -> None:
        block = self.measure.split("[gcode_macro CC_CALIBRATE]", 1)[1].split(
            "[gcode_macro _CC_PREPARE_MEASUREMENTS]", 1
        )[0]
        calls = re.findall(r"^\s*_CC_MEASURE INDEX=([1-5])\s*$", block, re.M)
        self.assertEqual(calls, ["1", "2", "3", "4", "5"])

    def test_each_measurement_tares_before_probe(self) -> None:
        block = self.measure.split("[gcode_macro _CC_MEASURE]", 1)[1].split(
            "[gcode_macro _CC_CAPTURE]", 1
        )[0]
        self.assertLess(block.index("LOAD_CELL_TARE"), block.index("PROBE"))
        self.assertLess(block.index("PROBE"), block.index("_CC_CAPTURE"))

    def test_measurement_isolated_from_loaded_bed_mesh_and_restored(self) -> None:
        calibrate = self.measure.split("[gcode_macro CC_CALIBRATE]", 1)[1].split(
            "[gcode_macro _CC_PREPARE_MEASUREMENTS]", 1
        )[0]
        restore = self.measure.split("[gcode_macro _CC_RESTORE_MESH]", 1)[1].split(
            "[gcode_macro _CC_CLEANUP]", 1
        )[0]
        self.assertIn("BED_MESH_CLEAR FROM=CALIBRATION_CENTER", calibrate)
        self.assertIn("BED_MESH_PROFILE LOAD={mesh_name}", restore)

    def test_reject_cleanup_executes_before_separate_error_macro(self) -> None:
        finalize = self.measure.split("[gcode_macro _CC_FINALIZE]", 1)[1].split(
            "[gcode_macro _CC_RESTORE_MESH]", 1
        )[0]
        self.assertNotRegex(finalize, r"\{\s*action_raise_error")
        self.assertIn("_CC_CLEANUP\n        _CC_ERROR_INCOMPLETE", finalize)
        self.assertIn("_CC_CLEANUP\n        _CC_ERROR_UNSTABLE", finalize)
        self.assertIn("_CC_CLEANUP\n        _CC_ERROR_DELTA", finalize)

    def test_unstable_result_is_rejected_before_auto_ref_save(self) -> None:
        finalize = self.measure.split("[gcode_macro _CC_FINALIZE]", 1)[1].split(
            "[gcode_macro _CC_RESTORE_MESH]", 1
        )[0]
        self.assertIn("spread > st.max_range", finalize)
        self.assertIn("calibration_reject", finalize)
        self.assertIn("VARIABLE=cc_p{slot}_auto_ref", finalize)
        self.assertLess(
            finalize.index("spread > st.max_range"),
            finalize.index("VARIABLE=cc_p{slot}_auto_ref"),
        )

    def test_rejected_remeasure_preserves_existing_verified_profile(self) -> None:
        finalize = self.measure.split("[gcode_macro _CC_FINALIZE]", 1)[1].split(
            "[gcode_macro _CC_RESTORE_MESH]", 1
        )[0]
        self.assertIn("verified_ref >= 9000.0", finalize)
        self.assertIn("SAVE_VARIABLE VARIABLE=cc_p{slot}_state VALUE=3", finalize)
        delta_branch = finalize.split(
            "verified_ref < 9000.0 and (median - verified_ref)|abs", 1
        )[1].split("{% else %}", 1)[0]
        self.assertNotIn("VARIABLE=cc_p{slot}_state VALUE=3", delta_branch)

    def test_calibration_marks_profile_pending_until_full_series_accepts(self) -> None:
        calibrate = self.measure.split("[gcode_macro CC_CALIBRATE]", 1)[1].split(
            "[gcode_macro _CC_PREPARE_MEASUREMENTS]", 1
        )[0]
        finalize = self.measure.split("[gcode_macro _CC_FINALIZE]", 1)[1].split(
            "[gcode_macro _CC_RESTORE_MESH]", 1
        )[0]
        self.assertIn("VARIABLE=cc_p{slot}_needs_calibration VALUE=1", calibrate)
        self.assertIn("VARIABLE=cc_p{slot}_needs_calibration VALUE=0", finalize)
        success_branch = finalize.rsplit("{% else %}", 1)[1]
        self.assertIn("VARIABLE=cc_p{slot}_needs_calibration VALUE=0", success_branch)

    def test_switching_profiles_requires_fresh_calibration(self) -> None:
        select = self.profiles.split("[gcode_macro CC_PROFILE_SELECT]", 1)[1].split(
            "[gcode_macro CC_PROFILE_RENAME]", 1
        )[0]
        self.assertIn("old_slot != slot", select)
        self.assertIn("VARIABLE=cc_p{slot}_needs_calibration VALUE=1", select)

    def test_print_start_cancels_if_selected_profile_is_not_ready(self) -> None:
        apply = self.print_cfg.split("[gcode_macro CC_APPLY_PROFILE]", 1)[1].split(
            "[gcode_macro CC_FIRST_LAYER_CONTROLS]", 1
        )[0]
        self.assertIn("needs == 1", apply)
        self.assertIn("CANCEL_PRINT", apply)
        self.assertLess(apply.index("needs == 1"), apply.index("_SET_GCODE_OFFSET_FAST"))

    def test_failed_probe_evidence_cannot_be_cleared_by_rollback(self) -> None:
        rollback = self.print_cfg.split("[gcode_macro CC_ROLLBACK]", 1)[1].split(
            "[gcode_macro CC_ENABLE]", 1
        )[0]
        self.assertIn("last_result != 3", rollback)
        self.assertIn("VARIABLE=cc_p{slot}_needs_calibration VALUE=0", rollback)

    def test_cleanup_turns_heaters_off_before_restoration(self) -> None:
        cleanup = self.measure.split("[gcode_macro _CC_CLEANUP]", 1)[1].split(
            "[gcode_macro _CC_ERROR_INCOMPLETE]", 1
        )[0]
        self.assertLess(cleanup.index("TURN_OFF_HEATERS"), cleanup.index("_CC_RESTORE_MESH"))
        self.assertLess(cleanup.index("TURN_OFF_HEATERS"), cleanup.index("RESTORE_GCODE_STATE"))

    def test_profile_model_keeps_auto_and_verified_separate(self) -> None:
        for token in (
            "_auto_ref",
            "_verified_ref",
            "_verified_bias",
            "_auto_delta",
            "_prev_verified_ref",
            "_prev_verified_bias",
            "_needs_calibration",
        ):
            self.assertIn(token, self.text)

    def test_initial_verification_uses_deliberate_live_adjustment(self) -> None:
        verify = self.print_cfg.split("[gcode_macro CC_VERIFY_CURRENT]", 1)[1].split(
            "[gcode_macro CC_ROLLBACK]", 1
        )[0]
        self.assertIn("old_ref >= 9000.0", verify)
        self.assertIn("new_bias = st.live_adjust|float", verify)

    def test_print_hook_captures_zmod_baseline_before_profile_adjustment(self) -> None:
        apply = self.print_cfg.split("[gcode_macro CC_APPLY_PROFILE]", 1)[1].split(
            "[gcode_macro CC_FIRST_LAYER_CONTROLS]", 1
        )[0]
        self.assertLess(apply.index("last_base_runtime"), apply.index("_SET_GCODE_OFFSET_FAST"))
        self.assertIn("mesh_test in [3, 4]", apply)
        self.assertIn("cc_auto = 0.0", apply)
        self.assertIn("different anchor", apply)

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
        self.assertNotRegex(operational, r"\bunbind\b")
        self.assertNotRegex(operational, r"\bbind\b")
        self.assertNotIn("flash_mcu", operational)

    def test_print_busy_guards_exist(self) -> None:
        self.assertGreaterEqual(self.text.count("['printing', 'paused']"), 5)

    def test_failsafe_turns_heaters_off_and_restores_state(self) -> None:
        block = self.measure.split("[delayed_gcode _CC_FAILSAFE]", 1)[1]
        self.assertIn("TURN_OFF_HEATERS", block)
        self.assertIn("_CC_RESTORE_MESH", block)
        self.assertIn("RESTORE_GCODE_STATE NAME=cc_calibration", block)


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

    def test_installer_fails_closed_when_printer_state_is_unknown(self) -> None:
        self.assertIn("Moonraker недоступен; безопасное состояние принтера не подтверждено", self.text)
        self.assertIn("print_stats.state; установка остановлена fail-closed", self.text)

    def test_payload_safety_guard_scans_every_split_cfg(self) -> None:
        self.assertIn('"$CFG_DIR"/*.cfg', self.text)

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
