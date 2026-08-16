from __future__ import annotations

import importlib.util
import math
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "moonraker" / "components" / "plugins_ad5x_zcalibration.py"
spec = importlib.util.spec_from_file_location("plugins_ad5x_zcalibration", MODULE)
if spec is None or spec.loader is None:
    raise RuntimeError("unable to load Z calibration core")
z = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = z
spec.loader.exec_module(z)


def probe_policy():
    return z.ProbeValidationPolicy(3, 0.05, 0.04, -2.5, -1.0)


def accepted(samples=(-1.82, -1.83, -1.81)):
    result = z.validate_probe_series(samples, probe_policy())
    if not result.accepted:
        raise AssertionError(result)
    return result


class OffsetCompositionTests(unittest.TestCase):
    def test_table_driven_composition(self):
        cases = [
            ((0, 0, 0, 0), 0),
            ((0.04, 0, 0, 0), 0.04),
            ((0, -0.03, 0, 0), -0.03),
            ((0, 0, 0.02, 0), 0.02),
            ((0, 0, 0, -0.01), -0.01),
            ((0.04, -0.03, 0.02, 0.01), 0.04),
            ((0.05, -0.05, 0.01, -0.01), 0),
        ]
        for values, expected in cases:
            with self.subTest(values=values):
                self.assertAlmostEqual(z.OffsetComposition(*values).known_total, expected)

    def test_auto_replaces_instead_of_double_applying(self):
        c = z.OffsetComposition(auto_alignment=0.04).replace_auto(0.04).replace_auto(0.02)
        self.assertAlmostEqual(c.auto_alignment, 0.02)
        self.assertAlmostEqual(c.known_total, 0.02)

    def test_job_scope_replaces_and_clears(self):
        c = z.OffsetComposition(persistent_user=-0.03).start_job(0.02).start_job(-0.01)
        self.assertAlmostEqual(c.slicer_job, -0.01)
        c = c.end_job()
        self.assertEqual(c.slicer_job, 0)
        self.assertAlmostEqual(c.persistent_user, -0.03)

    def test_live_save_and_no_save(self):
        c = z.OffsetComposition(persistent_user=-0.03).step_live(0.01).step_live(-0.005)
        self.assertAlmostEqual(c.live_adjustment, 0.005)
        self.assertAlmostEqual(c.end_job().persistent_user, -0.03)
        saved = c.save_live_to_persistent()
        self.assertAlmostEqual(saved.persistent_user, -0.025)
        self.assertEqual(saved.live_adjustment, 0)

    def test_external_offset_is_classified(self):
        c = z.OffsetComposition(auto_alignment=0.04, persistent_user=-0.03)
        reconciled = c.reconcile_actual(0.05, tolerance=0.0005)
        self.assertAlmostEqual(reconciled.external_unknown, 0.04)
        self.assertAlmostEqual(reconciled.effective, 0.05)

    def test_tolerance_does_not_invent_external_component(self):
        c = z.OffsetComposition(auto_alignment=0.04, persistent_user=-0.03)
        self.assertEqual(c.reconcile_actual(0.0102, tolerance=0.0005).external_unknown, 0)

    def test_nonfinite_offsets_fail(self):
        with self.assertRaises(z.PolicyError): z.OffsetComposition(auto_alignment=math.nan)
        with self.assertRaises(z.PolicyError): z.OffsetComposition().start_job(math.inf)


class SearchEnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.policy = z.SearchEnvelopePolicy(-5, 220, 0.25, 0.20)

    def test_trusted_reference_is_bounded(self):
        e = self.policy.build(-1.8)
        self.assertEqual(e.mode, z.SearchMode.TRUSTED_REFERENCE)
        self.assertAlmostEqual(e.lower_z, -2.0)
        self.assertAlmostEqual(e.upper_z, -1.55)

    def test_missing_reference_requires_explicit_initial_mode(self):
        with self.assertRaises(z.PolicyError): self.policy.build(None)

    def test_initial_acquisition_requires_explicit_safe_limits(self):
        with self.assertRaises(z.PolicyError): self.policy.build(None, initial_acquisition=True)
        p = z.SearchEnvelopePolicy(-5, 220, 0.25, 0.20, -2.5, 1.0)
        self.assertEqual(p.build(None, initial_acquisition=True).mode, z.SearchMode.INITIAL_ACQUISITION)

    def test_no_position_min_fallback(self):
        with self.assertRaises(z.PolicyError): self.policy.build(-4.9)

    def test_invalid_margins_fail(self):
        with self.assertRaises(z.PolicyError): z.SearchEnvelopePolicy(-5, 220, 0, 0.2)
        with self.assertRaises(z.PolicyError): z.SearchEnvelopePolicy(-5, 220, 0.2, -0.1)

    def test_trigger_classification(self):
        e = self.policy.build(-1.8)
        self.assertEqual(e.classify_trigger(-1.4), "early")
        self.assertEqual(e.classify_trigger(-2.1), "below_lower_bound")
        self.assertEqual(e.classify_trigger(-1.8), "inside")

    def test_lower_bound_mutation_sensitivity(self):
        e = self.policy.build(-1.8)
        def safety_assertion(envelope):
            return envelope.classify_trigger(envelope.lower_z - 0.01) == "below_lower_bound"
        self.assertTrue(safety_assertion(e))
        original = z.SearchEnvelope.classify_trigger
        try:
            z.SearchEnvelope.classify_trigger = lambda _self, _value: "inside"
            self.assertFalse(safety_assertion(e))
        finally:
            z.SearchEnvelope.classify_trigger = original


class ProbeSeriesTests(unittest.TestCase):
    def test_stable_series_passes(self):
        r = z.validate_probe_series([-1.82, -1.83, -1.81], probe_policy())
        self.assertTrue(r.accepted)
        self.assertLessEqual(r.spread, 0.05)

    def test_single_outlier_is_not_silently_dropped(self):
        r = z.validate_probe_series([-1.52, -1.83, -1.84], probe_policy())
        self.assertEqual(r.status, z.SeriesStatus.HIGH_SPREAD)

    def test_monotonic_drift_rejected(self):
        p = z.ProbeValidationPolicy(3, 0.20, 0.03, -2.5, -1.0)
        self.assertEqual(z.validate_probe_series([-1.80, -1.82, -1.84], p).status, z.SeriesStatus.DRIFT)

    def test_high_scatter_rejected(self):
        self.assertEqual(z.validate_probe_series([-1.80, -1.88, -1.82], probe_policy()).status, z.SeriesStatus.HIGH_SPREAD)

    def test_plausibility_and_nonfinite_rejected(self):
        self.assertEqual(z.validate_probe_series([-1.8, -1.82, -3.2], probe_policy()).status, z.SeriesStatus.OUT_OF_PLAUSIBLE_RANGE)
        self.assertEqual(z.validate_probe_series([-1.8, math.nan, -1.82], probe_policy()).status, z.SeriesStatus.NON_FINITE)


