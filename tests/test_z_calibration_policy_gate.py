from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOONRAKER = ROOT / "moonraker"
COMPONENTS = MOONRAKER / "components"
MODULE = COMPONENTS / "plugins_ad5x_zpolicy.py"


def load_module():
    for name in list(sys.modules):
        if name == "moonraker" or name.startswith("moonraker."):
            del sys.modules[name]
    moonraker_pkg = types.ModuleType("moonraker")
    moonraker_pkg.__path__ = [str(MOONRAKER)]
    components_pkg = types.ModuleType("moonraker.components")
    components_pkg.__path__ = [str(COMPONENTS)]
    sys.modules["moonraker"] = moonraker_pkg
    sys.modules["moonraker.components"] = components_pkg
    spec = importlib.util.spec_from_file_location(
        "moonraker.components.plugins_ad5x_zpolicy", MODULE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Z calibration policy module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


policy = load_module()
z = policy.core


def run_policies() -> policy.CalibrationRunPolicies:
    # Test fixture only. These are not release defaults.
    return policy.CalibrationRunPolicies(
        search=z.SearchEnvelopePolicy(-5.0, 220.0, 0.50, 0.30, -2.50, -1.00),
        probe=z.ProbeValidationPolicy(3, 0.05, 0.04, -2.50, -1.00),
        reference=z.ReferenceDecisionPolicy(0.10, 0.03),
        tare=z.TarePolicy(100.0),
        effective_offset_tolerance=0.0005,
        sample_count=3,
        confirmation_sample_count=3,
    )


def accepted_policy(
    *,
    source_refs: tuple[str, ...] = ("source:probe-contract",),
    hardware_run_ids: tuple[str, ...] = ("hw-run-001", "hw-run-002"),
    margin_rationale: str = "bounded margin derived from repeated acceptance data",
    owner_accepted: bool = True,
) -> policy.AcceptedCalibrationPolicy:
    return policy.AcceptedCalibrationPolicy(
        run_policies(),
        policy.HardwarePolicyEvidence(
            policy_id="ad5x-z-v2-hw-acceptance-001",
            source_refs=source_refs,
            hardware_run_ids=hardware_run_ids,
            margin_rationale=margin_rationale,
            owner_accepted=owner_accepted,
        ),
    )


def preflight(
    *,
    calibration_policy=...,
    write_gate_enabled: bool = True,
    hook_loaded: bool = True,
    klippy_ready: bool = True,
    print_state: str = "standby",
    homed_axes: str = "xyz",
    job_phase: str = "idle",
    offsets: z.OffsetComposition = z.OffsetComposition(persistent_user=-0.03),
    actual_effective: float | None = -0.03,
) -> policy.CalibrationPreflightInput:
    if calibration_policy is ...:
        calibration_policy = accepted_policy()
    return policy.CalibrationPreflightInput(
        policy=calibration_policy,
        write_gate_enabled=write_gate_enabled,
        hook_loaded=hook_loaded,
        klippy_ready=klippy_ready,
        print_state=print_state,
        homed_axes=homed_axes,
        job_phase=job_phase,
        offsets=offsets,
        actual_effective=actual_effective,
        effective_offset_tolerance=0.0005,
    )


class HardwareEvidenceGateTests(unittest.TestCase):
    def test_bare_feature_flags_cannot_replace_hardware_policy(self) -> None:
        result = policy.evaluate_calibration_preflight(
            preflight(calibration_policy=None)
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(policy.MotionBlocker.POLICY_MISSING, result.blockers)
        self.assertIsNone(result.policy_id)

    def test_owner_acceptance_boolean_alone_is_not_evidence(self) -> None:
        result = policy.evaluate_calibration_preflight(
            preflight(
                calibration_policy=accepted_policy(
                    source_refs=(),
                    hardware_run_ids=(),
                    margin_rationale="",
                    owner_accepted=True,
                )
            )
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(policy.MotionBlocker.POLICY_SOURCE_MISSING, result.blockers)
        self.assertIn(
            policy.MotionBlocker.POLICY_REPEATED_RUNS_MISSING,
            result.blockers,
        )
        self.assertIn(policy.MotionBlocker.POLICY_MARGIN_MISSING, result.blockers)
        self.assertNotIn(policy.MotionBlocker.POLICY_NOT_ACCEPTED, result.blockers)

    def test_unaccepted_evidence_remains_blocked(self) -> None:
        result = policy.evaluate_calibration_preflight(
            preflight(
                calibration_policy=accepted_policy(owner_accepted=False)
            )
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(policy.MotionBlocker.POLICY_NOT_ACCEPTED, result.blockers)

    def test_single_hardware_run_does_not_satisfy_repeated_evidence(self) -> None:
        result = policy.evaluate_calibration_preflight(
            preflight(
                calibration_policy=accepted_policy(
                    hardware_run_ids=("hw-run-001",)
                )
            )
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(
            policy.MotionBlocker.POLICY_REPEATED_RUNS_MISSING,
            result.blockers,
        )

    def test_duplicate_hardware_run_ids_are_rejected(self) -> None:
        with self.assertRaises(z.PolicyError):
            policy.HardwarePolicyEvidence(
                policy_id="policy",
                source_refs=("source",),
                hardware_run_ids=("same", "same"),
                margin_rationale="margin",
                owner_accepted=False,
            )


class RuntimePreflightGateTests(unittest.TestCase):
    def test_fully_evidenced_clean_idle_baseline_can_be_ready(self) -> None:
        result = policy.evaluate_calibration_preflight(preflight())
        self.assertTrue(result.ready_for_motion)
        self.assertEqual(result.blockers, ())
        self.assertEqual(result.policy_id, "ad5x-z-v2-hw-acceptance-001")
        self.assertAlmostEqual(result.external_unknown or 0.0, 0.0)

    def test_write_gate_remains_independent_hard_blocker(self) -> None:
        result = policy.evaluate_calibration_preflight(
            preflight(write_gate_enabled=False)
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(policy.MotionBlocker.WRITE_GATE_CLOSED, result.blockers)

    def test_hook_klippy_idle_job_and_homing_are_independent_blockers(self) -> None:
        result = policy.evaluate_calibration_preflight(
            preflight(
                hook_loaded=False,
                klippy_ready=False,
                print_state="printing",
                homed_axes="xy",
                job_phase="active",
            )
        )
        self.assertFalse(result.ready_for_motion)
        expected = {
            policy.MotionBlocker.HOOK_NOT_LOADED,
            policy.MotionBlocker.KLIPPY_NOT_READY,
            policy.MotionBlocker.PRINTER_NOT_IDLE,
            policy.MotionBlocker.JOB_LIFECYCLE_ACTIVE,
            policy.MotionBlocker.AXES_NOT_HOMED,
        }
        self.assertTrue(expected.issubset(set(result.blockers)))

    def test_missing_effective_offset_blocks_motion(self) -> None:
        result = policy.evaluate_calibration_preflight(
            preflight(actual_effective=None)
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(
            policy.MotionBlocker.EFFECTIVE_OFFSET_UNAVAILABLE,
            result.blockers,
        )
        self.assertIsNone(result.external_unknown)

    def test_unexplained_standard_klipper_offset_blocks_motion(self) -> None:
        result = policy.evaluate_calibration_preflight(
            preflight(actual_effective=-0.02)
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(
            policy.MotionBlocker.EXTERNAL_UNKNOWN_OFFSET,
            result.blockers,
        )
        self.assertAlmostEqual(result.external_unknown or 0.0, 0.01)

    def test_dirty_transient_provenance_blocks_even_when_actual_matches(self) -> None:
        offsets = z.OffsetComposition(
            persistent_user=-0.03,
            auto_alignment=0.01,
        )
        result = policy.evaluate_calibration_preflight(
            preflight(offsets=offsets, actual_effective=-0.02)
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(
            policy.MotionBlocker.DIRTY_TRANSIENT_BASELINE,
            result.blockers,
        )

    def test_negative_effective_tolerance_is_rejected(self) -> None:
        with self.assertRaises(z.PolicyError):
            policy.CalibrationPreflightInput(
                policy=accepted_policy(),
                write_gate_enabled=True,
                hook_loaded=True,
                klippy_ready=True,
                print_state="standby",
                homed_axes="xyz",
                job_phase="idle",
                offsets=z.OffsetComposition(),
                actual_effective=0.0,
                effective_offset_tolerance=-0.001,
            )


if __name__ == "__main__":
    unittest.main()
