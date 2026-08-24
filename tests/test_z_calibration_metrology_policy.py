from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = (ROOT / "z_calibration_rc_policy.cfg").read_text(encoding="utf-8")
PRODUCT = (ROOT / "installer" / "z_calibration_productization.py").read_text(encoding="utf-8")
RUNTIME = (ROOT / "installer" / "z_calibration_runtime.sh").read_text(encoding="utf-8")
MEASUREMENT_ID = "adz-metrology-mesh5-median3-final05-median3-reuse-v2-20260825"

class MetrologyPolicyTests(unittest.TestCase):
    def test_precision_policy_is_scoped_not_global(self):
        self.assertNotIn("\n[probe]\n", POLICY)
        self.assertIn(f'variable_policy_id: "{MEASUREMENT_ID}"', POLICY)
        self.assertIn("[gcode_macro _BED_MESH_CALIBRATE]", POLICY)
        self.assertIn("rename_existing: _ADZ_BED_MESH_CALIBRATE_BASE", POLICY)
        self.assertIn("PROBE_SPEED={m.mesh_probe_speed} SAMPLES={m.mesh_probe_samples} SAMPLES_RESULT={m.mesh_probe_result}", POLICY)
        self.assertIn("variable_mesh_probe_speed: 5.0", POLICY)
        self.assertIn("variable_final_probe_speed: 0.5", POLICY)
        self.assertIn("[gcode_macro PROBE]", POLICY)
        self.assertIn("rename_existing: _ADZ_PROBE_BASE", POLICY)
        commands = [line.strip() for line in POLICY.splitlines()]
        self.assertNotIn("G0", commands)
        self.assertNotIn("G1", commands)
        self.assertIn("_LOAD_CELL_TARE", commands)

    def test_final_precision_probe_is_one_shot_and_position_bound(self):
        start = POLICY.index("[gcode_macro PROBE]")
        end = POLICY.index("[gcode_macro _ADZ_RC_ABORT_MESH_POLICY]", start)
        block = POLICY[start:end]
        self.assertIn("final_probe_armed", block)
        self.assertIn("final_probe_x", block)
        self.assertIn("final_probe_y", block)
        self.assertIn("final_probe_armed VALUE=0", block)
        self.assertIn("_ADZ_PROBE_BASE {rawparams} PROBE_SPEED={m.final_probe_speed} SAMPLES={m.final_probe_samples} SAMPLES_RESULT={m.final_probe_result}", block)

    def test_tare_reuse_is_print_scoped_and_fail_closed(self):
        start = POLICY.index("[gcode_macro LOAD_CELL_TARE]")
        end = POLICY.index("[gcode_macro _ADZ_RECORD_MESH_POLICY]", start)
        block = POLICY[start:end]
        self.assertIn('state == "printing" and edge_tare', block)
        self.assertIn("persistent_match", block)
        self.assertIn("fresh_match", block)
        self.assertIn("fresh_context", block)
        self.assertIn("measurement.fresh_mesh_built", block)
        self.assertIn('state == "printing" and armed == 1 and inside_mesh', block)
        self.assertIn("final_probe_armed VALUE=1", block)
        self.assertIn("_ADZ_RC_ABORT_MESH_POLICY", block)

    def test_fresh_rebuild_bootstrap_precedes_saved_fingerprint_gate(self):
        tare_start = POLICY.index("[gcode_macro LOAD_CELL_TARE]")
        tare_end = POLICY.index("[gcode_macro _ADZ_RECORD_MESH_POLICY]", tare_start)
        tare_block = POLICY[tare_start:tare_end]
        self.assertIn('active_profile != "" and y <', tare_block)
        self.assertIn("force_kamp == True or force_leveling == True", tare_block)
        self.assertIn("measurement.fresh_mesh_built|int == 1 or fresh_context", tare_block)

        saved_start = POLICY.index("[gcode_macro _ADZ_SAVED_CHECK_POLICY]")
        saved_end = POLICY.index("[gcode_macro _ADZ_ACTION_CONTRACT]", saved_start)
        saved_block = POLICY[saved_start:saved_end]
        self.assertLess(
            saved_block.index("fresh_mesh_proven and pre_prime == 1"),
            saved_block.index("not mesh_policy_match"),
        )

    def test_fresh_path_arms_before_native_reconciliation_and_fingerprints_after(self):
        start = POLICY.index("[gcode_macro _ADZ_PREPRINT_FRESH_MESH]")
        end = POLICY.index("[gcode_macro _ADZ_SAVED_CHECK_POLICY]", start)
        block = POLICY[start:end]
        self.assertIn("fresh_native_check_done", block)
        self.assertIn("already passed native Z-Mod AutoZOffset", block)
        self.assertIn("requires final native Z-Mod AutoZOffset", block)
        self.assertLess(block.index("_ADZ_VALIDATE_NATIVE_RESULT"), block.index("_ADZ_RECORD_MESH_POLICY"))
        self.assertIn("profile == saved_profile", block)

    def test_saved_guard_binds_id_profile_and_exact_matrix(self):
        start = POLICY.index("[gcode_macro _ADZ_SAVED_CHECK_POLICY]")
        end = POLICY.index("[gcode_macro _ADZ_ACTION_CONTRACT]", start)
        block = POLICY[start:end]
        self.assertIn("stored_policy == measurement.policy_id", block)
        self.assertIn("stored_profile == active_profile", block)
        self.assertIn("stored_points == active_points", block)
        self.assertLess(block.index("not mesh_policy_match"), block.index("auto_alignment|abs"))

    def test_real_print_time_mesh_build_sets_transient_fresh_proof(self):
        start = POLICY.index("[gcode_macro _BED_MESH_CALIBRATE]")
        end = POLICY.index("[gcode_macro PROBE]", start)
        block = POLICY[start:end]
        self.assertIn('printer.print_stats.state|default("unknown")|string == "printing"', block)
        self.assertLess(block.index("fresh_mesh_built VALUE=0"), block.index("_ADZ_BED_MESH_CALIBRATE_BASE {rawparams}"))
        self.assertIn("fresh_native_check_done VALUE=0", block)
        self.assertGreater(block.index("fresh_mesh_built VALUE=1"), block.index("_ADZ_BED_MESH_CALIBRATE_BASE {rawparams}"))

    def test_native_mesh_test_completion_is_tracked_without_repeating_check(self):
        start = POLICY.index("[gcode_macro _MESH_TEST]")
        end = POLICY.index("[gcode_macro PROBE]", start)
        block = POLICY[start:end]
        self.assertIn("rename_existing: _ADZ_MESH_TEST_BASE", block)
        self.assertIn("_ADZ_MESH_TEST_BASE {rawparams}", block)
        self.assertIn("fresh_native_check_done VALUE=1", block)

    def test_live_verifier_queries_runtime_macro_variables(self):
        self.assertIn("gcode_macro%20_ADZ_MEASUREMENT_POLICY", RUNTIME)
        self.assertIn("gcode_macro%20LOAD_CELL_TARE", RUNTIME)
        self.assertIn('status.get("gcode_macro _ADZ_MEASUREMENT_POLICY", {})', PRODUCT)
        self.assertIn('status.get("gcode_macro LOAD_CELL_TARE", {})', PRODUCT)

    def test_productizer_owns_and_invalidates_mesh_fingerprint(self):
        self.assertIn(f'MEASUREMENT_POLICY_ID = "{MEASUREMENT_ID}"', PRODUCT)
        for name in ("adz_mesh_policy", "adz_mesh_profile", "adz_mesh_points"):
            self.assertIn(name, PRODUCT)
        self.assertIn("previous_measurement_policy != MEASUREMENT_POLICY_ID", PRODUCT)
        self.assertIn('manifest["measurement_policy_id"] = MEASUREMENT_POLICY_ID', PRODUCT)

if __name__ == "__main__":
    unittest.main()