class ReferenceDecisionTests(unittest.TestCase):
    def setUp(self):
        self.policy = z.ReferenceDecisionPolicy(0.10, 0.03)

    def test_alignment_sign_is_current_minus_mesh(self):
        d = z.decide_reference_alignment(accepted(), mesh_reference=-1.87, policy=self.policy)
        self.assertEqual(d.kind, z.ReferenceDecisionKind.ALIGN)
        self.assertAlmostEqual(d.alignment_delta, 0.05)

    def test_boundary_is_not_auto_applied(self):
        d = z.decide_reference_alignment(accepted((-1.77, -1.77, -1.77)), mesh_reference=-1.87, policy=self.policy)
        self.assertEqual(d.kind, z.ReferenceDecisionKind.RECONFIRM_REQUIRED)

    def test_large_delta_requires_real_confirmation(self):
        first = accepted((-1.52, -1.52, -1.52))
        d = z.decide_reference_alignment(first, mesh_reference=-1.87, policy=self.policy)
        self.assertEqual(d.kind, z.ReferenceDecisionKind.RECONFIRM_REQUIRED)
        second = accepted((-1.53, -1.52, -1.52))
        d = z.decide_reference_alignment(first, mesh_reference=-1.87, policy=self.policy, confirmation_series=second)
        self.assertEqual(d.kind, z.ReferenceDecisionKind.HARDWARE_CHANGE_SUSPECTED)

    def test_large_delta_not_reproduced_rejects(self):
        first = accepted((-1.52, -1.52, -1.52))
        normal = accepted((-1.83, -1.82, -1.82))
        d = z.decide_reference_alignment(first, mesh_reference=-1.87, policy=self.policy, confirmation_series=normal)
        self.assertEqual(d.kind, z.ReferenceDecisionKind.REJECT)
        self.assertEqual(d.reason, "large_delta_not_reproduced")

    def test_inconsistent_large_confirmation_rejects(self):
        first = accepted((-1.52, -1.52, -1.52))
        inconsistent = accepted((-1.64, -1.64, -1.64))
        d = z.decide_reference_alignment(first, mesh_reference=-1.87, policy=self.policy, confirmation_series=inconsistent)
        self.assertEqual(d.kind, z.ReferenceDecisionKind.REJECT)

    def test_bad_series_never_aligns(self):
        bad = z.validate_probe_series([-1.52, -1.83, -1.84], probe_policy())
        d = z.decide_reference_alignment(bad, mesh_reference=-1.87, policy=self.policy)
        self.assertEqual(d.kind, z.ReferenceDecisionKind.REJECT)
        self.assertIsNone(d.alignment_delta)


class MeshPolicyTests(unittest.TestCase):
    def setUp(self):
        self.mesh = z.MeshState(saved_profile="auto", saved_reference=-1.87)
        self.policy = z.ReferenceDecisionPolicy(0.10, 0.03)

    def test_saved_requires_existing_mesh(self):
        self.assertFalse(z.decide_mesh_mode(z.MeshMode.SAVED, z.MeshState()).accepted)
        self.assertTrue(z.decide_mesh_mode(z.MeshMode.SAVED, self.mesh).accepted)

    def test_saved_check_applies_one_validated_alignment(self):
        ref = z.decide_reference_alignment(accepted(), mesh_reference=-1.87, policy=self.policy)
        d = z.decide_mesh_mode(z.MeshMode.SAVED_CHECK, self.mesh, ref)
        self.assertTrue(d.accepted)
        self.assertAlmostEqual(d.auto_alignment, 0.05)

    def test_saved_check_rejects_large_delta(self):
        ref = z.decide_reference_alignment(accepted((-1.52, -1.52, -1.52)), mesh_reference=-1.87, policy=self.policy)
        self.assertFalse(z.decide_mesh_mode(z.MeshMode.SAVED_CHECK, self.mesh, ref).accepted)

    def test_runtime_is_explicit_build_without_save(self):
        d = z.decide_mesh_mode(z.MeshMode.RUNTIME, self.mesh)
        self.assertEqual(d.action, z.MeshAction.BUILD_RUNTIME)
        self.assertEqual(d.auto_alignment, 0)


