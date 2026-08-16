"""Production motion-policy gate for Z Calibration Subsystem v2.

This module contains no printer I/O and intentionally defines no release
motion defaults.  A real motion adapter may only be constructed around an
explicit, evidence-linked policy that passes both the generic calibration
preflight and the concrete motion-envelope checks below.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from . import plugins_ad5x_zcalibration as core
from .plugins_ad5x_zorchestrator import CalibrationRunRequest
from .plugins_ad5x_zpolicy import (
    CalibrationPreflightInput,
    CalibrationPreflightResult,
    evaluate_calibration_preflight,
)


class MotionPolicyBlocker(str, Enum):
    MOTION_GATE_CLOSED = "motion_gate_closed"
    POLICY_MISSING = "motion_policy_missing"
    POLICY_ID_MISMATCH = "motion_policy_evidence_id_mismatch"
    REFERENCE_OUTSIDE_XY_BOUNDS = "reference_point_outside_xy_bounds"
    CLEARANCE_OUTSIDE_Z_BOUNDS = "travel_clearance_outside_z_bounds"
    CLEARANCE_NOT_ABOVE_SEARCH = "travel_clearance_not_above_search_envelope"
    CONTACT_NOT_SLOWER_THAN_APPROACH = "contact_search_not_slower_than_safe_approach"
    SEARCH_ENVELOPE_INVALID = "search_envelope_invalid_for_motion"


@dataclass(frozen=True)
class MachineMotionBounds:
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float

    def __post_init__(self) -> None:
        values = {
            "min_x": self.min_x,
            "max_x": self.max_x,
            "min_y": self.min_y,
            "max_y": self.max_y,
            "min_z": self.min_z,
            "max_z": self.max_z,
        }
        for name, value in values.items():
            core._finite(value, name)
        if self.min_x >= self.max_x:
            raise core.PolicyError("machine min_x must be below max_x")
        if self.min_y >= self.max_y:
            raise core.PolicyError("machine min_y must be below max_y")
        if self.min_z >= self.max_z:
            raise core.PolicyError("machine min_z must be below max_z")


@dataclass(frozen=True)
class ProductionMotionPolicy:
    """Explicit hardware-accepted motion values; every field is required."""

    policy_id: str
    reference_x: float
    reference_y: float
    travel_clearance_z: float
    safe_approach_speed: float
    contact_search_speed: float
    sample_retract_distance: float
    abort_retract_distance: float
    retract_speed: float

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise core.PolicyError("motion policy_id is required")
        for name in (
            "reference_x",
            "reference_y",
            "travel_clearance_z",
            "safe_approach_speed",
            "contact_search_speed",
            "sample_retract_distance",
            "abort_retract_distance",
            "retract_speed",
        ):
            core._finite(getattr(self, name), name)
        for name in (
            "safe_approach_speed",
            "contact_search_speed",
            "sample_retract_distance",
            "abort_retract_distance",
            "retract_speed",
        ):
            if getattr(self, name) <= 0:
                raise core.PolicyError(f"{name} must be positive")


@dataclass(frozen=True)
class ProductionMotionPreflightInput:
    calibration: CalibrationPreflightInput
    run: CalibrationRunRequest
    motion_policy: Optional[ProductionMotionPolicy]
    machine_bounds: MachineMotionBounds
    motion_gate_enabled: bool


@dataclass(frozen=True)
class ProductionMotionPreflightResult:
    ready_for_motion: bool
    calibration: CalibrationPreflightResult
    blockers: tuple[MotionPolicyBlocker, ...]
    motion_policy_id: Optional[str]
    envelope: Optional[core.SearchEnvelope]


def evaluate_production_motion_preflight(
    request: ProductionMotionPreflightInput,
) -> ProductionMotionPreflightResult:
    """Return ready only when generic + concrete motion gates both pass."""

    calibration = evaluate_calibration_preflight(request.calibration)
    blockers: list[MotionPolicyBlocker] = []
    envelope: Optional[core.SearchEnvelope] = None

    if not request.motion_gate_enabled:
        blockers.append(MotionPolicyBlocker.MOTION_GATE_CLOSED)

    motion = request.motion_policy
    if motion is None:
        blockers.append(MotionPolicyBlocker.POLICY_MISSING)
        motion_policy_id = None
    else:
        motion_policy_id = motion.policy_id
        accepted = request.calibration.policy
        if accepted is None or accepted.evidence.policy_id != motion.policy_id:
            blockers.append(MotionPolicyBlocker.POLICY_ID_MISMATCH)

        bounds = request.machine_bounds
        if not (
            bounds.min_x <= motion.reference_x <= bounds.max_x
            and bounds.min_y <= motion.reference_y <= bounds.max_y
        ):
            blockers.append(MotionPolicyBlocker.REFERENCE_OUTSIDE_XY_BOUNDS)

        if not (bounds.min_z < motion.travel_clearance_z <= bounds.max_z):
            blockers.append(MotionPolicyBlocker.CLEARANCE_OUTSIDE_Z_BOUNDS)

        if motion.contact_search_speed >= motion.safe_approach_speed:
            blockers.append(MotionPolicyBlocker.CONTACT_NOT_SLOWER_THAN_APPROACH)

        try:
            envelope = request.run.policies.search.build(
                request.run.search_reference,
                initial_acquisition=request.run.initial_acquisition,
            )
        except core.PolicyError:
            blockers.append(MotionPolicyBlocker.SEARCH_ENVELOPE_INVALID)
        else:
            # Clearance is a distinct non-contact travel zone and therefore
            # must sit above the entire concrete contact-search envelope.
            if motion.travel_clearance_z <= envelope.upper_z:
                blockers.append(MotionPolicyBlocker.CLEARANCE_NOT_ABOVE_SEARCH)

    blockers = list(dict.fromkeys(blockers))
    return ProductionMotionPreflightResult(
        ready_for_motion=calibration.ready_for_motion and not blockers,
        calibration=calibration,
        blockers=tuple(blockers),
        motion_policy_id=motion_policy_id,
        envelope=envelope,
    )
