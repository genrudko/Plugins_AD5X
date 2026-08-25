from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOONRAKER = ROOT / "moonraker"
COMPONENTS = MOONRAKER / "components"
MODULE = COMPONENTS / "plugins_ad5x_zmotion_policy.py"


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
        "moonraker.components.plugins_ad5x_zmotion_policy", MODULE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Z motion policy module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


motion = load_module()
z = motion.core


def policies() -> motion.CalibrationRunRequest.__annotations__["policies"]:
    # Test fixture only. These values are not production defaults.
    from moonraker.components.plugins_ad5x_zorchestrator import CalibrationRunPolicies

    return CalibrationRunPolicies(
        search=z.SearchEnvelopePolicy(-5.0, 220.0, 0.50, 0.30, -2.50, -1.00),
        probe=z.ProbeValidationPolicy(3, 0.05, 0.04, -2.50, -1.00),
        reference=z.ReferenceDecisionPolicy(0.10, 0.03),
        tare=z.TarePolicy(100.0),
        effective_offset_tolerance=0.0005,
        sample_count=3,
        confirmation_sample_count=3,
    )


def accepted_policy():
    from moonraker.components.plugins_ad5x_zpolicy import (
        AcceptedCalibrationPolicy,
        HardwarePolicyEvidence,
    )

    return AcceptedCalibrationPolicy(
        policies(),
        HardwarePolicyEvidence(
            policy_id="hw-policy-accepted-001",
            source_refs=("source:controlled-ad5x-acceptance",),
            hardware_run_ids=("run-001", "run-002"),
            margin_rationale="test fixture: accepted margin rationale",
            owner_accepted=True,
        ),
    )


def calibration_preflight(*, accepted=None):
    from moonraker.components.plugins_ad5x_zpolicy import CalibrationPreflightInput

    if accepted is None:
        accepted = accepted_policy()
    return CalibrationPreflightInput(
        policy=accepted,
        write_gate_enabled=True,
        hook_loaded=True,
        klippy_ready=True,
        print_state="standby",
        homed_axes="xyz",
        job_phase="idle",
        offsets=z.OffsetComposition(persistent_user=-0.03),
        actual_effective=-0.03,
        effective_offset_tolerance=0.0005,
    )


def run_request(*, trusted_reference: float | None = -1.87):
    return motion.CalibrationRunRequest(
        correlation_id="motion-test",
        mesh_mode=z.MeshMode.SAVED_CHECK,
        mesh=z.MeshState(saved_profile="auto", saved_reference=-1.87),
        policies=policies(),
        offsets=z.OffsetComposition(persistent_user=-0.03),
        trusted_reference=trusted_reference,
        expected_reference=-1.87,
        initial_acquisition=False,
    )


def motion_policy(**overrides):
    values = dict(
        policy_id="hw-policy-accepted-001",
        reference_x=110.0,
        reference_y=110.0,
        travel_clearance_z=5.0,
        safe_approach_speed=10.0,
        contact_search_speed=1.0,
        sample_retract_distance=1.0,
        abort_retract_distance=3.0,
        retract_speed=5.0,
    )
    values.update(overrides)
    return motion.ProductionMotionPolicy(**values)


def bounds():
    return motion.MachineMotionBounds(
        min_x=0.0,
        max_x=220.0,
        min_y=0.0,
        max_y=220.0,
        min_z=-5.0,
        max_z=220.0,
    )


def preflight(**overrides):
    values = dict(
        calibration=calibration_preflight(),
        run=run_request(),
        motion_policy=motion_policy(),
        machine_bounds=bounds(),
        motion_gate_enabled=True,
    )
    values.update(overrides)
    return motion.ProductionMotionPreflightInput(**values)