class StateMachineTests(unittest.TestCase):
    def test_happy_path(self):
        path = [z.CalibrationState.PRECHECK, z.CalibrationState.PREPARE_PROBE, z.CalibrationState.TARE,
                z.CalibrationState.SAFE_APPROACH, z.CalibrationState.SLOW_CONTACT_SEARCH,
                z.CalibrationState.VERIFY_CONTACT, z.CalibrationState.REPEATABILITY_CHECK,
                z.CalibrationState.REFERENCE_DECISION, z.CalibrationState.MESH_DECISION,
                z.CalibrationState.OFFSET_COMPOSITION, z.CalibrationState.READY]
        model = z.CalibrationModel()
        for target in path: model = model.transition(target)
        self.assertEqual(model.state, z.CalibrationState.READY)

    def test_illegal_transitions_rejected(self):
        with self.assertRaises(z.InvalidTransition): z.CalibrationModel().transition(z.CalibrationState.SLOW_CONTACT_SEARCH)
        with self.assertRaises(z.InvalidTransition): z.CalibrationModel(state=z.CalibrationState.ABORT).transition(z.CalibrationState.PRECHECK)

    def test_hardware_change_must_abort_through_atomic_abort(self):
        model = z.CalibrationModel(state=z.CalibrationState.REFERENCE_DECISION, offsets=z.OffsetComposition(0.04, -0.03, 0.01, 0.005))
        model = model.transition(z.CalibrationState.HARDWARE_CHANGE_SUSPECTED)
        with self.assertRaises(z.InvalidTransition): model.transition(z.CalibrationState.ABORT)
        model = model.abort("confirmed_large_delta", motion_state_allows_retract=True)
        self.assertEqual(model.state, z.CalibrationState.ABORT)
        self.assertAlmostEqual(model.offsets.persistent_user, -0.03)
        self.assertEqual(model.offsets.auto_alignment, 0)
        self.assertTrue(model.retract_required)

    def test_cancel_every_operational_state_preserves_persistent(self):
        for state in z.CalibrationState:
            if state in {z.CalibrationState.IDLE, z.CalibrationState.ABORT}: continue
            with self.subTest(state=state):
                model = z.CalibrationModel(state, z.OffsetComposition(0.04, -0.03, 0.01, 0.005, 0.002), "auto", "runtime")
                cancelled = model.cancel(motion_state_allows_retract=True)
                self.assertEqual(cancelled.state, z.CalibrationState.ABORT)
                self.assertAlmostEqual(cancelled.offsets.persistent_user, -0.03)
                self.assertEqual(cancelled.offsets.auto_alignment, 0)
                self.assertEqual(cancelled.offsets.slicer_job, 0)
                self.assertEqual(cancelled.runtime_mesh_id, None)
                self.assertEqual(cancelled.saved_mesh_id, "auto")

    def test_abort_requires_fresh_reset(self):
        model = z.CalibrationModel(state=z.CalibrationState.PRECHECK).abort("x", motion_state_allows_retract=False)
        with self.assertRaises(z.InvalidTransition): model.transition(z.CalibrationState.PRECHECK)
        model = model.reset_after_abort()
        self.assertEqual(model.transition(z.CalibrationState.PRECHECK).state, z.CalibrationState.PRECHECK)


class DiagnosticsTests(unittest.TestCase):
    def test_bounded_retention_and_correlation(self):
        log = z.BoundedDiagnosticLog(2)
        log.emit("probe_series", correlation_id="run-1", payload={"samples": [-1.82]})
        log.emit("reference_decision", correlation_id="run-1", payload={"decision": "accept"})
        log.emit("offset_composed", correlation_id="run-1", payload={"effective": -0.03})
        events = log.recent()
        self.assertEqual(len(events), 2)
        self.assertEqual([e.sequence for e in events], [2, 3])
        self.assertTrue(all(e.correlation_id == "run-1" for e in events))

    def test_secret_like_payload_rejected(self):
        log = z.BoundedDiagnosticLog(3)
        with self.assertRaises(z.PolicyError): log.emit("x", correlation_id="r", payload={"nested": {"api_key": "secret"}})

    def test_corrupt_old_record_is_ignored(self):
        log = z.BoundedDiagnosticLog(3)
        self.assertFalse(log.ingest_untrusted_record({"schema_version": "old"}))
        self.assertEqual(log.recent(), ())

    def test_anomaly_event_can_reconstruct_decision(self):
        payload = {"expected_reference": -1.87, "measured_samples": [-1.52, -1.52, -1.52],
                   "mesh": {"mode": "saved+check", "profile": "auto"},
                   "offset": {"auto": 0, "user": -0.03, "job": 0, "live": 0},
                   "decision": "reconfirm_required", "tare": {"residual": 80}}
        event = z.BoundedDiagnosticLog(5).emit("reference_decision", correlation_id="anomaly-1", payload=payload)
        for key in ("expected_reference", "measured_samples", "mesh", "offset", "decision", "tare"):
            self.assertIn(key, event.payload)


class FakeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.env = z.SearchEnvelopePolicy(-5, 220, 0.25, 0.20).build(-1.8)

    def test_early_trigger(self):
        with self.assertRaises(z.EarlyTrigger): z.FakeKlipperMoonrakerAdapter(probe_script=[-1.40]).probe_once(self.env)

    def test_no_trigger_stops_at_lower_bound(self):
        adapter = z.FakeKlipperMoonrakerAdapter(probe_script=[None])
        with self.assertRaises(z.NoTrigger): adapter.probe_once(self.env)
        self.assertIn(("probe_stop_at_lower_bound", self.env.lower_z), adapter.calls)

    def test_trigger_below_lower_bound_rejected(self):
        with self.assertRaises(z.LowerBoundViolation): z.FakeKlipperMoonrakerAdapter(probe_script=[-2.20]).probe_once(self.env)

    def test_not_ready_unhomed_printing_paused_fail_closed(self):
        cases = [z.FakeKlipperMoonrakerAdapter(klippy_ready=False), z.FakeKlipperMoonrakerAdapter(homed=False),
                 z.FakeKlipperMoonrakerAdapter(print_state="printing"), z.FakeKlipperMoonrakerAdapter(print_state="paused")]
        for adapter in cases:
            with self.subTest(adapter=adapter):
                with self.assertRaises(z.AdapterNotReady): adapter.ensure_ready_for_calibration()

    def test_disconnect_and_reconnect(self):
        adapter = z.FakeKlipperMoonrakerAdapter(effective_offset=-0.03)
        adapter.disconnect()
        with self.assertRaises(z.CommunicationFailure): adapter.read_effective_offset()
        adapter.reconnect(); self.assertAlmostEqual(adapter.read_effective_offset(), -0.03)

    def test_cancel_blocks_motion_and_offset_write(self):
        adapter = z.FakeKlipperMoonrakerAdapter(probe_script=[-1.82]); adapter.request_cancel()
        with self.assertRaises(z.AdapterCancelled): adapter.probe_once(self.env)
        with self.assertRaises(z.AdapterCancelled): adapter.set_effective_offset(-0.02)

    def test_h7_missing_delayed_contradictory_do_not_remove_primary_bound(self):
        for item in (None, z.H7Reading(z.H7Status.DELAYED), z.H7Reading(z.H7Status.CONTRADICTORY, 999)):
            adapter = z.FakeKlipperMoonrakerAdapter(probe_script=[None], h7_script=[item])
            adapter.read_h7()
            with self.assertRaises(z.NoTrigger): adapter.probe_once(self.env)
            self.assertIn(("probe_stop_at_lower_bound", self.env.lower_z), adapter.calls)

    def test_signless_weight_and_signed_raw_are_distinct(self):
        adapter = z.FakeKlipperMoonrakerAdapter(h7_script=[z.H7Reading(z.H7Status.AVAILABLE, 80, False), z.H7Reading(z.H7Status.AVAILABLE, -80, True)])
        self.assertFalse(adapter.read_h7().signed)
        raw = adapter.read_h7(); self.assertTrue(raw.signed); self.assertEqual(raw.value, -80)

    def test_tare_accepts_near_zero_not_only_exact_zero(self):
        policy = z.TarePolicy(100)
        self.assertTrue(policy.accepts(0)); self.assertTrue(policy.accepts(80)); self.assertTrue(policy.accepts(-80)); self.assertFalse(policy.accepts(101))

    def test_runtime_mesh_does_not_overwrite_saved_until_explicit_save(self):
        adapter = z.FakeKlipperMoonrakerAdapter(saved_meshes={"auto": -1.87})
        before = dict(adapter.saved_meshes)
        adapter.build_runtime_mesh("runtime-1", reference=-1.82)
        self.assertEqual(adapter.saved_meshes, before)
        adapter.explicit_save_runtime_mesh(reference=-1.82)
        self.assertEqual(adapter.saved_meshes["runtime-1"], -1.82)

    def test_external_offset_not_silently_corrected_back(self):
        c = z.OffsetComposition(auto_alignment=0.04, persistent_user=-0.03)
        adapter = z.FakeKlipperMoonrakerAdapter(effective_offset=c.known_total)
        adapter.external_set_effective_offset(0.05)
        reconciled = c.reconcile_actual(adapter.read_effective_offset(), tolerance=0.0005)
        self.assertNotEqual(reconciled.external_unknown, 0)
        self.assertFalse(any(name == "set_effective_offset" for name, _ in adapter.calls))


if __name__ == "__main__":
    unittest.main()
