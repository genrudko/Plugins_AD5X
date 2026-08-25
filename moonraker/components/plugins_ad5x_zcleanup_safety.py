"""Fail-closed cleanup disposition for Z Calibration Subsystem v2.

This module performs no printer I/O.  It turns the orchestrator's independent
cleanup confirmations into one explicit continuation disposition.  Missing or
non-true confirmations are unsafe by construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class CleanupDisposition(str, Enum):
    CLEAN = "clean"
    UNSAFE = "unsafe"


_REQUIRED_CONFIRMATIONS = (
    "offset_reconciled",
    "mesh_reconciled",
    "retracted",
)


@dataclass(frozen=True)
class CleanupAssessment:
    disposition: CleanupDisposition
    failed_confirmations: tuple[str, ...]

    @property
    def safe_to_continue(self) -> bool:
        return self.disposition is CleanupDisposition.CLEAN


def assess_cleanup(cleanup: Mapping[str, bool]) -> CleanupAssessment:
    """Classify cleanup without assuming that missing evidence means success."""

    failed = tuple(
        key for key in _REQUIRED_CONFIRMATIONS if cleanup.get(key) is not True
    )
    return CleanupAssessment(
        disposition=(
            CleanupDisposition.UNSAFE if failed else CleanupDisposition.CLEAN
        ),
        failed_confirmations=failed,
    )
