from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
LIFECYCLE = ROOT / "installer" / "z_calibration_rc_lifecycle.sh"
HELPER = ROOT / "installer" / "z_calibration_runtime.sh"
PRODUCTIZER = ROOT / "installer" / "z_calibration_productization.py"


class ZCalibrationCanonicalLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.text = LIFECYCLE.read_text(encoding="utf-8")

    def test_canonical_modes_cover_install_update_repair_rollback_uninstall(self) -> None:
        self.assertIn("install|update|repair|rollback|uninstall|status", self.text)
        self.assertIn("install|update|repair)", self.text)
        self.assertIn("uninstall)", self.text)

    def test_lifecycle_reuses_shared_productizer_and_runtime_helper(self) -> None:
        self.assertIn("installer/z_calibration_runtime.sh", self.text)
        self.assertIn("installer/z_calibration_productization.py", self.text)
        self.assertIn("z_calibration_rc_policy.cfg", self.text)
        self.assertIn("zcal_rc_apply", self.text)
        self.assertIn("zcal_rc_uninstall", self.text)

    def test_lifecycle_performs_no_git_worktree_operation(self) -> None:
        lowered = self.text.lower()
        self.assertNotIn("git checkout", lowered)
        self.assertNotIn("git reset", lowered)
        self.assertNotIn("git clean", lowered)
        executable_git = [
            line for line in self.text.splitlines()
            if line.strip().lower().startswith("git ")
        ]
        self.assertEqual(executable_git, [])

    def test_apply_crosses_reload_and_live_verification_boundary(self) -> None:
        block = self.text[self.text.index("install|update|repair)") : self.text.index("uninstall)")]
        self.assertLess(block.index("zcal_rc_apply"), block.index("zcal_rc_klippy_host_restart"))
        self.assertLess(block.index("zcal_rc_klippy_host_restart"), block.index("zcal_rc_live_verify"))

    def test_successful_update_records_previous_version_only_after_live_verify(self) -> None:
        block = self.text[self.text.index("install|update|repair)") : self.text.index("rollback)")]
        self.assertIn('record_rollback_target "$B"', block)
        self.assertLess(block.index("zcal_rc_live_verify"), block.index('record_rollback_target "$B"'))

    def test_explicit_rollback_restores_reload_verifies_and_preserves_undo_point(self) -> None:
        start = self.text.index("rollback)")
        end = self.text.index("uninstall)", start)
        block = self.text[start:end]
        order = [
            block.index("restore_version_snapshot"),
            block.index("zcal_rc_klippy_host_restart"),
            block.index("verify_restored_managed_active"),
            block.index('record_rollback_target "$B"'),
        ]
        self.assertEqual(order, sorted(order))

    def test_rollback_pointer_is_bounded_to_managed_version_backups(self) -> None:
        self.assertIn('previous-successful-backup', self.text)
        self.assertIn('zcal-productization-update-*', self.text)
        self.assertIn('zcal-productization-rollback-*', self.text)
        self.assertIn('rollback transaction snapshot is missing', self.text)
        self.assertIn('rollback plan is missing', self.text)
        self.assertIn('rollback effective-state marker is missing', self.text)
        self.assertIn('active=0|active=1', self.text)

    def test_update_snapshot_recognizes_previous_owned_active_version_without_new_verifier(self) -> None:
        self.assertIn("managed_active_preflight(){", self.text)
        self.assertIn('p.get("baseline_source") != "manifest"', self.text)
        self.assertIn('["CC_APPLY_PROFILE", "_ADZ_SAVED_CHECK_POLICY"]', self.text)
        self.assertIn('["CC_APPLY_PROFILE", "_AD5X_Z_SAVED_CHECK_POLICY"]', self.text)
        self.assertIn("zcal_rc_live_verify >/dev/null 2>&1 || managed_active_preflight", self.text)

    def test_failed_klippy_recovery_uses_firmware_restart_before_idle_guard(self) -> None:
        self.assertIn("recover_shutdown_klippy(){", self.text)
        start = self.text.index("recover_shutdown_klippy(){")
        end = self.text.index("check_idle(){", start)
        recovery = self.text[start:end]
        self.assertIn('"klippy_state":"shutdown"', recovery)
        self.assertIn('"klippy_state":"error"', recovery)
        self.assertIn("zcal_rc_firmware_restart", recovery)
        self.assertNotIn("zcal_rc_klippy_host_restart", recovery)
        self.assertNotIn("print_stats", recovery)
        prepare = self.text[self.text.index("operation_prepare(){"):self.text.index("rollback_operation(){")]
        self.assertLess(prepare.index("recover_shutdown_klippy"), prepare.index("check_idle"))
        idle = self.text[self.text.index("check_idle(){"):self.text.index('mkdir -p "$GENERATED"')]
        self.assertIn("printing|paused) fail", idle)

    def test_active_version_rollback_uses_version_compatible_preflight_verification(self) -> None:
        self.assertIn("verify_restored_managed_active(){", self.text)
        block = self.text[self.text.index("verify_restored_managed_active(){"):self.text.index("operation_prepare(){")]
        self.assertIn("wait_klippy_ready", block)
        self.assertIn("ZCAL_RC_PREFLIGHT_READY=0", block)
        self.assertIn("zcal_rc_preflight", block)
        self.assertIn("managed_active_preflight", block)
        self.assertIn("active=1) verify_restored_managed_active", self.text)

    def test_rollback_can_restore_inactive_or_parked_preupdate_state(self) -> None:
        self.assertIn("printf 'active=0\\n'", self.text)
        start = self.text.index("rollback)")
        end = self.text.index("uninstall)", start)
        block = self.text[start:end]
        self.assertIn("active=0) wait_klippy_ready", block)
        self.assertIn("active=1) verify_restored_managed_active", block)

    def test_parked_update_refresh_is_bounded_and_precedes_apply(self) -> None:
        start = self.text.index("prepare_parked_policy_refresh(){")
        end = self.text.index("rollback_target(){", start)
        block = self.text[start:end]
        for token in (
            '[ "$MODE" = update ]', "active=0", '"$(include_count)" -eq 0',
            "plan_allows_parked_policy_refresh", "policy_macro_loaded",
            "manifest_policy_hash", 'rm -f "$ZCAL_RC_POLICY_DEST"',
        ):
            self.assertIn(token, block)
        apply = self.text[self.text.index("install|update|repair)"):self.text.index("rollback)", self.text.index("install|update|repair)"))]
        self.assertLess(apply.index("prepare_parked_policy_refresh"), apply.index("zcal_rc_apply"))

    def test_parked_refresh_requires_owned_pristine_inactive_state(self) -> None:
        self.assertIn('plan.get("baseline_source") != "manifest"', self.text)
        self.assertIn('plan.get("effective_commands") not in ([], ["CC_APPLY_PROFILE"])', self.text)
        self.assertIn('manifest.get("policy_dest", "")', self.text)
        self.assertIn("parked RC policy macro is still loaded", self.text)
        self.assertIn("gcode_macro _ad5x_z_saved_check_policy", self.text)
        self.assertIn("if policy_macro_loaded; then RC=0; else RC=$?; fi", self.text)
        self.assertIn("could not prove parked RC policy macro is inactive", self.text)

    def test_uninstall_keeps_provenance_until_effective_baseline_is_verified(self) -> None:
        start = self.text.index("uninstall)")
        block = self.text[start:]
        order = [
            block.index("zcal_rc_uninstall"),
            block.index("restore_owned_include_state"),
            block.index("zcal_rc_klippy_host_restart"),
            block.index("zcal_rc_live_verify_uninstalled"),
            block.index("zcal_rc_finalize_uninstall"),
            block.index('rm -rf "$ROLLBACK_STATE_DIR"'),
        ]
        self.assertEqual(order, sorted(order))

    def test_transaction_rollback_restores_include_and_productizer_snapshot(self) -> None:
        self.assertIn('snapshot "$KLIPPER_INCLUDES" plugins.cfg', self.text)
        self.assertIn('restore_snapshot "$KLIPPER_INCLUDES" plugins.cfg', self.text)
        self.assertIn("rollback_operation", self.text)
        self.assertIn("zcal_rc_klippy_host_restart", self.text)

    def test_rc_transaction_versions_mesh_anchor_runtime_with_policy(self) -> None:
        self.assertIn('snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py', self.text)
        self.assertIn('snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256', self.text)
        self.assertIn('restore_snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py', self.text)
        self.assertIn('restore_snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256', self.text)
        apply = self.text[self.text.index("install|update|repair)"):self.text.index("rollback)", self.text.index("install|update|repair)"))]
        self.assertLess(apply.index("zcal_mesh_anchor_deploy_managed_copy"), apply.index("zcal_rc_apply"))
        self.assertLess(apply.index("zcal_rc_apply"), apply.index("zcal_rc_klippy_host_restart"))
        status = self.text[self.text.index('if [ "$MODE" = status ]'):self.text.index('ROLLBACK_TARGET=', self.text.index('if [ "$MODE" = status ]'))]
        self.assertIn("zcal_mesh_anchor_runtime_matches_source", status)

    def test_explicit_rollback_requires_and_restores_mesh_anchor_snapshot(self) -> None:
        self.assertIn("rollback mesh-anchor runtime snapshot is missing", self.text)
        self.assertIn("rollback mesh-anchor hash snapshot is missing", self.text)
        start = self.text.index("restore_version_snapshot(){")
        block = self.text[start:self.text.index("managed_active_preflight(){", start)]
        self.assertIn('restore_snapshot "$ZCAL_MESH_ANCHOR_DEST" zcal-mesh-anchor.py', block)
        self.assertIn('restore_snapshot "$ZCAL_MESH_ANCHOR_HASH_STATE" zcal-mesh-anchor.sha256', block)

    def test_generated_include_has_owned_provenance(self) -> None:
        self.assertIn("include-state.pending", self.text)
        self.assertIn("original_present=0", self.text)
        self.assertIn("original_present=1", self.text)
        self.assertIn("duplicate generated RC policy include", self.text)

    def test_no_second_motion_or_direct_offset_path_is_added(self) -> None:
        command_tokens = ("PROBE", "SET_GCODE_OFFSET", " G0 ", " G1 ")
        for token in command_tokens:
            self.assertNotIn(token, self.text)

    def test_shared_helpers_also_remain_worktree_neutral(self) -> None:
        combined = (
            HELPER.read_text(encoding="utf-8")
            + PRODUCTIZER.read_text(encoding="utf-8")
        ).lower()
        self.assertNotIn("git checkout", combined)
        self.assertNotIn("git reset", combined)


if __name__ == "__main__":
    unittest.main()
