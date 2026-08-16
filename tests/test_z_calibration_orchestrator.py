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
        "moonraker.components.plugins_ad5x_zorchestrator", MODULE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load Z calibration orchestrator")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


zrun = load_module()
z = zrun.core


def policies(
    *,
    tare_limit: float = 100.0,
    initial_limits: bool = True,
) -> zrun.CalibrationRunPolicies:
    return zrun.CalibrationRunPolicies(
        search=z.SearchEnvelopePolicy(
            -5.0,
            220.0,
            0.50,
            0.30,
            -2.50 if initial_limits else None,
            -1.00 if initial_limits else None,
        ),
        probe=z.ProbeValidationPolicy(3, 0.05, 0.04, -2.50, -1.00),
        reference=z.ReferenceDecisionPolicy(0.10, 0.03),
        tare=z.TarePolicy(tare_limit),
        effective_offset_tolerance=0.0005,
        sample_count=3,
        confirmation_sample_count=3,
    )


def saved_check_request(
    *,
    correlation_id: str = "run-1",
    user_trim: float = -0.03,
) -> zrun.CalibrationRunRequest:
    return zrun.CalibrationRunRequest(
        correlation_id=correlation_id,
        mesh_mode=z.MeshMode.SAVED_CHECK,
        mesh=z.MeshState(saved_profile="auto", saved_reference=-1.87),
        policies=policies(),
        offsets=z.OffsetComposition(persistent_user=user_trim),
        trusted_reference=-1.87,
    )


def happy_adapter(*, user_trim: float = -0.03, **kwargs):
    return zrun.FakeCalibrationRunAdapter(
        effective_offset=user_trim,
        probe_script=(-1.82, -1.83, -1.81),
        h7_script=(z.H7Reading(z.H7Status.AVAILABLE, 0.0),),
        saved_meshes={"auto": -1.87},
        **kwargs,
    )


class OrchestratorHappyPathTests(unittest.TestCase):
    def test_saved_check_composes_one_validated_auto_alignment(self):
        adapter = happy_adapter()
        log = z.BoundedDiagnosticLog(32)

        result = zrun.ZCalibrationOrchestrator(adapter, log).run(
            saved_check_request()
        )

        self.assertTrue(result.success)
        self.assertEqual(result.model.state, z.CalibrationState.READY)
        self.assertAlmostEqual(result.model.offsets.persistent_user, -0.03)
        self.assertAlmostEqual(result.model.offsets.auto_alignment, 0.05)
        self.assertAlmostEqual(result.model.offsets.effective, 0.02)
        self.assertAlmostEqual(adapter.effective_offset, 0.02)
        self.assertEqual(adapter.active_mesh, "auto")
        self.assertEqual(adapter.saved_meshes, {"auto": -1.87})
        self.assertIsNone(adapter.runtime_mesh)
        self.assertEqual(result.reference_decision.kind, z.ReferenceDecisionKind.ALIGN)
        self.assertEqual(
            result.mesh_decision.action,
            z.MeshAction.USE_SAVED_WITH_ALIGNMENT,
        )
        self.assertNotIn(("save_runtime_mesh",), adapter.calls)
        self.assertFalse(any(name == "safe_retract" for name, _ in adapter.calls))

    def test_runtime_initial_acquisition_builds_session_mesh_without_saving(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(-1.82, -1.83, -1.81),
            h7_script=(z.H7Reading(z.H7Status.MISSING),),
            saved_meshes={},
        )
        log = z.BoundedDiagnosticLog(32)
        request = zrun.CalibrationRunRequest(
            correlation_id="runtime-1",
            mesh_mode=z.MeshMode.RUNTIME,
            mesh=z.MeshState(),
            policies=policies(),
            offsets=z.OffsetComposition(persistent_user=-0.03),
            initial_acquisition=True,
            runtime_mesh_id="runtime-1",
        )

        result = zrun.ZCalibrationOrchestrator(adapter, log).run(request)

        self.assertTrue(result.success)
        self.assertEqual(result.envelope.mode, z.SearchMode.INITIAL_ACQUISITION)
        self.assertEqual(result.model.runtime_mesh_id, "runtime-1")
        self.assertEqual(adapter.runtime_mesh, "runtime-1")
        self.assertEqual(adapter.active_mesh, "runtime-1")
        self.assertEqual(adapter.saved_meshes, {})
        self.assertAlmostEqual(adapter.effective_offset, -0.03)
        self.assertFalse(any(name == "save_runtime_mesh" for name, _ in adapter.calls))

    def test_all_diagnostics_keep_the_run_correlation_id(self):
        adapter = happy_adapter()
        log = z.BoundedDiagnosticLog(32)
        result = zrun.ZCalibrationOrchestrator(adapter, log).run(
            saved_check_request(correlation_id="corr-42")
        )
        self.assertTrue(result.success)
        events = log.recent()
        self.assertGreaterEqual(len(events), 6)
        self.assertTrue(all(event.correlation_id == "corr-42" for event in events))
        self.assertEqual(events[0].event_type, "calibration_start")
        self.assertEqual(events[-1].event_type, "calibration_ready")


