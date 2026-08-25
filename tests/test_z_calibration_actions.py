from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOONRAKER = ROOT / "moonraker"
COMPONENTS = MOONRAKER / "components"
MODULE = COMPONENTS / "plugins_ad5x_zactions.py"


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
        "moonraker.components.plugins_ad5x_zactions", MODULE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Z calibration actions module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


actions = load_module()
z = actions.core


def policies() -> actions.CalibrationRunPolicies:
    # Test-only thresholds; not release defaults.
    return actions.CalibrationRunPolicies(
        search=z.SearchEnvelopePolicy(-5.0, 220.0, 0.50, 0.30, -2.50, -1.00),
        probe=z.ProbeValidationPolicy(3, 0.05, 0.04, -2.50, -1.00),
        reference=z.ReferenceDecisionPolicy(0.10, 0.03),
        tare=z.TarePolicy(100.0),
        effective_offset_tolerance=0.0005,
        sample_count=3,
        confirmation_sample_count=3,
    )


class SemanticActionTests(unittest.TestCase):
    def test_only_measurement_actions_are_exposed(self) -> None:
        self.assertEqual(
            {item.value for item in actions.CalibrationAction},
            {"check_z", "full_calibration"},
        )
        self.assertNotIn("saved", {item.value for item in actions.CalibrationAction})

    def test_check_z_maps_exactly_to_saved_check(self) -> None:
        context = actions.CalibrationActionContext(
            correlation_id="check-1",
            action=actions.CalibrationAction.CHECK_Z,
            policies=policies(),
            offsets=z.OffsetComposition(persistent_user=-0.03),
            mesh=z.MeshState(saved_profile="auto", saved_reference=-1.87),
        )
        request = actions.build_calibration_run_request(context)

        self.assertEqual(request.mesh_mode, z.MeshMode.SAVED_CHECK)
        self.assertFalse(request.initial_acquisition)
        self.assertEqual(request.trusted_reference, -1.87)
        self.assertEqual(request.expected_reference, -1.87)
        self.assertIsNone(request.runtime_mesh_id)

    def test_check_z_requires_saved_mesh_reference(self) -> None:
        context = actions.CalibrationActionContext(
            correlation_id="check-missing",
            action=actions.CalibrationAction.CHECK_Z,
            policies=policies(),
            offsets=z.OffsetComposition(),
            mesh=z.MeshState(),
        )
        with self.assertRaises(z.PolicyError):
            actions.build_calibration_run_request(context)

    def test_check_z_can_use_a_separate_trusted_search_reference(self) -> None:
        context = actions.CalibrationActionContext(
            correlation_id="check-trusted",
            action=actions.CalibrationAction.CHECK_Z,
            policies=policies(),
            offsets=z.OffsetComposition(),
            mesh=z.MeshState(saved_profile="auto", saved_reference=-1.87),
            trusted_reference=-1.84,
        )
        request = actions.build_calibration_run_request(context)
        self.assertEqual(request.trusted_reference, -1.84)
        self.assertEqual(request.expected_reference, -1.87)

    def test_full_calibration_maps_to_runtime_without_saved_profile_overwrite(self) -> None:
        context = actions.CalibrationActionContext(
            correlation_id="full-1",
            action=actions.CalibrationAction.FULL_CALIBRATION,
            policies=policies(),
            offsets=z.OffsetComposition(persistent_user=-0.03),
            mesh=z.MeshState(saved_profile="auto", saved_reference=-1.87),
            trusted_reference=-1.84,
            runtime_mesh_id="runtime-full-1",
        )
        request = actions.build_calibration_run_request(context)

        self.assertEqual(request.mesh_mode, z.MeshMode.RUNTIME)
        self.assertFalse(request.initial_acquisition)
        self.assertEqual(request.trusted_reference, -1.84)
        self.assertIsNone(request.expected_reference)
        self.assertEqual(request.runtime_mesh_id, "runtime-full-1")
        self.assertEqual(request.mesh.saved_profile, "auto")

    def test_full_calibration_without_trusted_reference_uses_explicit_initial_path(self) -> None:
        context = actions.CalibrationActionContext(
            correlation_id="full-initial",
            action=actions.CalibrationAction.FULL_CALIBRATION,
            policies=policies(),
            offsets=z.OffsetComposition(),
            mesh=z.MeshState(),
            runtime_mesh_id="runtime-initial",
        )
        request = actions.build_calibration_run_request(context)
        self.assertTrue(request.initial_acquisition)
        self.assertIsNone(request.trusted_reference)
        self.assertEqual(request.mesh_mode, z.MeshMode.RUNTIME)

    def test_full_calibration_requires_runtime_session_id(self) -> None:
        context = actions.CalibrationActionContext(
            correlation_id="full-missing-id",
            action=actions.CalibrationAction.FULL_CALIBRATION,
            policies=policies(),
            offsets=z.OffsetComposition(),
            mesh=z.MeshState(),
        )
        with self.assertRaises(z.PolicyError):
            actions.build_calibration_run_request(context)

    def test_dirty_baseline_is_rejected_by_shared_run_contract(self) -> None:
        context = actions.CalibrationActionContext(
            correlation_id="dirty",
            action=actions.CalibrationAction.CHECK_Z,
            policies=policies(),
            offsets=z.OffsetComposition(live_adjustment=0.01),
            mesh=z.MeshState(saved_profile="auto", saved_reference=-1.87),
        )
        with self.assertRaises(z.PolicyError):
            actions.build_calibration_run_request(context)


if __name__ == "__main__":
    unittest.main()
