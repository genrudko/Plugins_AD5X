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
        self.assertLess(block.index("zcal_rc_apply"), block.index("zcal_rc_firmware_restart"))
        self.assertLess(block.index("zcal_rc_firmware_restart"), block.index("zcal_rc_live_verify"))

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
            block.index("zcal_rc_firmware_restart"),
            block.index("zcal_rc_live_verify"),
            block.index('record_rollback_target "$B"'),
        ]
        self.assertEqual(order, sorted(order))

    def test_rollback_pointer_is_bounded_to_managed_version_backups(self) -> None:
        self.assertIn('previous-successful-backup', self.text)
        self.assertIn('zcal-productization-update-*', self.text)
        self.assertIn('zcal-productization-rollback-*', self.text)
        self.assertIn('rollback transaction snapshot is missing', self.text)
        self.assertIn('rollback plan is missing', self.text)

    def test_uninstall_keeps_provenance_until_effective_baseline_is_verified(self) -> None:
        start = self.text.index("uninstall)")
        block = self.text[start:]
        order = [
            block.index("zcal_rc_uninstall"),
            block.index("restore_owned_include_state"),
            block.index("zcal_rc_firmware_restart"),
            block.index("zcal_rc_live_verify_uninstalled"),
            block.index("zcal_rc_finalize_uninstall"),
            block.index('rm -rf "$ROLLBACK_STATE_DIR"'),
        ]
        self.assertEqual(order, sorted(order))

    def test_transaction_rollback_restores_include_and_productizer_snapshot(self) -> None:
        self.assertIn('snapshot "$KLIPPER_INCLUDES" plugins.cfg', self.text)
        self.assertIn('restore_snapshot "$KLIPPER_INCLUDES" plugins.cfg', self.text)
        self.assertIn("rollback_operation", self.text)
        self.assertIn("zcal_rc_firmware_restart", self.text)

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
