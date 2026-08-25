"""Hardware-evidence and preflight gate for Z Calibration motion.

No numeric release thresholds live here. A caller must supply an explicit
CalibrationRunPolicies bundle plus evidence that those numbers came from
sources, repeated hardware runs and a documented safety margin. This module
cannot prove that the evidence is truthful; it makes the evidence requirement
machine-visible and prevents a bare boolean feature flag from being sufficient.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from . import plugins_ad5x_zcalibration as core
from .plugins_ad5x_zorchestrator import CalibrationRunPolicies


class MotionBlocker(str, Enum):
    POLICY_MISSING = "hardware_policy_missing"
    POLICY_SOURCE_MISSING = "hardware_policy_source_missing"
    POLICY_REPEATED_RUNS_MISSING = "hardware_policy_repeated_runs_missing"
    POLICY_MARGIN_MISSING = "hardware_policy_margin_missing"
    POLICY_NOT_ACCEPTED = "hardware_policy_not_owner_accepted"
    WRITE_GATE_CLOSED = "offset_write_gate_closed"
    HOOK_NOT_LOADED = "z_lifecycle_hook_not_loaded"
    KLIPPY_NOT_READY = "klippy_not_ready"
    PRINTER_NOT_IDLE = "printer_not_idle"
    JOB_LIFECYCLE_ACTIVE = "job_lifecycle_active"
    AXES_NOT_HOMED = "axes_not_homed"
    EFFECTIVE_OFFSET_UNAVAILABLE = "effective_offset_unavailable"
    DIRTY_TRANSIENT_BASELINE = "dirty_transient_baseline"
    EXTERNAL_UNKNOWN_OFFSET = "external_unknown_offset"


@dataclass(frozen=True)
class HardwarePolicyEvidence:
    policy_id: str
    source_refs: tuple[str, ...]
    hardware_run_ids: tuple[str, ...]
    margin_rationale: str
    owner_accepted: bool = False

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise core.PolicyError("hardware policy_id is required")
        if any(not item.strip() for item in self.source_refs):
            raise core.PolicyError("hardware policy source_refs cannot contain blanks")
        if any(not item.strip() for item in self.hardware_run_ids):
            raise core.PolicyError("hardware_run_ids cannot contain blanks")
        if len(set(self.hardware_run_ids)) != len(self.hardware_run_ids):
            raise core.PolicyError("hardware_run_ids must be distinct")


@dataclass(frozen=True)
class AcceptedCalibrationPolicy:
    policies: CalibrationRunPolicies
    evidence: HardwarePolicyEvidence


@dataclass(frozen=True)
class CalibrationPreflightInput:
    policy: Optional[AcceptedCalibrationPolicy]
    write_gate_enabled: bool
    hook_loaded: bool
    klippy_ready: bool
    print_state: str
    homed_axes: str
    job_phase: str
    offsets: core.OffsetComposition
    actual_effective: Optional[float]
    effective_offset_tolerance: float

    def __post_init__(self) -> None:
        tolerance = core._finite(
            self.effective_offset_tolerance, "effective_offset_tolerance"
        )
        if tolerance < 0:
            raise core.PolicyError("effective_offset_tolerance cannot be negative")
        if self.actual_effective is not None:
            core._finite(self.actual_effective, "actual_effective")


@dataclass(frozen=True)
class CalibrationPreflightResult:
    ready_for_motion: bool
    blockers: tuple[MotionBlocker, ...]
    policy_id: Optional[str]
    external_unknown: Optional[float]


def evaluate_calibration_preflight(
    request: CalibrationPreflightInput,
) -> CalibrationPreflightResult:
    blockers: list[MotionBlocker] = []
    external_unknown: Optional[float] = None

    if request.policy is None:
        blockers.append(MotionBlocker.POLICY_MISSING)
        policy_id = None
    else:
        evidence = request.policy.evidence
        policy_id = evidence.policy_id
        if not evidence.source_refs:
            blockers.append(MotionBlocker.POLICY_SOURCE_MISSING)
        # "Repeated" is encoded literally as at least two distinct hardware
        # runs. This is not a claim that two runs are sufficient for release;
        # more evidence may be required by the actual hardware acceptance plan.
        if len(evidence.hardware_run_ids) < 2:
            blockers.append(MotionBlocker.POLICY_REPEATED_RUNS_MISSING)
        if not evidence.margin_rationale.strip():
            blockers.append(MotionBlocker.POLICY_MARGIN_MISSING)
        if not evidence.owner_accepted:
            blockers.append(MotionBlocker.POLICY_NOT_ACCEPTED)

    if not request.write_gate_enabled:
        blockers.append(MotionBlocker.WRITE_GATE_CLOSED)
    if not request.hook_loaded:
        blockers.append(MotionBlocker.HOOK_NOT_LOADED)
    if not request.klippy_ready:
        blockers.append(MotionBlocker.KLIPPY_NOT_READY)
    if request.print_state != "standby":
        blockers.append(MotionBlocker.PRINTER_NOT_IDLE)
    if request.job_phase != "idle":
        blockers.append(MotionBlocker.JOB_LIFECYCLE_ACTIVE)
    if not all(axis in request.homed_axes for axis in "xyz"):
        blockers.append(MotionBlocker.AXES_NOT_HOMED)

    if any(
        abs(value) > request.effective_offset_tolerance
        for value in (
            request.offsets.auto_alignment,
            request.offsets.slicer_job,
            request.offsets.live_adjustment,
            request.offsets.external_unknown,
        )
    ):
        blockers.append(MotionBlocker.DIRTY_TRANSIENT_BASELINE)

    if request.actual_effective is None:
        blockers.append(MotionBlocker.EFFECTIVE_OFFSET_UNAVAILABLE)
    else:
        reconciled = request.offsets.reconcile_actual(
            request.actual_effective,
            tolerance=request.effective_offset_tolerance,
        )
        external_unknown = reconciled.external_unknown
        if abs(external_unknown) > request.effective_offset_tolerance:
            blockers.append(MotionBlocker.EXTERNAL_UNKNOWN_OFFSET)

    blockers = list(dict.fromkeys(blockers))
    return CalibrationPreflightResult(
        ready_for_motion=not blockers,
        blockers=tuple(blockers),
        policy_id=policy_id,
        external_unknown=external_unknown,
    )
