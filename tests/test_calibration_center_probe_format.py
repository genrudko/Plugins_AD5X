from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CC = ROOT / "calibration_center"


class ProbeFormatSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.measure = (CC / "cc_measure.cfg").read_text(encoding="utf-8")
        cls.print_cfg = (CC / "cc_print.cfg").read_text(encoding="utf-8")
        cls.profiles = (CC / "cc_profiles.cfg").read_text(encoding="utf-8")

    def test_profiles_persist_probe_coordinate_formats(self) -> None:
        for token in (
            "_auto_probe_format",
            "_verified_probe_format",
            "_prev_verified_probe_format",
        ):
            self.assertIn(token, self.profiles)

    def test_verified_reference_is_never_compared_across_probe_formats(self) -> None:
        finalize = self.measure.split("[gcode_macro _CC_FINALIZE]", 1)[1].split(
            "[gcode_macro _CC_RESTORE_MESH]", 1
        )[0]
        format_branch = "verified_ref < 9000.0 and verified_format != current_format"
        delta_branch = "verified_ref < 9000.0 and (median - verified_ref)|abs"
        self.assertIn(format_branch, finalize)
        self.assertIn(delta_branch, finalize)
        self.assertLess(finalize.index(format_branch), finalize.index(delta_branch))

    def test_format_change_demotes_to_auto_measured(self) -> None:
        finalize = self.measure.split("[gcode_macro _CC_FINALIZE]", 1)[1].split(
            "[gcode_macro _CC_RESTORE_MESH]", 1
        )[0]
        branch = finalize.split(
            "verified_ref < 9000.0 and verified_format != current_format", 1
        )[1].split(
            "{% elif verified_ref < 9000.0 and (median - verified_ref)|abs", 1
        )[0]
        self.assertIn("VARIABLE=cc_p{slot}_auto_probe_format VALUE={current_format}", branch)
        self.assertIn("VARIABLE=cc_p{slot}_verified_ref VALUE=9999.0", branch)
        self.assertIn("VARIABLE=cc_p{slot}_verified_probe_format VALUE=-1", branch)
        self.assertIn("VARIABLE=cc_p{slot}_auto_delta VALUE=0.0", branch)
        self.assertIn("VARIABLE=cc_p{slot}_state VALUE=1", branch)
        self.assertIn("probe_format_rebase", branch)

    def test_verification_anchors_to_current_auto_probe_format(self) -> None:
        verify = self.print_cfg.split("[gcode_macro CC_VERIFY_CURRENT]", 1)[1].split(
            "[gcode_macro CC_ROLLBACK]", 1
        )[0]
        self.assertIn("auto_format not in [0, 1]", verify)
        self.assertIn("VARIABLE=cc_p{slot}_verified_probe_format VALUE={auto_format}", verify)
        self.assertIn("old_format != auto_format", verify)

    def test_rollback_refuses_cross_format_reference(self) -> None:
        rollback = self.print_cfg.split("[gcode_macro CC_ROLLBACK]", 1)[1].split(
            "[gcode_macro CC_ENABLE]", 1
        )[0]
        self.assertIn("prev_format != auto_format", rollback)
        self.assertIn("rollback между разными форматами", rollback)


if __name__ == "__main__":
    unittest.main()
