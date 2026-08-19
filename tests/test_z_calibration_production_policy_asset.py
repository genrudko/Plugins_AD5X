from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "z_calibration.cfg"
POLICY_ASSET = ROOT / "z_calibration_rc_policy.cfg"
POLICY_DOC = ROOT / "docs" / "Z_CALIBRATION_PRODUCTION_POLICY_V1.md"


class ZCalibrationProductionPolicyAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.wrapper = WRAPPER.read_text(encoding="utf-8")
        self.asset = POLICY_ASSET.read_text(encoding="utf-8")
        self.policy = POLICY_DOC.read_text(encoding="utf-8")

    def test_policy_identity_and_accepted_mesh_match_canonical_asset(self) -> None:
        policy_id = "zcal-saved-check-v1-20260817"
        self.assertIn(f'variable_policy_id: "{policy_id}"', self.asset)
        self.assertIn(f"**Policy ID:** `{policy_id}`", self.policy)
        self.assertIn('variable_saved_profile: "auto"', self.asset)
        self.assertIn("variable_saved_reference: -1.925833", self.asset)
        self.assertIn("variable_reference_tolerance: 0.000500", self.asset)
        self.assertIn("saved_reference = -1.925833 mm", self.policy)

    def test_rc_alignment_limit_matches_documented_margin(self) -> None:
        self.assertIn("variable_max_auto_alignment: 0.120000", self.asset)
        self.assertIn("abs(auto_alignment) < 0.120000 mm", self.policy)
        self.assertIn("0.064167 mm", self.policy)
        self.assertIn("0.055833 mm", self.policy)
        self.assertIn("≈ 1.87", self.policy)

    def test_saved_check_requires_abort_style_zmod_mode_three(self) -> None:
        self.assertIn("mesh_test != 3", self.asset)
        self.assertIn("unattended saved+check requires MESH_TEST=3", self.asset)
        self.assertIn("`MESH_TEST=3` is intentional", self.policy)
        self.assertIn("automatic KAMP fallback", self.policy)

    def test_rejection_restores_global_baseline_before_each_guard_abort(self) -> None:
        guard_start = self.asset.index("[gcode_macro _ADZ_SAVED_CHECK_POLICY]")
        actions_start = self.asset.index("[gcode_macro _ADZ_ACTION_CONTRACT]")
        guard = self.asset[guard_start:actions_start]
        guarded_abort_calls = (
            "_ADZ_RC_ABORT_PATH",
            "_ADZ_RC_ABORT_MODE",
            "_ADZ_RC_ABORT_PROFILE",
            "_ADZ_RC_ABORT_REFERENCE",
            "_ADZ_RC_ABORT_ALIGNMENT",
        )
        for macro in guarded_abort_calls:
            call = next(
                line
                for line in guard.splitlines()
                if line.strip().startswith(macro) and not line.startswith("[gcode_macro")
            )
            call_pos = guard.index(call)
            preceding = guard[:call_pos]
            restore_pos = preceding.rfind("LOAD_GCODE_OFFSET")
            self.assertNotEqual(restore_pos, -1, macro)
            branch_pos = preceding.rfind("{% ")
            self.assertGreater(restore_pos, branch_pos, macro)
        self.assertEqual(guard.count("LOAD_GCODE_OFFSET"), 6)

    def test_policy_guard_is_pure_klipper_and_does_not_own_start_hook(self) -> None:
        self.assertIn('RESPOND PREFIX="info" MSG="Plugins AD5X saved+check PASS:', self.asset)
        self.assertNotIn("action_call_remote_method", self.asset)
        self.assertNotIn("[gcode_macro _USER_START_PRINT]", self.asset)
        self.assertNotIn("[gcode_macro _USER_START_PRINT]", self.wrapper)

    def test_callable_macro_names_obey_klipper_parser_rule(self) -> None:
        names = re.findall(r"^\[gcode_macro\s+([^\]]+)\]$", self.asset, re.MULTILINE)
        self.assertGreater(len(names), 0)
        legacy_data_only = "_AD5X_Z_SAVED_CHECK_POLICY"
        for name in names:
            if name == legacy_data_only:
                continue
            self.assertRegex(
                name,
                r"^[A-Za-z_]+(?:\d+)?$",
                f"Klipper macro command name is not parser-safe: {name}",
            )
            first_digit = next((i for i, ch in enumerate(name) if ch.isdigit()), None)
            if first_digit is not None:
                self.assertTrue(
                    name[first_digit:].isdigit(),
                    f"digits must be a trailing suffix in Klipper macro name: {name}",
                )
        self.assertIn("[gcode_macro _ADZ_SAVED_CHECK_POLICY]", self.asset)
        self.assertNotIn("\n        _AD5X_Z_SAVED_CHECK_POLICY\n", self.asset)

    def test_preprint_setting_is_persistent_and_maps_to_zmod_modes(self) -> None:
        self.assertIn("[gcode_macro ADZ_SET_PREPRINT]", self.asset)
        self.assertIn("variable_preprint_enabled_mode: 3", self.asset)
        self.assertIn("variable_preprint_disabled_mode: 0", self.asset)
        setter_start = self.asset.index("[gcode_macro ADZ_SET_PREPRINT]")
        check_start = self.asset.index("[gcode_macro ADZ_CHECK]")
        setter = self.asset[setter_start:check_start]
        self.assertIn("SAVE_VARIABLE VARIABLE=mesh_test", setter)
        self.assertIn("ENABLED", setter)
        self.assertIn("SET_GCODE_VARIABLE MACRO=_TEST_POINT VARIABLE=temp_z_offset VALUE=0.0", setter)
        self.assertIn("LOAD_GCODE_OFFSET", setter)

    def test_preprint_orchestrator_orders_final_mesh_before_z_policy(self) -> None:
        guard_start = self.asset.index("[gcode_macro _ADZ_SAVED_CHECK_POLICY]")
        actions_start = self.asset.index("[gcode_macro _ADZ_ACTION_CONTRACT]")
        guard = self.asset[guard_start:actions_start]
        self.assertIn("fresh_mesh_proven", guard)
        self.assertIn("force_kamp == True", guard)
        self.assertIn("force_leveling == True", guard)
        self.assertIn("print_leveling != 0 and screen == False", guard)
        self.assertIn("native_leveling_ambiguous", guard)
        self.assertIn("_ADZ_PREPRINT_FRESH_MESH", guard)
        self.assertIn("_ADZ_PREPRINT_DISABLED", guard)
        self.assertLess(guard.index("mesh_test == 0"), guard.index("mesh_test != 3"))
        self.assertLess(guard.index("fresh_mesh_proven %}"), guard.index("native_leveling_ambiguous %}"))

    def test_fresh_mesh_path_resets_transient_alignment_without_second_probe(self) -> None:
        start = self.asset.index("[gcode_macro _ADZ_PREPRINT_FRESH_MESH]")
        end = self.asset.index("[gcode_macro _ADZ_SAVED_CHECK_POLICY]")
        block = self.asset[start:end]
        self.assertIn("SET_GCODE_VARIABLE MACRO=_TEST_POINT VARIABLE=temp_z_offset VALUE=0.0", block)
        self.assertIn("LOAD_GCODE_OFFSET", block)
        self.assertNotIn("_MESH_TEST", block)
        self.assertNotIn("PROBE", block)

    def test_native_screen_leveling_choice_is_not_guessed(self) -> None:
        guard_start = self.asset.index("[gcode_macro _ADZ_SAVED_CHECK_POLICY]")
        actions_start = self.asset.index("[gcode_macro _ADZ_ACTION_CONTRACT]")
        guard = self.asset[guard_start:actions_start]
        self.assertIn("print_leveling != 0 and screen != False", guard)
        ambiguous = guard.index("native_leveling_ambiguous %}")
        abort = guard.index("_ADZ_RC_ABORT_PATH", ambiguous)
        self.assertLess(ambiguous, abort)

    def test_semantic_actions_delegate_only_to_zmod_owned_physical_paths(self) -> None:
        self.assertIn("[gcode_macro _ADZ_ACTION_CONTRACT]", self.asset)
        self.assertIn("variable_contract_version: 3", self.asset)
        self.assertIn('variable_runtime_profile: "ad5x_runtime"', self.asset)
        self.assertIn("[gcode_macro ADZ_CHECK]", self.asset)
        self.assertIn("[gcode_macro ADZ_BUILD_RUNTIME_MESH]", self.asset)
        self.assertIn("[gcode_macro ADZ_RESTORE_AUTO]", self.asset)
        self.assertIn("_MESH_TEST", self.asset)
        self.assertIn("AUTO_FULL_BED_LEVEL", self.asset)
        self.assertIn("PROFILE={runtime_profile}", self.asset)
        self.assertIn("BED_MESH_PROFILE LOAD=auto FROM=ADZ_BUILD_RUNTIME_MESH", self.asset)
        self.assertNotIn("[gcode_macro ADZ_FULL_CALIBRATION]", self.asset)
        self.assertNotIn("SAVE_CONFIG", self.asset)

    def test_semantic_actions_require_explicit_temperature_context(self) -> None:
        check_start = self.asset.index("[gcode_macro ADZ_CHECK]")
        runtime_start = self.asset.index("[gcode_macro ADZ_BUILD_RUNTIME_MESH]")
        restore_start = self.asset.index("[gcode_macro ADZ_RESTORE_AUTO]")
        check = self.asset[check_start:runtime_start]
        runtime = self.asset[runtime_start:restore_start]
        for block in (check, runtime):
            self.assertIn("params.EXTRUDER_TEMP|default(-1)|float", block)
            self.assertIn("params.BED_TEMP|default(-1)|float", block)
            self.assertIn("min_extrude_temp", block)
            self.assertIn("max_temp", block)
            self.assertIn("_ADZ_ACTION_ABORT_TEMP", block)
        self.assertNotIn("default(245)", check)
        self.assertNotIn("default(80)", check)

    def test_check_z_establishes_baseline_and_runs_guard_before_and_after_zmod(self) -> None:
        start = self.asset.index("[gcode_macro ADZ_CHECK]")
        end = self.asset.index("[gcode_macro ADZ_BUILD_RUNTIME_MESH]")
        block = self.asset[start:end]
        first_restore = block.index("LOAD_GCODE_OFFSET")
        first_guard = block.index("_ADZ_SAVED_CHECK_POLICY")
        zmod = block.index("_MESH_TEST")
        second_guard = block.index("_ADZ_SAVED_CHECK_POLICY", first_guard + 1)
        self.assertLess(first_restore, first_guard)
        self.assertLess(first_guard, zmod)
        self.assertLess(zmod, second_guard)
        self.assertIn("SET_GCODE_VARIABLE MACRO=_START_PRINT VARIABLE=zextruder_temp", block)
        self.assertIn("SET_GCODE_VARIABLE MACRO=_START_PRINT VARIABLE=zbed_temp", block)

    def test_runtime_mesh_restores_auto_and_never_persists_profile(self) -> None:
        start = self.asset.index("[gcode_macro ADZ_BUILD_RUNTIME_MESH]")
        end = self.asset.index("[gcode_macro ADZ_RESTORE_AUTO]")
        block = self.asset[start:end]
        build = block.index("AUTO_FULL_BED_LEVEL")
        restore = block.index("BED_MESH_PROFILE LOAD=auto FROM=ADZ_BUILD_RUNTIME_MESH")
        guard = block.index("_ADZ_SAVED_CHECK_POLICY", build)
        self.assertLess(build, restore)
        self.assertLess(restore, guard)
        self.assertNotIn("SAVE_CONFIG", block)

    def test_policy_adds_no_plugins_owned_motion_or_direct_z_write(self) -> None:
        command_lines = [
            line.strip()
            for line in self.asset.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertFalse(any(re.match(r"^G[01](?:\s|$)", line) for line in command_lines))
        self.assertFalse(any(re.match(r"^PROBE(?:\s|$)", line) for line in command_lines))
        self.assertFalse(any(re.match(r"^SET_GCODE_OFFSET(?:\s|$)", line) for line in command_lines))

    def test_policy_is_evidence_bound_not_universal_default(self) -> None:
        refs = (
            "Z_CALIBRATION_GATE_A_BASELINE_2026-08-16.md",
            "Z_CALIBRATION_GATE_B_RUN_001_2026-08-17.md",
            "Z_CALIBRATION_GATE_C_RUN_001_2026-08-17.md",
            "Z_CALIBRATION_GATE_C_RUN_002_PLA60_2026-08-17.md",
            "Z_CALIBRATION_GATE_C_RUN_003_CLEAN_POWER_CYCLE_2026-08-17.md",
        )
        for ref in refs:
            self.assertIn(ref, self.policy)
        self.assertIn("universal AD5X numeric default", self.policy)
        self.assertIn("No reboot compensation", self.policy)
        self.assertIn("hardware change suspected / full calibration required", self.policy)


if __name__ == "__main__":
    unittest.main()
