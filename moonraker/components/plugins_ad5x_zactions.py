"""Semantic action builder for Z Calibration Subsystem v2.

This layer intentionally has no Moonraker/Klipper I/O. It maps user-facing
calibration actions to the fake-proven orchestrator request contract and keeps
plain `saved` mesh selection out of the measurement/action path.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from . import plugins_ad5x_zcalibration as core
from .plugins_ad5x_zorchestrator import (
    CalibrationRunRequest,
    CalibrationRunPolicies,
)


class CalibrationAction(str, Enum):
    CHECK_Z = "check_z"
    FULL_CALIBRATION = "full_calibration"


@dataclass(frozen=True)
class CalibrationActionContext:
    correlation_id: str
    action: CalibrationAction
    policies: CalibrationRunPolicies
    offsets: core.OffsetComposition
    mesh: core.MeshState
    trusted_reference: Optional[float] = None
    runtime_mesh_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.correlation_id.strip():
            raise core.PolicyError("correlation_id is required")
        if self.trusted_reference is not None:
            core._finite(self.trusted_reference, "trusted_reference")


def build_calibration_run_request(
    context: CalibrationActionContext,
) -> CalibrationRunRequest:
    if context.action is CalibrationAction.CHECK_Z:
        if context.mesh.saved_profile is None or context.mesh.saved_reference is None:
            raise core.PolicyError("check_z requires a saved mesh and reference")
        return CalibrationRunRequest(
            correlation_id=context.correlation_id,
            mesh_mode=core.MeshMode.SAVED_CHECK,
            mesh=context.mesh,
            policies=context.policies,
            offsets=context.offsets,
            trusted_reference=(
                context.trusted_reference
                if context.trusted_reference is not None
                else context.mesh.saved_reference
            ),
            expected_reference=context.mesh.saved_reference,
            initial_acquisition=False,
        )

    if context.action is CalibrationAction.FULL_CALIBRATION:
        if not context.runtime_mesh_id:
            raise core.PolicyError("full_calibration requires runtime_mesh_id")
        return CalibrationRunRequest(
            correlation_id=context.correlation_id,
            mesh_mode=core.MeshMode.RUNTIME,
            mesh=context.mesh,
            policies=context.policies,
            offsets=context.offsets,
            trusted_reference=context.trusted_reference,
            expected_reference=None,
            initial_acquisition=context.trusted_reference is None,
            runtime_mesh_id=context.runtime_mesh_id,
        )

    raise core.PolicyError(f"unsupported calibration action: {context.action!r}")