class OrchestratorFailClosedTests(unittest.TestCase):
    def assert_safe_abort(self, result, adapter, *, reason: str):
        self.assertFalse(result.success)
        self.assertEqual(result.model.state, z.CalibrationState.ABORT)
        self.assertEqual(result.model.last_abort_reason, reason)
        self.assertAlmostEqual(result.model.offsets.persistent_user, -0.03)
        self.assertAlmostEqual(result.model.offsets.auto_alignment, 0.0)
        self.assertEqual(adapter.saved_meshes, {"auto": -1.87})

    def test_external_unknown_aborts_before_any_motion(self):
        adapter = happy_adapter(user_trim=-0.02)
        log = z.BoundedDiagnosticLog(16)
        result = zrun.ZCalibrationOrchestrator(adapter, log).run(
            saved_check_request(user_trim=-0.03)
        )
        self.assert_safe_abort(result, adapter, reason="external_unknown_offset")
        self.assertFalse(any(name == "prepare_probe" for name, _ in adapter.calls))
        self.assertFalse(any(name == "safe_approach" for name, _ in adapter.calls))
        self.assertFalse(any(name == "safe_retract" for name, _ in adapter.calls))

    def test_adapter_not_ready_aborts_before_motion(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            klippy_ready=False,
            effective_offset=-0.03,
            saved_meshes={"auto": -1.87},
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(16)
        ).run(saved_check_request())
        self.assert_safe_abort(result, adapter, reason="adapter_not_ready")
        self.assertFalse(any(name == "safe_approach" for name, _ in adapter.calls))

    def test_tare_residual_rejected_before_approach(self):
        adapter = happy_adapter(tare_script=(150.0,))
        request = zrun.CalibrationRunRequest(
            **{
                **saved_check_request().__dict__,
                "policies": policies(tare_limit=100.0),
            }
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(16)
        ).run(request)
        self.assert_safe_abort(
            result, adapter, reason="tare_residual_out_of_range"
        )
        self.assertFalse(any(name == "safe_approach" for name, _ in adapter.calls))
        self.assertFalse(any(name == "safe_retract" for name, _ in adapter.calls))

    def test_contradictory_h7_can_only_make_run_more_conservative(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(-1.82, -1.83, -1.81),
            h7_script=(z.H7Reading(z.H7Status.CONTRADICTORY, 500.0),),
            saved_meshes={"auto": -1.87},
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(16)
        ).run(saved_check_request())
        self.assert_safe_abort(result, adapter, reason="h7_contradictory")
        self.assertFalse(any(name == "safe_approach" for name, _ in adapter.calls))

    def test_early_trigger_aborts_and_retracts(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(-1.20,),
            saved_meshes={"auto": -1.87},
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(16)
        ).run(saved_check_request())
        self.assert_safe_abort(result, adapter, reason="early_trigger")
        self.assertTrue(any(name == "safe_retract" for name, _ in adapter.calls))
        self.assertAlmostEqual(adapter.effective_offset, -0.03)

    def test_no_trigger_stops_at_lower_bound_and_retracts(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(None,),
            saved_meshes={"auto": -1.87},
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(16)
        ).run(saved_check_request())
        self.assert_safe_abort(result, adapter, reason="no_trigger")
        self.assertTrue(
            any(name == "probe_stop_at_lower_bound" for name, _ in adapter.calls)
        )
        self.assertTrue(any(name == "safe_retract" for name, _ in adapter.calls))

    def test_probe_communication_failure_aborts_and_retracts(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(z.CommunicationFailure("lost"),),
            saved_meshes={"auto": -1.87},
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(16)
        ).run(saved_check_request())
        self.assert_safe_abort(result, adapter, reason="communication_failure")
        self.assertTrue(any(name == "safe_retract" for name, _ in adapter.calls))

    def test_high_scatter_is_not_silently_filtered(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(-1.80, -1.90, -1.82),
            saved_meshes={"auto": -1.87},
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(16)
        ).run(saved_check_request())
        self.assert_safe_abort(result, adapter, reason="probe_series_high_spread")
        self.assertEqual(result.primary_series.samples, (-1.80, -1.90, -1.82))
        self.assertTrue(any(name == "safe_retract" for name, _ in adapter.calls))

    def test_missing_initial_acquisition_policy_aborts_without_motion(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            saved_meshes={},
        )
        request = zrun.CalibrationRunRequest(
            correlation_id="missing-ref",
            mesh_mode=z.MeshMode.RUNTIME,
            mesh=z.MeshState(),
            policies=policies(initial_limits=False),
            offsets=z.OffsetComposition(persistent_user=-0.03),
            initial_acquisition=True,
            runtime_mesh_id="runtime",
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(16)
        ).run(request)
        self.assertEqual(result.model.last_abort_reason, "policy_error")
        self.assertFalse(any(name == "safe_approach" for name, _ in adapter.calls))


