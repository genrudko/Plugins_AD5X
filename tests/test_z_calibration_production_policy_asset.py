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
        guarded_abort_calls = (
            "_AD5X_Z_RC_ABORT_PATH",
            "_AD5X_Z_RC_ABORT_MODE",
            "_AD5X_Z_RC_ABORT_PROFILE",
            "_AD5X_Z_RC_ABORT_REFERENCE",
            "_AD5X_Z_RC_ABORT_ALIGNMENT",
        )
        for macro in guarded_abort_calls:
            call = next(
                line
                for line in self.asset.splitlines()
                if line.strip().startswith(macro) and not line.startswith("[gcode_macro")
            )
            call_pos = self.asset.index(call)
            preceding = self.asset[:call_pos]
            restore_pos = preceding.rfind("LOAD_GCODE_OFFSET")
            self.assertNotEqual(restore_pos, -1, macro)
            branch_pos = preceding.rfind("{% ")
            self.assertGreater(restore_pos, branch_pos, macro)
        self.assertEqual(self.asset.count("LOAD_GCODE_OFFSET"), 5)

    def test_policy_guard_is_pure_klipper_and_does_not_own_start_hook(self) -> None:
        self.assertIn('RESPOND PREFIX="info" MSG="Plugins AD5X saved+check PASS:', self.asset)
        self.assertNotIn("action_call_remote_method", self.asset)
        self.assertNotIn("[gcode_macro _USER_START_PRINT]", self.asset)
        self.assertNotIn("[gcode_macro _USER_START_PRINT]", self.wrapper)

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
