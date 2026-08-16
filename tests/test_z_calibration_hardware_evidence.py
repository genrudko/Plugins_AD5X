from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MOONRAKER = ROOT / "moonraker"
COMPONENTS = MOONRAKER / "components"
MODULE = COMPONENTS / "plugins_ad5x_zevidence.py"


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
        "moonraker.components.plugins_ad5x_zevidence_test", MODULE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load hardware evidence module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ze = load_module()
z = ze.core
SHA = "0123456789abcdef0123456789abcdef01234567"


def run(**overrides):
    values = dict(
        run_id="hw-run-001",
        phase=ze.EvidencePhase.CONTROLLED_MEASUREMENT,
        repository_sha=SHA,
        zmod_version="zmod-test-version",
        klipper_version="klipper-test-version",
        moonraker_version="moonraker-test-version",
        hardware_setup_id="ad5x-current-hotend-current-plate",
        source_refs=("diagnostic:hw-run-001",),
        setup_notes="test-only fixture; no production threshold implied",
        reference_series=ze.ReferenceSeriesObservation((-1.82, -1.83, -1.81)),
        tare_residual=0.0,
        h7_status=z.H7Status.MISSING,
        cleanup_confirmed=True,
    )
    values.update(overrides)
    return ze.HardwareEvidenceRunV1(**values)


class BedMeshObservationTests(unittest.TestCase):
    def test_mesh_preserves_raw_values_and_exposes_descriptive_span_only(self) -> None:
        mesh = ze.BedMeshObservation(
            source_id="mesh-after-mechanical-service",
            values=((0.10, 0.05), (-0.02, 0.03)),
        )
        self.assertEqual(mesh.flat_values, (0.10, 0.05, -0.02, 0.03))
        self.assertAlmostEqual(mesh.min_z, -0.02)
        self.assertAlmostEqual(mesh.max_z, 0.10)
        self.assertAlmostEqual(mesh.span, 0.12)

    def test_mesh_must_be_nonempty_rectangular_and_finite(self) -> None:
        with self.assertRaises(z.PolicyError):
            ze.BedMeshObservation(source_id="mesh", values=())
        with self.assertRaises(z.PolicyError):
            ze.BedMeshObservation(source_id="mesh", values=((0.0, 0.1), (0.2,)))
        with self.assertRaises(z.PolicyError):
            ze.BedMeshObservation(source_id="mesh", values=((0.0, float("nan")),))


class ReferenceObservationTests(unittest.TestCase):
    def test_reference_series_exposes_raw_descriptive_statistics(self) -> None:
        series = ze.ReferenceSeriesObservation((-1.82, -1.83, -1.81))
        self.assertAlmostEqual(series.mean, -1.82)
        self.assertAlmostEqual(series.median, -1.82)
        self.assertAlmostEqual(series.spread, 0.02)
        self.assertAlmostEqual(series.drift, 0.01)

    def test_reference_series_does_not_accept_empty_or_nonfinite_data(self) -> None:
        with self.assertRaises(z.PolicyError):
            ze.ReferenceSeriesObservation(())
        with self.assertRaises(z.PolicyError):
            ze.ReferenceSeriesObservation((-1.82, float("inf")))


class HardwareEvidenceRunTests(unittest.TestCase):
    def test_complete_measurement_is_only_reviewable_not_accepted(self) -> None:
        evidence = run()
        self.assertTrue(evidence.complete_for_policy_review)
        self.assertEqual(evidence.review_blockers, ())
        self.assertFalse(hasattr(evidence, "owner_accepted"))
        self.assertFalse(hasattr(evidence, "ready_for_motion"))

    def test_read_only_baseline_cannot_masquerade_as_motion_evidence(self) -> None:
        evidence = run(
            phase=ze.EvidencePhase.READ_ONLY_BASELINE,
            reference_series=None,
            cleanup_confirmed=None,
        )
        self.assertFalse(evidence.complete_for_policy_review)
        self.assertIn("measurement_phase_required", evidence.review_blockers)
        self.assertIn("reference_series_missing", evidence.review_blockers)

    def test_failed_hardware_run_is_recordable_but_not_reviewable(self) -> None:
        evidence = run(
            run_id="hw-run-failed",
            cleanup_confirmed=False,
            stop_condition_observed=True,
        )
        self.assertFalse(evidence.complete_for_policy_review)
        self.assertIn("cleanup_not_confirmed", evidence.review_blockers)
        self.assertIn("stop_condition_observed", evidence.review_blockers)

    def test_any_unintended_persistence_blocks_policy_review(self) -> None:
        self.assertIn(
            "persistent_state_changed",
            run(persistent_state_changed=True).review_blockers,
        )
        self.assertIn(
            "saved_mesh_changed",
            run(saved_mesh_changed=True).review_blockers,
        )

    def test_exact_repository_sha_and_source_provenance_are_mandatory(self) -> None:
        with self.assertRaises(z.PolicyError):
            run(repository_sha="deadbeef")
        with self.assertRaises(z.PolicyError):
            run(source_refs=())
        with self.assertRaises(z.PolicyError):
            run(source_refs=("same", "same"))

    def test_dataset_requires_distinct_run_ids(self) -> None:
        first = run(run_id="repeat-1", phase=ze.EvidencePhase.REPEATABILITY)
        second = run(run_id="repeat-2", phase=ze.EvidencePhase.REPEATABILITY)
        dataset = ze.HardwareEvidenceDatasetV1((first, second))
        self.assertEqual(dataset.reviewable_run_ids, ("repeat-1", "repeat-2"))
        self.assertEqual(dataset.repeatability_run_ids, ("repeat-1", "repeat-2"))
        with self.assertRaises(z.PolicyError):
            ze.HardwareEvidenceDatasetV1((first, first))


if __name__ == "__main__":
    unittest.main()
