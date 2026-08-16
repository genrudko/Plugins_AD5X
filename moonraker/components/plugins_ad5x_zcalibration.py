"""Pure Z Calibration Subsystem v2 model and deterministic fake adapter.

Milestone A deliberately has no Moonraker/Klipper imports and performs no real
I/O or motion. Numeric safety thresholds are supplied by policy/configuration;
this module does not freeze hardware thresholds before real-printer evidence.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import math
import statistics
from typing import Any, Deque, Iterable, Mapping, Optional, Protocol, Sequence

SCHEMA_VERSION = "1.0"


class CalibrationError(RuntimeError): pass
class InvalidTransition(CalibrationError): pass
class PolicyError(CalibrationError): pass
class AdapterError(CalibrationError): pass
class AdapterNotReady(AdapterError): pass
class AdapterCancelled(AdapterError): pass
class EarlyTrigger(AdapterError): pass
class NoTrigger(AdapterError): pass
class LowerBoundViolation(AdapterError): pass
class CommunicationFailure(AdapterError): pass


class CalibrationState(str, Enum):
    IDLE = "idle"
    PRECHECK = "precheck"
    PREPARE_PROBE = "prepare_probe"
    TARE = "tare"
    SAFE_APPROACH = "safe_approach"
    SLOW_CONTACT_SEARCH = "slow_contact_search"
    VERIFY_CONTACT = "verify_contact"
    REPEATABILITY_CHECK = "repeatability_check"
    REFERENCE_DECISION = "reference_decision"
    MESH_DECISION = "mesh_decision"
    OFFSET_COMPOSITION = "offset_composition"
    READY = "ready"
    HARDWARE_CHANGE_SUSPECTED = "hardware_change_suspected"
    ABORT = "abort"


class MeshMode(str, Enum):
    SAVED = "saved"
    SAVED_CHECK = "saved+check"
    RUNTIME = "runtime"


class MeshAction(str, Enum):
    USE_SAVED = "use_saved"
    USE_SAVED_WITH_ALIGNMENT = "use_saved_with_alignment"
    BUILD_RUNTIME = "build_runtime"


class SearchMode(str, Enum):
    TRUSTED_REFERENCE = "trusted_reference"
    INITIAL_ACQUISITION = "initial_acquisition"


class SeriesStatus(str, Enum):
    ACCEPTED = "accepted"
    TOO_FEW_SAMPLES = "too_few_samples"
    NON_FINITE = "non_finite"
    OUT_OF_PLAUSIBLE_RANGE = "out_of_plausible_range"
    HIGH_SPREAD = "high_spread"
    DRIFT = "drift"


class ReferenceDecisionKind(str, Enum):
    ALIGN = "align"
    RECONFIRM_REQUIRED = "reconfirm_required"
    HARDWARE_CHANGE_SUSPECTED = "hardware_change_suspected"
    REJECT = "reject"


class H7Status(str, Enum):
    AVAILABLE = "available"
    DELAYED = "delayed"
    MISSING = "missing"
    CONTRADICTORY = "contradictory"


def _finite(value: float, name: str) -> float:
    value = float(value)
    if not math.isfinite(value):
        raise PolicyError(f"{name} must be finite")
    return value


@dataclass(frozen=True)
class OffsetComposition:
    """Auditable composition of the effective standard Klipper Z offset."""
    auto_alignment: float = 0.0
    persistent_user: float = 0.0
    slicer_job: float = 0.0
    live_adjustment: float = 0.0
    external_unknown: float = 0.0

    def __post_init__(self) -> None:
        for name in ("auto_alignment", "persistent_user", "slicer_job", "live_adjustment", "external_unknown"):
            _finite(getattr(self, name), name)

    @property
    def known_total(self) -> float:
        return self.auto_alignment + self.persistent_user + self.slicer_job + self.live_adjustment

    @property
    def effective(self) -> float:
        return self.known_total + self.external_unknown

    def replace_auto(self, value: float) -> "OffsetComposition":
        return replace(self, auto_alignment=_finite(value, "auto_alignment"))

    def start_job(self, value: float = 0.0) -> "OffsetComposition":
        return replace(self, slicer_job=_finite(value, "slicer_job"), live_adjustment=0.0, external_unknown=0.0)

    def step_live(self, delta: float) -> "OffsetComposition":
        return replace(self, live_adjustment=self.live_adjustment + _finite(delta, "live_delta"))

    def save_live_to_persistent(self) -> "OffsetComposition":
        return replace(self, persistent_user=self.persistent_user + self.live_adjustment, live_adjustment=0.0)

    def end_job(self) -> "OffsetComposition":
        return replace(self, slicer_job=0.0, live_adjustment=0.0, external_unknown=0.0)

    def clear_transient(self) -> "OffsetComposition":
        return OffsetComposition(persistent_user=self.persistent_user)

    def reconcile_actual(self, actual_effective: float, *, tolerance: float) -> "OffsetComposition":
        actual = _finite(actual_effective, "actual_effective")
        tolerance = _finite(tolerance, "tolerance")
        if tolerance < 0:
            raise PolicyError("tolerance must be non-negative")
        mismatch = actual - self.known_total
        if abs(mismatch) <= tolerance:
            mismatch = 0.0
        return replace(self, external_unknown=mismatch)


@dataclass(frozen=True)
class SearchEnvelope:
    lower_z: float
    upper_z: float
    mode: SearchMode
    basis_reference: Optional[float] = None

    def __post_init__(self) -> None:
        if _finite(self.lower_z, "lower_z") >= _finite(self.upper_z, "upper_z"):
            raise PolicyError("search envelope must have lower_z < upper_z")
        if self.basis_reference is not None:
            _finite(self.basis_reference, "basis_reference")

    def classify_trigger(self, z: float) -> str:
        z = _finite(z, "trigger_z")
        if z > self.upper_z:
            return "early"
        if z < self.lower_z:
            return "below_lower_bound"
        return "inside"


@dataclass(frozen=True)
class SearchEnvelopePolicy:
    machine_min_z: float
    machine_max_z: float
    trusted_above_margin: float
    trusted_below_margin: float
    initial_lower_z: Optional[float] = None
    initial_upper_z: Optional[float] = None

    def __post_init__(self) -> None:
        mn, mx = _finite(self.machine_min_z, "machine_min_z"), _finite(self.machine_max_z, "machine_max_z")
        above, below = _finite(self.trusted_above_margin, "trusted_above_margin"), _finite(self.trusted_below_margin, "trusted_below_margin")
        if mn >= mx:
            raise PolicyError("machine_min_z must be below machine_max_z")
        if above <= 0 or below <= 0:
            raise PolicyError("trusted search margins must be positive")
        if self.initial_lower_z is not None: _finite(self.initial_lower_z, "initial_lower_z")
        if self.initial_upper_z is not None: _finite(self.initial_upper_z, "initial_upper_z")

    def build(self, previous_reference: Optional[float], *, initial_acquisition: bool = False) -> SearchEnvelope:
        if previous_reference is not None:
            ref = _finite(previous_reference, "previous_reference")
            lower, upper = ref - self.trusted_below_margin, ref + self.trusted_above_margin
            # Fail closed instead of clamping a missing-contact search to machine position_min.
            if lower <= self.machine_min_z or upper >= self.machine_max_z:
                raise PolicyError("trusted envelope crosses machine boundary")
            return SearchEnvelope(lower, upper, SearchMode.TRUSTED_REFERENCE, ref)
        if not initial_acquisition:
            raise PolicyError("missing trustworthy reference requires explicit initial acquisition")
        if self.initial_lower_z is None or self.initial_upper_z is None:
            raise PolicyError("initial acquisition requires explicit bounded limits")
        lower, upper = self.initial_lower_z, self.initial_upper_z
        if not (self.machine_min_z < lower < upper < self.machine_max_z):
            raise PolicyError("initial acquisition limits must be strictly inside machine bounds")
        return SearchEnvelope(lower, upper, SearchMode.INITIAL_ACQUISITION)


@dataclass(frozen=True)
class ProbeValidationPolicy:
    min_samples: int
    max_spread: float
    max_abs_drift: float
    plausible_min_z: float
    plausible_max_z: float

    def __post_init__(self) -> None:
        if self.min_samples < 2:
            raise PolicyError("min_samples must be at least 2")
        if _finite(self.max_spread, "max_spread") <= 0 or _finite(self.max_abs_drift, "max_abs_drift") <= 0:
            raise PolicyError("spread/drift gates must be positive")
        if _finite(self.plausible_min_z, "plausible_min_z") >= _finite(self.plausible_max_z, "plausible_max_z"):
            raise PolicyError("plausible_min_z must be below plausible_max_z")


@dataclass(frozen=True)
class ProbeSeriesResult:
    status: SeriesStatus
    samples: tuple[float, ...]
    count: int
    mean: Optional[float]
    median: Optional[float]
    spread: Optional[float]
    drift: Optional[float]

    @property
    def accepted(self) -> bool:
        return self.status is SeriesStatus.ACCEPTED


def validate_probe_series(samples: Sequence[float], policy: ProbeValidationPolicy) -> ProbeSeriesResult:
    raw = tuple(float(v) for v in samples)
    if len(raw) < policy.min_samples:
        return ProbeSeriesResult(SeriesStatus.TOO_FEW_SAMPLES, raw, len(raw), None, None, None, None)
    if not all(math.isfinite(v) for v in raw):
        return ProbeSeriesResult(SeriesStatus.NON_FINITE, raw, len(raw), None, None, None, None)
    mean, median = statistics.fmean(raw), statistics.median(raw)
    spread, drift = max(raw) - min(raw), raw[-1] - raw[0]
    if any(v < policy.plausible_min_z or v > policy.plausible_max_z for v in raw): status = SeriesStatus.OUT_OF_PLAUSIBLE_RANGE
    elif spread > policy.max_spread: status = SeriesStatus.HIGH_SPREAD
    elif abs(drift) > policy.max_abs_drift: status = SeriesStatus.DRIFT
    else: status = SeriesStatus.ACCEPTED
    return ProbeSeriesResult(status, raw, len(raw), mean, median, spread, drift)


@dataclass(frozen=True)
class ReferenceDecisionPolicy:
    max_auto_alignment_delta: float
    confirmation_max_difference: float

    def __post_init__(self) -> None:
        if _finite(self.max_auto_alignment_delta, "max_auto_alignment_delta") <= 0:
            raise PolicyError("max_auto_alignment_delta must be positive")
        if _finite(self.confirmation_max_difference, "confirmation_max_difference") <= 0:
            raise PolicyError("confirmation_max_difference must be positive")


@dataclass(frozen=True)
class ReferenceDecision:
    kind: ReferenceDecisionKind
    current_reference: Optional[float]
    mesh_reference: Optional[float]
    alignment_delta: Optional[float]
    reason: str


def decide_reference_alignment(series: ProbeSeriesResult, *, mesh_reference: float, policy: ReferenceDecisionPolicy, confirmation_series: Optional[ProbeSeriesResult] = None) -> ReferenceDecision:
    mesh_ref = _finite(mesh_reference, "mesh_reference")
    if not series.accepted or series.median is None:
        return ReferenceDecision(ReferenceDecisionKind.REJECT, series.median, mesh_ref, None, f"probe_series_{series.status.value}")
    current = series.median
    # Current Z-Mod MESH_TEST sign semantics: current probe reference - saved mesh reference.
    delta = current - mesh_ref
    if abs(delta) < policy.max_auto_alignment_delta:
        return ReferenceDecision(ReferenceDecisionKind.ALIGN, current, mesh_ref, delta, "within_alignment_gate")
    if confirmation_series is None:
        return ReferenceDecision(ReferenceDecisionKind.RECONFIRM_REQUIRED, current, mesh_ref, delta, "large_delta_requires_independent_confirmation")
    if not confirmation_series.accepted or confirmation_series.median is None:
        return ReferenceDecision(ReferenceDecisionKind.REJECT, current, mesh_ref, None, f"confirmation_series_{confirmation_series.status.value}")
    confirmation_delta = confirmation_series.median - mesh_ref
    if abs(confirmation_delta) < policy.max_auto_alignment_delta:
        return ReferenceDecision(ReferenceDecisionKind.REJECT, current, mesh_ref, None, "large_delta_not_reproduced")
    if abs(confirmation_delta - delta) > policy.confirmation_max_difference:
        return ReferenceDecision(ReferenceDecisionKind.REJECT, current, mesh_ref, None, "large_delta_confirmation_inconsistent")
    return ReferenceDecision(ReferenceDecisionKind.HARDWARE_CHANGE_SUSPECTED, current, mesh_ref, delta, "confirmed_large_delta")


@dataclass(frozen=True)
class MeshState:
    saved_profile: Optional[str] = None
    saved_reference: Optional[float] = None
    runtime_mesh_id: Optional[str] = None

    def __post_init__(self) -> None:
        if (self.saved_profile is None) != (self.saved_reference is None):
            raise PolicyError("saved profile and saved reference must exist together")
        if self.saved_reference is not None: _finite(self.saved_reference, "saved_reference")


@dataclass(frozen=True)
class MeshDecision:
    mode: MeshMode
    action: Optional[MeshAction]
    accepted: bool
    auto_alignment: float
    reason: str


def decide_mesh_mode(mode: MeshMode, mesh: MeshState, reference_decision: Optional[ReferenceDecision] = None) -> MeshDecision:
    if mode is MeshMode.SAVED:
        if mesh.saved_profile is None: return MeshDecision(mode, None, False, 0.0, "saved_mesh_missing")
        return MeshDecision(mode, MeshAction.USE_SAVED, True, 0.0, "saved_mesh_selected")
    if mode is MeshMode.SAVED_CHECK:
        if mesh.saved_profile is None: return MeshDecision(mode, None, False, 0.0, "saved_mesh_missing")
        if reference_decision is None or reference_decision.kind is not ReferenceDecisionKind.ALIGN:
            kind = "missing" if reference_decision is None else reference_decision.kind.value
            return MeshDecision(mode, None, False, 0.0, f"reference_{kind}")
        return MeshDecision(mode, MeshAction.USE_SAVED_WITH_ALIGNMENT, True, reference_decision.alignment_delta or 0.0, "saved_mesh_reference_aligned")
    if mode is MeshMode.RUNTIME:
        return MeshDecision(mode, MeshAction.BUILD_RUNTIME, True, 0.0, "runtime_mesh_requested")
    raise PolicyError(f"unsupported mesh mode: {mode!r}")


_ALLOWED_TRANSITIONS = {
    CalibrationState.IDLE: {CalibrationState.PRECHECK},
    CalibrationState.PRECHECK: {CalibrationState.PREPARE_PROBE},
    CalibrationState.PREPARE_PROBE: {CalibrationState.TARE},
    CalibrationState.TARE: {CalibrationState.SAFE_APPROACH},
    CalibrationState.SAFE_APPROACH: {CalibrationState.SLOW_CONTACT_SEARCH},
    CalibrationState.SLOW_CONTACT_SEARCH: {CalibrationState.VERIFY_CONTACT},
    CalibrationState.VERIFY_CONTACT: {CalibrationState.REPEATABILITY_CHECK},
    CalibrationState.REPEATABILITY_CHECK: {CalibrationState.REFERENCE_DECISION},
    CalibrationState.REFERENCE_DECISION: {CalibrationState.MESH_DECISION, CalibrationState.HARDWARE_CHANGE_SUSPECTED},
    CalibrationState.MESH_DECISION: {CalibrationState.OFFSET_COMPOSITION},
    CalibrationState.OFFSET_COMPOSITION: {CalibrationState.READY},
    CalibrationState.READY: {CalibrationState.IDLE},
    CalibrationState.HARDWARE_CHANGE_SUSPECTED: set(),
    CalibrationState.ABORT: set(),
}


@dataclass(frozen=True)
class CalibrationModel:
    state: CalibrationState = CalibrationState.IDLE
    offsets: OffsetComposition = field(default_factory=OffsetComposition)
    saved_mesh_id: Optional[str] = None
    runtime_mesh_id: Optional[str] = None
    last_abort_reason: Optional[str] = None
    retract_required: bool = False

    def transition(self, target: CalibrationState) -> "CalibrationModel":
        if target not in _ALLOWED_TRANSITIONS[self.state]:
            raise InvalidTransition(f"illegal transition {self.state.value} -> {target.value}")
        return replace(self, state=target)

    def abort(self, reason: str, *, motion_state_allows_retract: bool) -> "CalibrationModel":
        if not reason: raise PolicyError("abort reason is required")
        return CalibrationModel(CalibrationState.ABORT, self.offsets.clear_transient(), self.saved_mesh_id, None, reason, bool(motion_state_allows_retract))

    def cancel(self, *, motion_state_allows_retract: bool) -> "CalibrationModel":
        return self.abort("cancelled", motion_state_allows_retract=motion_state_allows_retract)

    def reset_after_abort(self) -> "CalibrationModel":
        if self.state is not CalibrationState.ABORT:
            raise InvalidTransition("fresh safe reset is only valid from ABORT")
        return replace(self, state=CalibrationState.IDLE, last_abort_reason=None, retract_required=False)


_SECRET_KEYS = {"password", "passwd", "token", "api_key", "apikey", "secret"}

def _payload_contains_secret(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(str(k).lower() in _SECRET_KEYS or _payload_contains_secret(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return any(_payload_contains_secret(v) for v in value)
    return False


@dataclass(frozen=True)
class DiagnosticEvent:
    schema_version: str
    sequence: int
    timestamp: str
    correlation_id: str
    event_type: str
    payload: Mapping[str, Any]


class DiagnosticStore(Protocol):
    def emit(self, event_type: str, *, correlation_id: str, payload: Mapping[str, Any], timestamp: Optional[str] = None) -> DiagnosticEvent: ...
    def recent(self) -> tuple[DiagnosticEvent, ...]: ...


class BoundedDiagnosticLog:
    def __init__(self, capacity: int) -> None:
        if capacity <= 0: raise PolicyError("diagnostic capacity must be positive")
        self._events: Deque[DiagnosticEvent] = deque(maxlen=capacity)
        self._sequence = 0

    def emit(self, event_type: str, *, correlation_id: str, payload: Mapping[str, Any], timestamp: Optional[str] = None) -> DiagnosticEvent:
        if not event_type or not correlation_id: raise PolicyError("event_type and correlation_id are required")
        if _payload_contains_secret(payload): raise PolicyError("diagnostic payload contains a secret-like key")
        self._sequence += 1
        timestamp = timestamp or datetime.now(timezone.utc).isoformat()
        event = DiagnosticEvent(SCHEMA_VERSION, self._sequence, timestamp, correlation_id, event_type, dict(payload))
        self._events.append(event)
        return event

    def recent(self) -> tuple[DiagnosticEvent, ...]:
        return tuple(self._events)

    def ingest_untrusted_record(self, record: Mapping[str, Any]) -> bool:
        try:
            if record.get("schema_version") != SCHEMA_VERSION or not isinstance(record["payload"], Mapping): return False
            self.emit(str(record["event_type"]), correlation_id=str(record["correlation_id"]), payload=record["payload"], timestamp=str(record["timestamp"]))
            return True
        except (KeyError, TypeError, ValueError, PolicyError):
            return False


@dataclass(frozen=True)
class TarePolicy:
    max_abs_residual: float
    def __post_init__(self) -> None:
        if _finite(self.max_abs_residual, "max_abs_residual") < 0: raise PolicyError("max_abs_residual cannot be negative")
    def accepts(self, residual: float) -> bool:
        return abs(_finite(residual, "tare_residual")) <= self.max_abs_residual


@dataclass(frozen=True)
class H7Reading:
    status: H7Status
    value: Optional[float] = None
    signed: bool = True
    def __post_init__(self) -> None:
        if self.value is not None: _finite(self.value, "h7_value")


class FakeKlipperMoonrakerAdapter:
    """Deterministic Layer-B fake: no real motion, config writes, or persistence."""
    def __init__(self, *, klippy_ready: bool = True, homed: bool = True, print_state: str = "standby", effective_offset: float = 0.0, probe_script: Iterable[Any] = (), h7_script: Iterable[Any] = (), saved_meshes: Optional[Mapping[str, float]] = None) -> None:
        self.klippy_ready, self.homed, self.print_state = bool(klippy_ready), bool(homed), print_state
        self.effective_offset = _finite(effective_offset, "effective_offset")
        self.probe_script, self.h7_script = deque(probe_script), deque(h7_script)
        self.saved_meshes = dict(saved_meshes or {})
        self.active_mesh: Optional[str] = None
        self.runtime_mesh: Optional[str] = None
        self.cancelled = False
        self.calls: list[tuple[str, Any]] = []

    def ensure_ready_for_calibration(self) -> None:
        self.calls.append(("ensure_ready", None))
        if not self.klippy_ready: raise AdapterNotReady("Klippy is unavailable/not ready")
        if not self.homed: raise AdapterNotReady("printer is not homed")
        if self.print_state in {"printing", "paused"}: raise AdapterNotReady(f"calibration forbidden while {self.print_state}")
        if self.cancelled: raise AdapterCancelled("operation cancelled")

    def read_effective_offset(self) -> float:
        if not self.klippy_ready: raise CommunicationFailure("Klippy disconnected")
        self.calls.append(("read_effective_offset", self.effective_offset)); return self.effective_offset

    def set_effective_offset(self, value: float) -> None:
        if not self.klippy_ready: raise CommunicationFailure("Klippy disconnected")
        if self.cancelled: raise AdapterCancelled("operation cancelled")
        self.effective_offset = _finite(value, "effective_offset"); self.calls.append(("set_effective_offset", self.effective_offset))

    def external_set_effective_offset(self, value: float) -> None:
        self.effective_offset = _finite(value, "external_effective_offset"); self.calls.append(("external_set_effective_offset", self.effective_offset))

    def probe_once(self, envelope: SearchEnvelope) -> float:
        self.ensure_ready_for_calibration(); self.calls.append(("probe_begin", (envelope.upper_z, envelope.lower_z)))
        if not self.probe_script:
            self.calls.append(("probe_stop_at_lower_bound", envelope.lower_z)); raise NoTrigger("no trigger before lower safe bound")
        item = self.probe_script.popleft()
        if isinstance(item, BaseException): raise item
        if item is None:
            self.calls.append(("probe_stop_at_lower_bound", envelope.lower_z)); raise NoTrigger("no trigger before lower safe bound")
        z = _finite(item, "probe_trigger_z")
        classification = envelope.classify_trigger(z)
        if classification == "early": self.calls.append(("probe_early_trigger", z)); raise EarlyTrigger("probe triggered above allowed contact window")
        if classification == "below_lower_bound": self.calls.append(("probe_lower_bound_violation", z)); raise LowerBoundViolation("trigger below lower safe bound")
        self.calls.append(("probe_trigger", z)); return z

    def read_h7(self) -> H7Reading:
        self.calls.append(("read_h7", None))
        if not self.h7_script: return H7Reading(H7Status.MISSING)
        item = self.h7_script.popleft()
        if isinstance(item, BaseException): raise item
        return H7Reading(H7Status.MISSING) if item is None else item

    def load_saved_mesh(self, profile: str) -> None:
        if profile not in self.saved_meshes: raise AdapterError(f"saved mesh {profile!r} does not exist")
        self.active_mesh = profile; self.calls.append(("load_saved_mesh", profile))

    def build_runtime_mesh(self, runtime_id: str, *, reference: float) -> None:
        if not runtime_id: raise PolicyError("runtime mesh id is required")
        ref = _finite(reference, "runtime_mesh_reference")
        self.runtime_mesh = self.active_mesh = runtime_id; self.calls.append(("build_runtime_mesh", (runtime_id, ref)))
        # Deliberately do not mutate saved_meshes.

    def explicit_save_runtime_mesh(self, *, reference: float) -> None:
        if self.runtime_mesh is None: raise AdapterError("no runtime mesh to save")
        ref = _finite(reference, "runtime_mesh_reference")
        self.saved_meshes[self.runtime_mesh] = ref; self.calls.append(("save_runtime_mesh", (self.runtime_mesh, ref)))

    def request_cancel(self) -> None:
        self.cancelled = True; self.calls.append(("cancel", None))
    def disconnect(self) -> None:
        self.klippy_ready = False; self.calls.append(("disconnect", None))
    def reconnect(self) -> None:
        self.klippy_ready = True; self.calls.append(("reconnect", None))
