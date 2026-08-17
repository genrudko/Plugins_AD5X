from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "z_calibration.cfg"
POLICY = ROOT / "docs" / "Z_CALIBRATION_PRODUCTION_POLICY_V1.md"


class ZCalibrationProductionPolicyAssetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.hook = HOOK.read_text(encoding="utf-8")
        self.policy = POLICY.read_text(encoding="utf-8")

    def test_policy_identity_and_accepted_mesh_match_hook(self) -> None:
        policy_id = "zcal-saved-check-v1-20260817"
        self.assertIn(f'variable_plugins_ad5x_policy_id: "{policy_id}"', self.hook)
        self.assertIn(f"**Policy ID:** `{policy_id}`", self.policy)

        self.assertIn('variable_plugins_ad5x_saved_profile: "auto"', self.hook)
        self.assertIn("saved_reference = -1.925833 mm", self.policy)
        self.assertIn("variable_plugins_ad5x_saved_reference: -1.925833", self.hook)
        self.assertIn("variable_plugins_ad5x_reference_tolerance: 0.000500", self.hook)

    def test_rc_alignment_limit_matches_documented_margin(self) -> None:
        self.assertIn("variable_plugins_ad5x_max_auto_alignment: 0.120000", self.hook)
        self.assertIn("abs(auto_alignment) < 0.120000 mm", self.policy)
        self.assertIn("0.064167 mm", self.policy)
        self.assertIn("0.055833 mm", self.policy)
        self.assertIn("≈ 1.87", self.policy)
        self.assertIn("abs(auto_alignment) >= 0.120000 mm", self.policy)

    def test_saved_check_requires_abort_style_zmod_mode_three(self) -> None:
        self.assertIn("mesh_test != 3", self.hook)
        self.assertIn("Required: SAVE_ZMOD_DATA MESH_TEST=3", self.hook)
        self.assertIn("`MESH_TEST=3` is intentional", self.policy)
        self.assertIn("automatic KAMP fallback", self.policy)

    def test_rejection_restores_global_baseline_before_each_guard_abort(self) -> None:
        guarded_abort_calls = (
            "_AD5X_Z_POLICY_ABORT_MODE",
            "_AD5X_Z_POLICY_ABORT_PROFILE",
            "_AD5X_Z_POLICY_ABORT_REFERENCE",
            "_AD5X_Z_POLICY_ABORT_ALIGNMENT",
        )
        for macro in guarded_abort_calls:
            call = next(
                line
                for line in self.hook.splitlines()
                if line.strip().startswith(macro) and not line.startswith("[gcode_macro")
            )
            call_pos = self.hook.index(call)
            preceding = self.hook[:call_pos]
            restore_pos = preceding.rfind("LOAD_GCODE_OFFSET")
            self.assertNotEqual(restore_pos, -1, macro)
            branch_pos = preceding.rfind("{% ")
            self.assertGreater(restore_pos, branch_pos, macro)

        # Four policy rejection branches restore Z-Mod's persistent global
        # baseline; no extra restoration is injected into the PASS branch.
        self.assertEqual(self.hook.count("LOAD_GCODE_OFFSET"), 4)

    def test_policy_guard_precedes_global_lifecycle_adoption(self) -> None:
        pass_pos = self.hook.index('RESPOND PREFIX="info" MSG="Plugins AD5X saved+check PASS:')
        adoption_pos = self.hook.index("_AD5X_Z_REMOTE_GLOBAL", pass_pos)
        self.assertGreater(adoption_pos, pass_pos)

        # One global helper + unchanged job/none branches. This protects the
        # existing exactly-once lifecycle contract.
        remote = 'action_call_remote_method("plugins_ad5x_z_job_start"'
        self.assertEqual(self.hook.count(remote), 3)

    def test_rc_hook_adds_no_plugins_owned_motion_or_offset_write(self) -> None:
        command_lines = [
            line.strip()
            for line in self.hook.splitlines()
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
        self.assertIn("not a universal AD5X numeric default", self.policy)
        self.assertIn("No reboot compensation", self.policy)
        self.assertIn("hardware change suspected / full calibration required", self.policy)

    def test_owner_acceptance_requires_real_first_layer(self) -> None:
        self.assertIn("one short first-layer print test", self.policy)
        self.assertIn("saved+check PASS", self.policy)
        self.assertIn("without manual Z-offset correction", self.policy)


if __name__ == "__main__":
    unittest.main()
