"""Pure calibration math for CALIBRATION-CENTER-001.

This module has no printer I/O. Runtime motion remains in Klipper/Z-Mod macros;
these functions make the coordinate/correction model independently testable.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Iterable


class CalibrationRejected(ValueError):
    """Raised when measurement evidence must fail closed."""


@dataclass(frozen=True)
class Measurement:
    samples: tuple[float, ...]
    minimum: float
    maximum: float
    mean: float
    median: float
    spread: float


def evaluate_samples(
    samples: Iterable[float], *, max_range: float = 0.030
) -> Measurement:
    values = tuple(float(value) for value in samples)
    if len(values) != 5:
        raise CalibrationRejected("exactly five independent samples are required")
    if not all(math.isfinite(value) for value in values):
        raise CalibrationRejected("all samples must be finite")
    if not 0.005 <= max_range <= 0.100:
        raise CalibrationRejected("max_range is outside the supported safety bounds")

    minimum = min(values)
    maximum = max(values)
    spread = maximum - minimum
    if spread > max_range:
        raise CalibrationRejected(
            f"unstable probe series: spread {spread:.6f} > {max_range:.6f} mm"
        )

    return Measurement(
        samples=values,
        minimum=minimum,
        maximum=maximum,
        mean=statistics.fmean(values),
        median=statistics.median(values),
        spread=spread,
    )


def reference_delta(
    fresh_reference: float,
    verified_reference: float,
    *,
    max_delta: float = 0.300,
) -> float:
    """Return the upstream-compatible `fresh - saved` geometric delta."""
    fresh = float(fresh_reference)
    verified = float(verified_reference)
    if not math.isfinite(fresh) or not math.isfinite(verified):
        raise CalibrationRejected("references must be finite")
    if not 0.050 <= max_delta <= 0.500:
        raise CalibrationRejected("max_delta is outside the supported safety bounds")
    delta = fresh - verified
    if abs(delta) > max_delta:
        raise CalibrationRejected(
            f"reference delta {delta:.6f} exceeds {max_delta:.6f} mm"
        )
    return delta


def runtime_adjust(
    *,
    verified_bias: float,
    auto_delta: float,
    mesh_test: int,
    verified_global_z: float = 0.0,
    current_global_z: float = 0.0,
) -> float:
    """Return the transient Calibration Center correction for one print.

    The user's Z-Mod global offset is an independent persistent baseline.
    Calibration Center records the global value present when a profile is
    USER VERIFIED, then compensates any later global change in its own transient
    G92 layer. MESH_TEST 3/4 already owns the geometric AutoZOffset term.
    """
    bias = float(verified_bias)
    delta = float(auto_delta)
    verified_global = float(verified_global_z)
    current_global = float(current_global_z)
    if not all(
        math.isfinite(value)
        for value in (bias, delta, verified_global, current_global)
    ):
        raise CalibrationRejected("runtime corrections must be finite")
    cc_auto = 0.0 if int(mesh_test) in (3, 4) else delta
    return bias + cc_auto + (verified_global - current_global)


def initial_verified_process_bias(*, live_adjust: float) -> float:
    """For a new profile, deliberate built-in-test transient adjustment is bias."""
    value = float(live_adjust)
    if not math.isfinite(value):
        raise CalibrationRejected("live adjustment must be finite")
    return value


def reverified_process_bias(
    *, applied_profile_correction: float, live_adjust: float
) -> float:
    """Re-anchor a verified profile without changing its effective print plane.

    The already-applied transient correction may contain the old bias, a fresh
    physical-reference delta, and compensation for a changed global Z-Mod
    baseline. Once verification saves the current physical/global anchors, those
    extra terms become zero on the next print, so the new bias must absorb the
    correction that was actually active plus the operator's final live delta.
    """
    applied = float(applied_profile_correction)
    live = float(live_adjust)
    if not math.isfinite(applied) or not math.isfinite(live):
        raise CalibrationRejected("verification adjustments must be finite")
    return applied + live
