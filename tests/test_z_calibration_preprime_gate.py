from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
POLICY = (ROOT / "z_calibration_rc_policy.cfg").read_text(encoding="utf-8")
PRODUCTIZER = (ROOT / "installer" / "z_calibration_productization.py").read_text(encoding="utf-8")

class PrePrimeGateTests(unittest.TestCase):
    def test_fresh_autoz_runs_before_any_priming_route(self) -> None:
        start = POLICY.index("[gcode_macro _ADZ_PRIME_GATE]")
        end = POLICY.index("[gcode_macro _ADZ_PREPRINT_FRESH_MESH]", start)
        gate = POLICY[start:end]
        finalized = gate.index("_ADZ_SAVED_CHECK_POLICY PRE_PRIME=1")
        self.assertLess(finalized, gate.index("LINE_PURGE", finalized))
        self.assertLess(finalized, gate.rindex("{delegate}"))

    def test_kamp_preserves_zmod_line_purge_routing(self) -> None:
        start = POLICY.index("[gcode_macro _ADZ_PRIME_GATE]")
        end = POLICY.index("[gcode_macro _ADZ_PREPRINT_FRESH_MESH]", start)
        gate = POLICY[start:end]
        self.assertIn("zforce_kamp", gate)
        self.assertIn("v['use_kamp']", gate)
        for clear in ("_CLEAR1", "_CLEAR2", "_CLEAR3", "_CLEAR4"):
            self.assertIn(clear, gate)
        self.assertIn("KAMP purge compatibility; LINE_PURGE forced", gate)

    def test_missing_delegate_preserves_zmod_line_purge_fallback(self) -> None:
        start = POLICY.index("[gcode_macro _ADZ_PRIME_GATE]")
        end = POLICY.index("[gcode_macro _ADZ_PREPRINT_FRESH_MESH]", start)
        gate = POLICY[start:end]
        self.assertIn("delegate_settings is none", gate)
        self.assertIn('printer.configfile.settings.get("gcode_macro line_purge")', gate)
        self.assertIn("preserving Z-Mod fallback to LINE_PURGE", gate)
        self.assertIn('_ADZ_RC_ABORT_PRIME DELEGATE="LINE_PURGE"', gate)

    def test_end_hook_cannot_run_fresh_autoz_late(self) -> None:
        self.assertIn("fresh_mesh_proven and pre_prime == 1", POLICY)
        self.assertIn("fresh_mesh_proven and fresh_finalized == 1", POLICY)
        self.assertIn("_ADZ_FINALIZE_MACHINE_ANCHOR", POLICY)
        self.assertIn("_ADZ_RC_ABORT_PATH", POLICY)

    def test_productizer_owns_and_restores_public_clear_seam(self) -> None:
        for token in ("original_clear", "original_disable_priming", "original_prime_delegate", '"clear", PRIME_GATE', '"disable_priming", 0', "PRIME_DELEGATE_VARIABLE"):
            self.assertIn(token, PRODUCTIZER)

if __name__ == "__main__":
    unittest.main()