class OrchestratorLargeDeltaTests(unittest.TestCase):
    def test_confirmed_large_delta_escalates_without_offset_or_mesh_mutation(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(-1.52, -1.52, -1.52, -1.53, -1.52, -1.52),
            saved_meshes={"auto": -1.87},
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(32)
        ).run(saved_check_request())

        self.assertFalse(result.success)
        self.assertEqual(result.model.last_abort_reason, "confirmed_large_delta")
        self.assertEqual(
            result.reference_decision.kind,
            z.ReferenceDecisionKind.HARDWARE_CHANGE_SUSPECTED,
        )
        self.assertIsNotNone(result.confirmation_series)
        self.assertEqual(adapter.saved_meshes, {"auto": -1.87})
        self.assertIsNone(adapter.active_mesh)
        self.assertAlmostEqual(adapter.effective_offset, -0.03)
        self.assertFalse(any(name == "set_effective_offset" for name, _ in adapter.calls))

    def test_large_delta_that_is_not_reproduced_is_rejected(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(-1.52, -1.52, -1.52, -1.82, -1.83, -1.81),
            saved_meshes={"auto": -1.87},
        )
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(32)
        ).run(saved_check_request())
        self.assertEqual(result.model.last_abort_reason, "large_delta_not_reproduced")
        self.assertEqual(result.reference_decision.kind, z.ReferenceDecisionKind.REJECT)
        self.assertAlmostEqual(adapter.effective_offset, -0.03)
        self.assertEqual(adapter.saved_meshes, {"auto": -1.87})


