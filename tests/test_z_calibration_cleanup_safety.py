from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOONRAKER = ROOT / "moonraker"
COMPONENTS = MOONRAKER / "components"
ORCHESTRATOR = COMPONENTS / "plugins_ad5x_zorchestrator.py"
CLEANUP_SAFETY = COMPONENTS / "plugins_ad5x_zcleanup_safety.py"


def _reset_packages() -> None:
    for name in list(sys.modules):
        if name == "moonraker" or name.startswith("moonraker."):
            del sys.modules[name]
    moonraker_pkg = types.ModuleType("moonraker")
    moonraker_pkg.__path__ = [str(MOONRAKER)]
    components_pkg = types.ModuleType("moonraker.components")
    components_pkg.__path__ = [str(COMPONENTS)]
    sys.modules["moonraker"] = moonraker_pkg
    sys.modules["moonraker.components"] = components_pkg


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_reset_packages()
zrun = _load(
    ORCHESTRATOR,
    "moonraker.components.plugins_ad5x_zorchestrator_cleanup_safety_test",
)
zsafe = _load(
    CLEANUP_SAFETY,
    "moonraker.components.plugins_ad5x_zcleanup_safety_test",
)
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


def saved_check_request(correlation_id: str) -> zrun.CalibrationRunRequest:
    return zrun.CalibrationRunRequest(
        correlation_id=correlation_id,
        mesh_mode=z.MeshMode.SAVED_CHECK,
        mesh=z.MeshState(saved_profile="auto", saved_reference=-1.87),
        policies=policies(),
        offsets=z.OffsetComposition(persistent_user=-0.03),
        trusted_reference=-1.87,
    )


class OffsetVerifyLostRollbackFails(zrun.FakeCalibrationRunAdapter):
    def __init__(self) -> None:
        super().__init__(
            effective_offset=-0.03,
            probe_script=(-1.82, -1.83, -1.81),
            saved_meshes={"auto": -1.87},
        )
        self.write_count = 0
        self.fail_verification_read = True

    def set_effective_offset(self, value: float) -> None:
        self.write_count += 1
        if self.write_count == 1:
            super().set_effective_offset(value)
            return
        self.calls.append(("rollback_offset_failed", value))
        raise z.CommunicationFailure("rollback offset acknowledgement unavailable")

    def read_effective_offset(self) -> float:
        if self.write_count == 1 and self.fail_verification_read:
            self.fail_verification_read = False
            self.calls.append(("offset_verification_read_failed", None))
            raise z.CommunicationFailure("verification read unavailable")
        return super().read_effective_offset()


class RuntimeMeshApplyAndCleanupBothFail(zrun.FakeCalibrationRunAdapter):
    def __init__(self) -> None:
        super().__init__(
            effective_offset=-0.03,
            probe_script=(-1.82, -1.83, -1.81),
            saved_meshes={},
        )

    def build_runtime_mesh(self, runtime_id: str, *, reference: float) -> None:
        self.runtime_mesh = runtime_id
        self.active_mesh = runtime_id
        self.calls.append(("runtime_mesh_applied_then_rpc_failed", runtime_id))
        raise z.CommunicationFailure("runtime mesh response unavailable")

    def clear_runtime_mesh(self) -> None:
        self.calls.append(("runtime_mesh_cleanup_failed", self.runtime_mesh))
        raise z.CommunicationFailure("runtime mesh cleanup unavailable")


class CleanupSafetyTests(unittest.TestCase):
    def test_offset_rollback_failure_is_explicitly_unsafe(self) -> None:
        adapter = OffsetVerifyLostRollbackFails()
        log = z.BoundedDiagnosticLog(32)
        result = zrun.ZCalibrationOrchestrator(adapter, log).run(
            saved_check_request("cleanup-offset")
        )

        assessment = zsafe.assess_cleanup(result.cleanup)
        self.assertFalse(result.success)
        self.assertFalse(result.cleanup["offset_reconciled"])
        self.assertEqual(assessment.disposition, zsafe.CleanupDisposition.UNSAFE)
        self.assertFalse(assessment.safe_to_continue)
        self.assertEqual(assessment.failed_confirmations, ("offset_reconciled",))
        self.assertNotAlmostEqual(adapter.effective_offset, -0.03)
        abort = log.recent()[-1]
        self.assertEqual(abort.event_type, "calibration_abort")
        self.assertFalse(abort.payload["offset_reconciled"])

    def test_runtime_mesh_cleanup_failure_is_explicitly_unsafe(self) -> None:
        adapter = RuntimeMeshApplyAndCleanupBothFail()
        log = z.BoundedDiagnosticLog(32)
        request = zrun.CalibrationRunRequest(
            correlation_id="cleanup-mesh",
            mesh_mode=z.MeshMode.RUNTIME,
            mesh=z.MeshState(),
            policies=policies(),
            offsets=z.OffsetComposition(persistent_user=-0.03),
            initial_acquisition=True,
            runtime_mesh_id="runtime-unsafe",
        )
        result = zrun.ZCalibrationOrchestrator(adapter, log).run(request)

        assessment = zsafe.assess_cleanup(result.cleanup)
        self.assertFalse(result.cleanup["mesh_reconciled"])
        self.assertEqual(assessment.disposition, zsafe.CleanupDisposition.UNSAFE)
        self.assertEqual(assessment.failed_confirmations, ("mesh_reconciled",))
        self.assertEqual(adapter.runtime_mesh, "runtime-unsafe")
        abort = log.recent()[-1]
        self.assertFalse(abort.payload["mesh_reconciled"])

    def test_retract_failure_is_explicitly_unsafe(self) -> None:
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(-1.0,),
            retract_script=(z.CommunicationFailure("retract unavailable"),),
            saved_meshes={"auto": -1.87},
        )
        log = z.BoundedDiagnosticLog(32)
        result = zrun.ZCalibrationOrchestrator(adapter, log).run(
            saved_check_request("cleanup-retract")
        )

        assessment = zsafe.assess_cleanup(result.cleanup)
        self.assertEqual(result.model.last_abort_reason, "early_trigger")
        self.assertFalse(result.cleanup["retracted"])
        self.assertEqual(assessment.disposition, zsafe.CleanupDisposition.UNSAFE)
        self.assertEqual(assessment.failed_confirmations, ("retracted",))
        abort = log.recent()[-1]
        self.assertFalse(abort.payload["retracted"])

    def test_cleanly_recovered_abort_is_not_mislabeled_unsafe(self) -> None:
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(),
            saved_meshes={"auto": -1.87},
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(32)
        ).run(saved_check_request("cleanup-clean-abort"))

        assessment = zsafe.assess_cleanup(result.cleanup)
        self.assertFalse(result.success)
        self.assertEqual(result.model.last_abort_reason, "no_trigger")
        self.assertEqual(assessment.disposition, zsafe.CleanupDisposition.CLEAN)
        self.assertTrue(assessment.safe_to_continue)

    def test_missing_cleanup_confirmation_fails_closed(self) -> None:
        assessment = zsafe.assess_cleanup(
            {"offset_reconciled": True, "mesh_reconciled": True}
        )
        self.assertEqual(assessment.disposition, zsafe.CleanupDisposition.UNSAFE)
        self.assertEqual(assessment.failed_confirmations, ("retracted",))


if __name__ == "__main__":
    unittest.main()