class ProductionMotionPolicyTests(unittest.TestCase):
    def test_all_motion_values_are_explicit_required_constructor_fields(self):
        with self.assertRaises(TypeError):
            motion.ProductionMotionPolicy(policy_id="incomplete")

    def test_nonpositive_speeds_and_retracts_are_rejected(self):
        for field in (
            "safe_approach_speed",
            "contact_search_speed",
            "sample_retract_distance",
            "abort_retract_distance",
            "retract_speed",
        ):
            with self.subTest(field=field):
                with self.assertRaises(z.PolicyError):
                    motion_policy(**{field: 0.0})

    def test_invalid_machine_bounds_are_rejected(self):
        with self.assertRaises(z.PolicyError):
            motion.MachineMotionBounds(0, 0, 0, 220, -5, 220)

    def test_fully_accepted_concrete_policy_can_pass_repository_preflight(self):
        result = motion.evaluate_production_motion_preflight(preflight())
        self.assertTrue(result.ready_for_motion)
        self.assertEqual(result.blockers, ())
        self.assertTrue(result.calibration.ready_for_motion)
        self.assertEqual(result.motion_policy_id, "hw-policy-accepted-001")
        self.assertIsNotNone(result.envelope)

    def test_motion_gate_is_independent_from_write_gate(self):
        result = motion.evaluate_production_motion_preflight(
            preflight(motion_gate_enabled=False)
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(motion.MotionPolicyBlocker.MOTION_GATE_CLOSED, result.blockers)
        self.assertTrue(result.calibration.ready_for_motion)

    def test_missing_motion_policy_blocks_even_with_generic_preflight_green(self):
        result = motion.evaluate_production_motion_preflight(
            preflight(motion_policy=None)
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(motion.MotionPolicyBlocker.POLICY_MISSING, result.blockers)
        self.assertTrue(result.calibration.ready_for_motion)

    def test_motion_policy_must_be_covered_by_same_accepted_evidence_id(self):
        result = motion.evaluate_production_motion_preflight(
            preflight(motion_policy=motion_policy(policy_id="different-policy"))
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(motion.MotionPolicyBlocker.POLICY_ID_MISMATCH, result.blockers)

    def test_reference_point_must_be_inside_machine_xy_bounds(self):
        result = motion.evaluate_production_motion_preflight(
            preflight(motion_policy=motion_policy(reference_x=221.0))
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(
            motion.MotionPolicyBlocker.REFERENCE_OUTSIDE_XY_BOUNDS,
            result.blockers,
        )

    def test_clearance_must_be_inside_machine_z_bounds(self):
        result = motion.evaluate_production_motion_preflight(
            preflight(motion_policy=motion_policy(travel_clearance_z=221.0))
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(
            motion.MotionPolicyBlocker.CLEARANCE_OUTSIDE_Z_BOUNDS,
            result.blockers,
        )

    def test_clearance_must_be_above_concrete_search_envelope(self):
        # trusted ref -1.87, upper margin +0.50 -> upper search boundary -1.37.
        result = motion.evaluate_production_motion_preflight(
            preflight(motion_policy=motion_policy(travel_clearance_z=-1.37))
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(
            motion.MotionPolicyBlocker.CLEARANCE_NOT_ABOVE_SEARCH,
            result.blockers,
        )

    def test_contact_search_must_be_strictly_slower_than_safe_approach(self):
        result = motion.evaluate_production_motion_preflight(
            preflight(
                motion_policy=motion_policy(
                    safe_approach_speed=1.0,
                    contact_search_speed=1.0,
                )
            )
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(
            motion.MotionPolicyBlocker.CONTACT_NOT_SLOWER_THAN_APPROACH,
            result.blockers,
        )

    def test_generic_calibration_blocker_still_blocks_motion(self):
        from moonraker.components.plugins_ad5x_zpolicy import MotionBlocker

        generic = calibration_preflight()
        generic = type(generic)(
            policy=generic.policy,
            write_gate_enabled=False,
            hook_loaded=generic.hook_loaded,
            klippy_ready=generic.klippy_ready,
            print_state=generic.print_state,
            homed_axes=generic.homed_axes,
            job_phase=generic.job_phase,
            offsets=generic.offsets,
            actual_effective=generic.actual_effective,
            effective_offset_tolerance=generic.effective_offset_tolerance,
        )
        result = motion.evaluate_production_motion_preflight(
            preflight(calibration=generic)
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(MotionBlocker.WRITE_GATE_CLOSED, result.calibration.blockers)
        self.assertEqual(result.blockers, ())

    def test_invalid_concrete_search_envelope_blocks_motion(self):
        # A missing trusted reference without explicit initial acquisition must
        # fail at the motion boundary rather than being silently guessed.
        bad_run = run_request(trusted_reference=None)
        bad_run = type(bad_run)(
            correlation_id=bad_run.correlation_id,
            mesh_mode=z.MeshMode.RUNTIME,
            mesh=z.MeshState(),
            policies=bad_run.policies,
            offsets=bad_run.offsets,
            trusted_reference=None,
            expected_reference=None,
            initial_acquisition=False,
            runtime_mesh_id="runtime-test",
        )
        result = motion.evaluate_production_motion_preflight(
            preflight(run=bad_run)
        )
        self.assertFalse(result.ready_for_motion)
        self.assertIn(
            motion.MotionPolicyBlocker.SEARCH_ENVELOPE_INVALID,
            result.blockers,
        )


if __name__ == "__main__":
    unittest.main()