class OrchestratorAtomicCleanupTests(unittest.TestCase):
    def test_offset_verification_failure_rolls_back_to_clean_baseline(self):
        adapter = happy_adapter(ignore_offset_writes=True)
        result = zrun.ZCalibrationOrchestrator(
            adapter, z.BoundedDiagnosticLog(32)
        ).run(saved_check_request())

        self.assertFalse(result.success)
        self.assertEqual(result.model.last_abort_reason, "offset_verification_failed")
        self.assertAlmostEqual(adapter.effective_offset, -0.03)
        self.assertTrue(result.cleanup["offset_reconciled"])
        self.assertTrue(any(name == "safe_retract" for name, _ in adapter.calls))
        self.assertAlmostEqual(result.model.offsets.persistent_user, -0.03)
        self.assertEqual(result.model.offsets.auto_alignment, 0.0)

    def test_runtime_mesh_is_cleared_when_cancel_occurs_after_build(self):
        adapter = zrun.FakeCalibrationRunAdapter(
            effective_offset=-0.03,
            probe_script=(-1.82, -1.83, -1.81),
            saved_meshes={},
        )
        request = zrun.CalibrationRunRequest(
            correlation_id="runtime-cancel",
            mesh_mode=z.MeshMode.RUNTIME,
            mesh=z.MeshState(),
            policies=policies(),
            offsets=z.OffsetComposition(persistent_user=-0.03),
            initial_acquisition=True,
            runtime_mesh_id="runtime-cancel",
        )
        orchestrator = zrun.ZCalibrationOrchestrator(
            adapter,
            z.BoundedDiagnosticLog(32),
            cancelled=lambda state: state is z.CalibrationState.OFFSET_COMPOSITION,
        )
        result = orchestrator.run(request)

        self.assertEqual(result.model.last_abort_reason, "cancelled")
        self.assertIsNone(adapter.runtime_mesh)
        self.assertIsNone(adapter.active_mesh)
        self.assertEqual(adapter.saved_meshes, {})
        self.assertTrue(result.cleanup["mesh_reconciled"])
        self.assertTrue(any(name == "clear_runtime_mesh" for name, _ in adapter.calls))

    def test_cancel_at_each_main_state_never_leaks_transient_offset(self):
        states = (
            z.CalibrationState.PRECHECK,
            z.CalibrationState.PREPARE_PROBE,
            z.CalibrationState.TARE,
            z.CalibrationState.SAFE_APPROACH,
            z.CalibrationState.SLOW_CONTACT_SEARCH,
            z.CalibrationState.VERIFY_CONTACT,
            z.CalibrationState.REPEATABILITY_CHECK,
            z.CalibrationState.REFERENCE_DECISION,
            z.CalibrationState.MESH_DECISION,
            z.CalibrationState.OFFSET_COMPOSITION,
            z.CalibrationState.READY,
        )
        for cancel_state in states:
            with self.subTest(cancel_state=cancel_state):
                adapter = happy_adapter()
                result = zrun.ZCalibrationOrchestrator(
                    adapter,
                    z.BoundedDiagnosticLog(32),
                    cancelled=lambda state, target=cancel_state: state is target,
                ).run(saved_check_request(correlation_id=cancel_state.value))

                self.assertFalse(result.success)
                self.assertEqual(result.model.last_abort_reason, "cancelled")
                self.assertAlmostEqual(result.model.offsets.persistent_user, -0.03)
                self.assertAlmostEqual(result.model.offsets.auto_alignment, 0.0)
                self.assertAlmostEqual(adapter.effective_offset, -0.03)
                self.assertEqual(adapter.saved_meshes, {"auto": -1.87})
                if cancel_state in {
                    z.CalibrationState.SLOW_CONTACT_SEARCH,
                    z.CalibrationState.VERIFY_CONTACT,
                    z.CalibrationState.REPEATABILITY_CHECK,
                    z.CalibrationState.REFERENCE_DECISION,
                    z.CalibrationState.MESH_DECISION,
                    z.CalibrationState.OFFSET_COMPOSITION,
                    z.CalibrationState.READY,
                }:
                    self.assertTrue(
                        any(name == "safe_retract" for name, _ in adapter.calls)
                    )


class OrchestratorPolicyTests(unittest.TestCase):
    def test_request_rejects_dirty_runtime_composition(self):
        dirty = (
            z.OffsetComposition(auto_alignment=0.01),
            z.OffsetComposition(slicer_job=0.01),
            z.OffsetComposition(live_adjustment=0.01),
            z.OffsetComposition(external_unknown=0.01),
        )
        for offsets in dirty:
            with self.subTest(offsets=offsets):
                with self.assertRaises(z.PolicyError):
                    zrun.CalibrationRunRequest(
                        correlation_id="dirty",
                        mesh_mode=z.MeshMode.RUNTIME,
                        mesh=z.MeshState(),
                        policies=policies(),
                        offsets=offsets,
                        initial_acquisition=True,
                        runtime_mesh_id="runtime",
                    )

    def test_runtime_mode_requires_explicit_session_mesh_id(self):
        with self.assertRaises(z.PolicyError):
            zrun.CalibrationRunRequest(
                correlation_id="runtime",
                mesh_mode=z.MeshMode.RUNTIME,
                mesh=z.MeshState(),
                policies=policies(),
                initial_acquisition=True,
            )

    def test_sample_counts_must_satisfy_validation_policy(self):
        with self.assertRaises(z.PolicyError):
            zrun.CalibrationRunPolicies(
                search=z.SearchEnvelopePolicy(-5, 220, 0.5, 0.3, -2.5, -1.0),
                probe=z.ProbeValidationPolicy(3, 0.05, 0.04, -2.5, -1.0),
                reference=z.ReferenceDecisionPolicy(0.1, 0.03),
                tare=z.TarePolicy(100),
                effective_offset_tolerance=0.0005,
                sample_count=2,
                confirmation_sample_count=3,
            )


if __name__ == "__main__":
    unittest.main()
