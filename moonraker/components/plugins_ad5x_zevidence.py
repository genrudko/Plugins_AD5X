"""Non-authorizing Hardware Evidence Run v1 schema for Z Calibration.

The records in this module are observations, not motion permissions.  They may
carry raw bed-mesh and reference-series data plus exact software/hardware
provenance.  No safety threshold is derived here and no evidence record can
open either the write gate or the motion gate by itself.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import statistics
from typing import Optional

from . import plugins_ad5x_zcalibration as core


EVIDENCE_SCHEMA_VERSION = "1.0"


class EvidencePhase(str, Enum):
    READ_ONLY_BASELINE = "gate_a_read_only_baseline"
    CONTROLLED_MEASUREMENT = "gate_b_controlled_measurement"
    REPEATABILITY = "gate_c_repeatability"


@dataclass(frozen=True)
class BedMeshObservation:
    source_id: str
    values: tuple[tuple[float, ...], ...]

    def __post_init__(self) -> None:
        if not self.source_id.strip():
            raise core.PolicyError("bed mesh source_id is required")
        if not self.values or not self.values[0]:
            raise core.PolicyError("bed mesh values cannot be empty")
        width = len(self.values[0])
        for row in self.values:
            if len(row) != width:
                raise core.PolicyError("bed mesh must be rectangular")
            for value in row:
                core._finite(value, "bed_mesh_value")

    @property
    def flat_values(self) -> tuple[float, ...]:
        return tuple(value for row in self.values for value in row)

    @property
    def min_z(self) -> float:
        return min(self.flat_values)

    @property
    def max_z(self) -> float:
        return max(self.flat_values)

    @property
    def span(self) -> float:
        return self.max_z - self.min_z


@dataclass(frozen=True)
class ReferenceSeriesObservation:
    samples: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.samples:
            raise core.PolicyError("reference series samples cannot be empty")
        for value in self.samples:
            core._finite(value, "reference_sample")

    @property
    def mean(self) -> float:
        return statistics.fmean(self.samples)

    @property
    def median(self) -> float:
        return statistics.median(self.samples)

    @property
    def spread(self) -> float:
        return max(self.samples) - min(self.samples)

    @property
    def drift(self) -> float:
        return self.samples[-1] - self.samples[0]


@dataclass(frozen=True)
class HardwareEvidenceRunV1:
    run_id: str
    phase: EvidencePhase
    repository_sha: str
    zmod_version: str
    klipper_version: str
    moonraker_version: str
    hardware_setup_id: str
    source_refs: tuple[str, ...]
    setup_notes: str
    bed_mesh: Optional[BedMeshObservation] = None
    reference_series: Optional[ReferenceSeriesObservation] = None
    tare_residual: Optional[float] = None
    h7_status: Optional[core.H7Status] = None
    cleanup_confirmed: Optional[bool] = None
    persistent_state_changed: bool = False
    saved_mesh_changed: bool = False
    stop_condition_observed: bool = False

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise core.PolicyError("hardware evidence run_id is required")
        sha = self.repository_sha.strip().lower()
        if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha):
            raise core.PolicyError("repository_sha must be an exact 40-character SHA")
        for name, value in (
            ("zmod_version", self.zmod_version),
            ("klipper_version", self.klipper_version),
            ("moonraker_version", self.moonraker_version),
            ("hardware_setup_id", self.hardware_setup_id),
            ("setup_notes", self.setup_notes),
        ):
            if not value.strip():
                raise core.PolicyError(f"{name} is required")
        if not self.source_refs:
            raise core.PolicyError("hardware evidence source_refs are required")
        if any(not item.strip() for item in self.source_refs):
            raise core.PolicyError("hardware evidence source_refs cannot contain blanks")
        if len(set(self.source_refs)) != len(self.source_refs):
            raise core.PolicyError("hardware evidence source_refs must be distinct")
        if self.tare_residual is not None:
            core._finite(self.tare_residual, "tare_residual")

    @property
    def review_blockers(self) -> tuple[str, ...]:
        """Return objective evidence-completeness blockers only.

        An empty tuple means the record is suitable for human/policy review. It
        does *not* mean that any threshold or motion policy has been accepted.
        """

        blockers: list[str] = []
        if self.phase is EvidencePhase.READ_ONLY_BASELINE:
            blockers.append("measurement_phase_required")
        if self.reference_series is None:
            blockers.append("reference_series_missing")
        if self.cleanup_confirmed is not True:
            blockers.append("cleanup_not_confirmed")
        if self.persistent_state_changed:
            blockers.append("persistent_state_changed")
        if self.saved_mesh_changed:
            blockers.append("saved_mesh_changed")
        if self.stop_condition_observed:
            blockers.append("stop_condition_observed")
        return tuple(blockers)

    @property
    def complete_for_policy_review(self) -> bool:
        return not self.review_blockers


@dataclass(frozen=True)
class HardwareEvidenceDatasetV1:
    runs: tuple[HardwareEvidenceRunV1, ...]

    def __post_init__(self) -> None:
        run_ids = tuple(run.run_id for run in self.runs)
        if len(set(run_ids)) != len(run_ids):
            raise core.PolicyError("hardware evidence run_ids must be distinct")

    @property
    def reviewable_run_ids(self) -> tuple[str, ...]:
        return tuple(run.run_id for run in self.runs if run.complete_for_policy_review)

    @property
    def repeatability_run_ids(self) -> tuple[str, ...]:
        return tuple(
            run.run_id
            for run in self.runs
            if run.phase is EvidencePhase.REPEATABILITY
            and run.complete_for_policy_review
        )
