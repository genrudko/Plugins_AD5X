from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOONRAKER = ROOT / "moonraker"
COMPONENTS = MOONRAKER / "components"
MODULE = COMPONENTS / "plugins_ad5x_zorchestrator.py"


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
        "moonraker.components.plugins_ad5x_zorchestrator_atomicity", MODULE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Z calibration orchestrator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


zrun = load_module()
z = zrun.core


def policies() -> zrun.CalibrationRunPolicies:
    return zrun.CalibrationRunPolicies(
        search=z.SearchEnvelopePolicy(-5.0, 220.0, 0.50, 0.30, -2.50, -1.00),
        probe=z.ProbeValidationPolicy(3, 0.05, 0.04, -2.50, -1.00),
        reference=z.ReferenceDecisionPolicy(0.10, 0.03),
        tare=z.TarePolicy(100.0),
        effective_offset_tolerance=0.0005,
        sample_count=3,
        confirmation_sample_count=3,
    )


def saved_check_request() -> zrun.CalibrationRunRequest:
    return zrun.CalibrationRunRequest(
        correlation_id="atomic-offset",
        mesh_mode=z.MeshMode.SAVED_CHECK,
        mesh=z.MeshState(saved_profile="auto", saved_reference=-1.87),
        policies=policies(),
        offsets=z.OffsetComposition(persistent_user=-0.03),
        trusted_reference=-1.87,
    )


class PartialOffsetApplyThenFail(zrun.FakeCalibrationRunAdapter):
    def __init__(self) -> None:
        super().__init__(
            effective_offset=-0.03,
            probe_script=(-1.82, -1.83, -1.81),
            saved_meshes={"auto": -1.87},
        )
        self.failed_once = False

    def set_effective_offset(self, value: float) -> None:
        if not self.failed_once:
            self.failed_once = True
            # Simulate Klipper applying the command before Moonraker loses the
            # response/connection.  Cleanup must not trust the missing ACK.
            self.effective_offset = z._finite(value, "effective_offset")
            self.calls.append(("partial_set_then_fail", self.effective_offset))
            raise z.CommunicationFailure("response lost after apply")
        super().set_effective_offset(value)


class PartialRuntimeMeshThenFail(zrun.FakeCalibrationRunAdapter):
    def __init__(self) -> None:
        super().__init__(
            effective_offset=-0.03,
            probe_script=(-1.82, -1.83, -1.81),
            saved_meshes={},
        )

    def build_runtime_mesh(self, runtime_id: str, *, reference: float) -> None:
        # Simulate the runtime mesh becoming active before the RPC reports a
        # transport failure.  Cleanup must clear it despite no success ACK.
        self.runtime_mesh = runtime_id
        self.active_mesh = runtime_id
        self.calls.append(("partial_runtime_mesh_then_fail", runtime_id))
        raise z.CommunicationFailure("response lost after mesh build")


class AtomicAttemptCleanupTests(unittest.TestCase):
    def test_partial_offset_apply_then_transport_failure_restores_baseline(self) -> None:
        adapter = PartialOffsetApplyThenFail()
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(32)
        ).run(saved_check_request())

        self.assertFalse(result.success)
        self.assertEqual(result.model.last_abort_reason, "communication_failure")
        self.assertTrue(result.cleanup["offset_reconciled"])
        self.assertAlmostEqual(adapter.effective_offset, -0.03)
        self.assertAlmostEqual(result.model.offsets.persistent_user, -0.03)
        self.assertAlmostEqual(result.model.offsets.auto_alignment, 0.0)
        self.assertEqual(adapter.saved_meshes, {"auto": -1.87})
        self.assertTrue(any(name == "partial_set_then_fail" for name, _ in adapter.calls))
        self.assertTrue(any(name == "set_effective_offset" for name, _ in adapter.calls))

    def test_partial_runtime_mesh_then_transport_failure_clears_runtime_mesh(self) -> None:
        adapter = PartialRuntimeMeshThenFail()
        request = zrun.CalibrationRunRequest(
            correlation_id="atomic-mesh",
            mesh_mode=z.MeshMode.RUNTIME,
            mesh=z.MeshState(),
            policies=policies(),
            offsets=z.OffsetComposition(persistent_user=-0.03),
            initial_acquisition=True,
            runtime_mesh_id="runtime-partial",
        )

        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(32)
        ).run(request)

        self.assertFalse(result.success)
        self.assertEqual(result.model.last_abort_reason, "communication_failure")
        self.assertTrue(result.cleanup["mesh_reconciled"])
        self.assertIsNone(adapter.runtime_mesh)
        self.assertIsNone(adapter.active_mesh)
        self.assertEqual(adapter.saved_meshes, {})
        self.assertTrue(
            any(name == "partial_runtime_mesh_then_fail" for name, _ in adapter.calls)
        )
        self.assertTrue(any(name == "clear_runtime_mesh" for name, _ in adapter.calls))


if __name__ == "__main__":
    unittest.main()
