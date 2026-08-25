from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = (ROOT / "z_calibration_rc_policy.cfg").read_text(encoding="utf-8")
PRODUCT = (ROOT / "installer" / "z_calibration_productization.py").read_text(encoding="utf-8")
ANCHOR = (ROOT / "klipper" / "extras" / "ad5x_z_mesh_anchor.py").read_text(encoding="utf-8")
RUNTIME = (ROOT / "installer" / "z_calibration_runtime.sh").read_text(encoding="utf-8")
MEASUREMENT_ID = "adz-metrology-mesh5-median3-final05-median3-anchor-v5-20260825"

class MetrologyPolicyTests(unittest.TestCase):
    def test_precision_policy_is_scoped_not_global(self):
        self.assertNotIn("\n[probe]\n", POLICY)
        self.assertNotIn("[gcode_macro _PREPARE_PRINT]", POLICY)
        self.assertNotIn("_ADZ_PREPARE_PRINT_BASE", POLICY)
        self.assertNotIn("[gcode_macro _BED_MESH_CALIBRATE]", POLICY)
        self.assertNotIn("[gcode_macro PROBE]", POLICY)
        self.assertNotIn("rename_existing:", POLICY)
        self.assertIn(f'variable_policy_id: "{MEASUREMENT_ID}"', POLICY)
        self.assertIn("variable_mesh_probe_speed: 5.0", POLICY)
        self.assertIn("variable_final_probe_speed: 0.5", POLICY)
        self.assertNotIn("variable_expected_reconciliation_delta", POLICY)
        self.assertIn("variable_final_probe_completed: 0", POLICY)
        self.assertIn('MESH_COMMAND = "_BED_MESH_CALIBRATE"', ANCHOR)
        self.assertIn('PROBE_COMMAND = "PROBE"', ANCHOR)
        self.assertIn('register_event_handler("klippy:ready", self._handle_ready)', ANCHOR)
        self.assertIn("def _cmd_mesh_calibrate", ANCHOR)
        self.assertIn("def _cmd_probe", ANCHOR)
        commands = [line.strip() for line in POLICY.splitlines()]
        self.assertNotIn("G0", commands)
        self.assertNotIn("G1", commands)
        self.assertIn("_LOAD_CELL_TARE", commands)

    def test_final_precision_probe_is_one_shot_and_position_bound(self):
        start = ANCHOR.index("    def _cmd_probe")
        end = ANCHOR.index("    def _bed_mesh", start)
        block = ANCHOR[start:end]
        self.assertIn('final_probe_armed', block)
        self.assertIn('final_probe_x', block)
        self.assertIn('final_probe_y', block)
        self.assertIn('self._set_measurement(final_probe_armed=0)', block)
        self.assertIn('("PROBE_SPEED", m["final_probe_speed"])', block)
        self.assertIn('("SAMPLES", m["final_probe_samples"])', block)
        self.assertIn('("SAMPLES_RESULT", m["final_probe_result"])', block)

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
        self.assertIn("already completed the precision native Auto-Z probe", block)
        self.assertIn("requires final precision native Auto-Z probe", block)
        self.assertIn("_ADZ_FINALIZE_MACHINE_ANCHOR", block)
        self.assertLess(block.index("_ADZ_RECORD_MESH_POLICY"), block.index("_ADZ_FINALIZE_MACHINE_ANCHOR"))
        self.assertIn("profile == saved_profile", block)

    def test_saved_guard_binds_id_profile_and_exact_matrix(self):
        start = POLICY.index("[gcode_macro _ADZ_SAVED_CHECK_POLICY]")
        end = POLICY.index("[gcode_macro _ADZ_ACTION_CONTRACT]", start)
        block = POLICY[start:end]
        self.assertIn("stored_policy == measurement.policy_id", block)
        self.assertIn("stored_profile == active_profile", block)
        self.assertIn("stored_points == active_points", block)
        self.assertIn("anchor_active", block)
        self.assertIn("anchor_finalized", block)
        self.assertIn("variable_max_machine_anchor: 0.310000", POLICY)
        self.assertNotIn("expected_reconciliation", block)
        self.assertNotIn("reconciliation_residual", block)
        self.assertLess(block.index("not mesh_policy_match"), block.index("_ADZ_FINALIZE_MACHINE_ANCHOR"))

    def test_native_reconciliation_moves_service_delta_into_transient_mesh(self):
        start = POLICY.index("[gcode_macro _ADZ_FINALIZE_MACHINE_ANCHOR]")
        end = POLICY.index("[gcode_macro _ADZ_REPORT_MACHINE_ANCHOR]", start)
        block = POLICY[start:end]
        self.assertNotIn("_SET_GCODE_OFFSET_FAST", block)
        self.assertNotIn("SET_GCODE_VARIABLE MACRO=_TEST_POINT VARIABLE=temp_z_offset", block)
        self.assertIn("final_probe_completed", block)
        self.assertIn("LOAD_GCODE_OFFSET", block)
        self.assertIn("ADZ_MESH_ANCHOR SHIFT={native_delta}", block)
        self.assertLess(block.index("LOAD_GCODE_OFFSET"), block.index("ADZ_MESH_ANCHOR SHIFT={native_delta}"))
        self.assertIn("machine_anchor_finalized VALUE=1", block)
        self.assertNotIn("expected_reconciliation_delta", POLICY)

        # v6 preserves the physical sum while keeping the user offset honest.
        for mesh, probe, persistent in (
            (-2.0025, -1.8550, -0.0560),
            (-2.0050, -1.8900, -0.0560),
            (-2.0025, -1.8650, -0.0910),
        ):
            delta = probe - mesh
            v5_effective = persistent + delta
            v6_mesh = mesh + delta
            self.assertAlmostEqual(mesh + v5_effective, v6_mesh + persistent, places=9)
            self.assertAlmostEqual(v6_mesh, probe, places=9)

    def test_real_print_time_mesh_build_sets_transient_fresh_proof(self):
        start = ANCHOR.index("    def _cmd_mesh_calibrate")
        end = ANCHOR.index("    def _cmd_probe", start)
        block = ANCHOR[start:end]
        self.assertIn('built_for_print = self._print_state() == "printing"', block)
        self.assertIn('fresh_mesh_built=0', block)
        self.assertIn('fresh_native_check_done=0', block)
        self.assertIn('final_probe_completed=0', block)
        self.assertIn('self._forward(MESH_COMMAND', block)
        self.assertIn('self._set_measurement(fresh_mesh_built=1)', block)
        self.assertLess(block.index('fresh_mesh_built=0'), block.index('self._forward(MESH_COMMAND'))
        self.assertGreater(block.index('fresh_mesh_built=1'), block.index('self._forward(MESH_COMMAND'))

    def test_native_completion_is_recorded_by_existing_probe_adapter(self):
        self.assertNotIn("[gcode_macro _MESH_TEST]\nrename_existing:", POLICY)
        start = ANCHOR.index("    def _cmd_probe")
        end = ANCHOR.index("    def _bed_mesh", start)
        block = ANCHOR[start:end]
        self.assertIn('final_match', block)
        self.assertIn('fresh_mesh_built', block)
        self.assertIn('updates["fresh_native_check_done"] = 1', block)
        self.assertLess(block.index('self._forward(PROBE_COMMAND'), block.index('updates = {"final_probe_completed": 1}'))

    def test_live_verifier_queries_runtime_macro_variables(self):
        self.assertIn("gcode_macro%20_ADZ_MEASUREMENT_POLICY", RUNTIME)
        self.assertIn("gcode_macro%20_ADZ_SAVED_CHECK_POLICY", RUNTIME)
        self.assertIn("gcode_macro%20LOAD_CELL_TARE", RUNTIME)
        self.assertIn("gcode_macro%20LOAD_CELL_TARE&ad5x_z_mesh_anchor", RUNTIME)
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
