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
    *, verified_bias: float, auto_delta: float, mesh_test: int
) -> float:
    """Layer profile correction without double-applying Z-Mod AutoZOffset.

    Z-Mod MESH_TEST 3/4 already performs fresh-reference AutoZOffset during
    START_PRINT. In those modes Calibration Center adds only process bias.
    """
    bias = float(verified_bias)
    delta = float(auto_delta)
    if not math.isfinite(bias) or not math.isfinite(delta):
        raise CalibrationRejected("runtime corrections must be finite")
    return bias if int(mesh_test) in (3, 4) else bias + delta


def verified_process_bias(
    *,
    current_offset: float,
    base_runtime_offset: float,
    runtime_auto_delta: float,
) -> float:
    """Extract process bias from a verified first-layer runtime state."""
    current = float(current_offset)
    base = float(base_runtime_offset)
    auto = float(runtime_auto_delta)
    if not all(math.isfinite(value) for value in (current, base, auto)):
        raise CalibrationRejected("runtime offsets must be finite")
    return current - base - auto


def initial_verified_process_bias(*, live_adjust: float) -> float:
    """For a new profile, the deliberate first-layer live adjustment is bias.

    This avoids assuming that the machine's pre-existing/native base offset is
    zero when the profile has never had a prior verified anchor.
    """
    value = float(live_adjust)
    if not math.isfinite(value):
        raise CalibrationRejected("live adjustment must be finite")
    return value
