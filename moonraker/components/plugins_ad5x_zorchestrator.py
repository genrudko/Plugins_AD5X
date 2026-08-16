"""Fake-first orchestration for Z Calibration Subsystem v2.

This module deliberately contains no Moonraker/Klipper imports and no real
printer adapter.  It composes the already tested pure calibration model into a
complete run so failure/cancel semantics can be proven before any production
motion endpoint exists.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Mapping, Optional, Protocol

from . import plugins_ad5x_zcalibration as core


class OrchestrationAbort(core.CalibrationError):
    def __init__(self, reason: str) -> None:
        if not reason:
            raise core.PolicyError("orchestration abort reason is required")
        super().__init__(reason)
        self.reason = reason


class CalibrationRunAdapter(Protocol):
    def ensure_ready_for_calibration(self) -> None: ...
    def read_effective_offset(self) -> float: ...
    def set_effective_offset(self, value: float) -> None: ...
    def prepare_probe(self, envelope: core.SearchEnvelope) -> None: ...
    def tare_load_cell(self) -> float: ...
    def read_h7(self) -> core.H7Reading: ...
    def safe_approach(self, envelope: core.SearchEnvelope) -> None: ...
    def probe_once(self, envelope: core.SearchEnvelope) -> float: ...
    def safe_retract(self) -> None: ...
    def load_saved_mesh(self, profile: str) -> None: ...
    def build_runtime_mesh(self, runtime_id: str, *, reference: float) -> None: ...
    def clear_runtime_mesh(self) -> None: ...


@dataclass(frozen=True)
class CalibrationRunPolicies:
    search: core.SearchEnvelopePolicy
    probe: core.ProbeValidationPolicy
    reference: core.ReferenceDecisionPolicy
    tare: core.TarePolicy
    effective_offset_tolerance: float
    sample_count: int
    confirmation_sample_count: int

    def __post_init__(self) -> None:
        tolerance = core._finite(
            self.effective_offset_tolerance, "effective_offset_tolerance"
        )
        if tolerance < 0:
            raise core.PolicyError("effective_offset_tolerance cannot be negative")
        if self.sample_count < self.probe.min_samples:
            raise core.PolicyError("sample_count must satisfy probe.min_samples")
        if self.confirmation_sample_count < self.probe.min_samples:
            raise core.PolicyError(
                "confirmation_sample_count must satisfy probe.min_samples"
            )


@dataclass(frozen=True)
class CalibrationRunRequest:
    correlation_id: str
    mesh_mode: core.MeshMode
    mesh: core.MeshState
    policies: CalibrationRunPolicies
    offsets: core.OffsetComposition = core.OffsetComposition()
    trusted_reference: Optional[float] = None
    expected_reference: Optional[float] = None
    initial_acquisition: bool = False
    runtime_mesh_id: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.correlation_id:
            raise core.PolicyError("correlation_id is required")
        for name in (
            "auto_alignment",
            "slicer_job",
            "live_adjustment",
            "external_unknown",
        ):
            if getattr(self.offsets, name) != 0.0:
                raise core.PolicyError(
                    "calibration run requires a clean non-job baseline; "
                    f"{name} must be zero"
                )
        if self.trusted_reference is not None:
            core._finite(self.trusted_reference, "trusted_reference")
        if self.expected_reference is not None:
            core._finite(self.expected_reference, "expected_reference")
        if self.mesh_mode is core.MeshMode.RUNTIME and not self.runtime_mesh_id:
            raise core.PolicyError("runtime mesh mode requires runtime_mesh_id")

    @property
    def comparison_reference(self) -> Optional[float]:
        if self.expected_reference is not None:
            return self.expected_reference
        if self.mesh_mode is core.MeshMode.SAVED_CHECK:
            return self.mesh.saved_reference
        return None

    @property
    def search_reference(self) -> Optional[float]:
        if self.trusted_reference is not None:
            return self.trusted_reference
        return self.comparison_reference


@dataclass(frozen=True)
class CalibrationRunResult:
    model: core.CalibrationModel
    envelope: Optional[core.SearchEnvelope]
    primary_series: Optional[core.ProbeSeriesResult]
    confirmation_series: Optional[core.ProbeSeriesResult]
    reference_decision: Optional[core.ReferenceDecision]
    mesh_decision: Optional[core.MeshDecision]
    tare_residual: Optional[float]
    h7: Optional[core.H7Reading]
    effective_before: Optional[float]
    effective_after: Optional[float]
    cleanup: Mapping[str, bool]

    @property
    def success(self) -> bool:
        return self.model.state is core.CalibrationState.READY


class FakeCalibrationRunAdapter(core.FakeKlipperMoonrakerAdapter):
    """Deterministic fake with the extra orchestration primitives.

    No method performs real motion, persistence, or config writes.  Scripts may
    contain exceptions to inject failures at exact boundaries.
    """

    def __init__(
        self,
        *,
        tare_script: Iterable[Any] = (),
        prepare_script: Iterable[Any] = (),
        approach_script: Iterable[Any] = (),
        retract_script: Iterable[Any] = (),
        ignore_offset_writes: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.tare_script = deque(tare_script)
        self.prepare_script = deque(prepare_script)
        self.approach_script = deque(approach_script)
        self.retract_script = deque(retract_script)
        self.ignore_offset_writes = bool(ignore_offset_writes)

    @staticmethod
    def _next_script(script: deque[Any], default: Any) -> Any:
        if not script:
            return default
        item = script.popleft()
        if isinstance(item, BaseException):
            raise item
        return item

    def prepare_probe(self, envelope: core.SearchEnvelope) -> None:
        self.ensure_ready_for_calibration()
        self.calls.append(("prepare_probe", (envelope.upper_z, envelope.lower_z)))
        self._next_script(self.prepare_script, None)

    def tare_load_cell(self) -> float:
        self.ensure_ready_for_calibration()
        value = self._next_script(self.tare_script, 0.0)
        residual = core._finite(value, "tare_residual")
        self.calls.append(("tare_load_cell", residual))
        return residual

    def safe_approach(self, envelope: core.SearchEnvelope) -> None:
        self.ensure_ready_for_calibration()
        self.calls.append(("safe_approach", (envelope.upper_z, envelope.lower_z)))
        self._next_script(self.approach_script, None)

    def safe_retract(self) -> None:
        self.calls.append(("safe_retract", None))
        self._next_script(self.retract_script, None)

    def clear_runtime_mesh(self) -> None:
        self.runtime_mesh = None
        self.active_mesh = None
        self.calls.append(("clear_runtime_mesh", None))

    def set_effective_offset(self, value: float) -> None:
        if self.ignore_offset_writes:
            value = core._finite(value, "effective_offset")
            self.calls.append(("set_effective_offset_ignored", value))
            return
        super().set_effective_offset(value)


class ZCalibrationOrchestrator:
    def __init__(
        self,
        adapter: CalibrationRunAdapter,
        diagnostics: core.DiagnosticStore,
        *,
        cancelled: Optional[Callable[[core.CalibrationState], bool]] = None,
    ) -> None:
        self.adapter = adapter
        self.diagnostics = diagnostics
        self.cancelled = cancelled

    def run(self, request: CalibrationRunRequest) -> CalibrationRunResult:
        model = core.CalibrationModel(
            offsets=request.offsets,
            saved_mesh_id=request.mesh.saved_profile,
        )
        envelope: Optional[core.SearchEnvelope] = None
        primary: Optional[core.ProbeSeriesResult] = None
        confirmation: Optional[core.ProbeSeriesResult] = None
        reference: Optional[core.ReferenceDecision] = None
        mesh_decision: Optional[core.MeshDecision] = None
        tare_residual: Optional[float] = None
        h7: Optional[core.H7Reading] = None
        effective_before: Optional[float] = None
        effective_after: Optional[float] = None
        motion_started = False
        offset_written = False
        runtime_mesh_built = False
        cleanup = {
            "offset_reconciled": True,
            "mesh_reconciled": True,
            "retracted": True,
        }

        self.diagnostics.emit(
            "calibration_start",
            correlation_id=request.correlation_id,
            payload={
                "mesh_mode": request.mesh_mode.value,
                "initial_acquisition": request.initial_acquisition,
            },
        )

        try:
            model = self._advance(model, core.CalibrationState.PRECHECK)
            self.adapter.ensure_ready_for_calibration()
            effective_before = self.adapter.read_effective_offset()
            reconciled = request.offsets.reconcile_actual(
                effective_before,
                tolerance=request.policies.effective_offset_tolerance,
            )
            if abs(reconciled.external_unknown) > request.policies.effective_offset_tolerance:
                raise OrchestrationAbort("external_unknown_offset")

            envelope = request.policies.search.build(
                request.search_reference,
                initial_acquisition=request.initial_acquisition,
            )

            model = self._advance(model, core.CalibrationState.PREPARE_PROBE)
            self.adapter.prepare_probe(envelope)

            model = self._advance(model, core.CalibrationState.TARE)
            tare_residual = self.adapter.tare_load_cell()
            if not request.policies.tare.accepts(tare_residual):
                raise OrchestrationAbort("tare_residual_out_of_range")
            h7 = self.adapter.read_h7()
            self.diagnostics.emit(
                "tare",
                correlation_id=request.correlation_id,
                payload={
                    "residual": tare_residual,
                    "h7_status": h7.status.value,
                },
            )
            if h7.status is core.H7Status.CONTRADICTORY:
                # Secondary evidence may make us more conservative, never less.
                raise OrchestrationAbort("h7_contradictory")

            model = self._advance(model, core.CalibrationState.SAFE_APPROACH)
            motion_started = True
            self.adapter.safe_approach(envelope)

            model = self._advance(model, core.CalibrationState.SLOW_CONTACT_SEARCH)
            samples = self._probe_series(request.policies.sample_count, envelope)

            model = self._advance(model, core.CalibrationState.VERIFY_CONTACT)
            primary = core.validate_probe_series(samples, request.policies.probe)
            self._emit_series(request.correlation_id, "primary", primary)
            if not primary.accepted:
                raise OrchestrationAbort(f"probe_series_{primary.status.value}")

            model = self._advance(model, core.CalibrationState.REPEATABILITY_CHECK)
            comparison_reference = request.comparison_reference
            if comparison_reference is not None:
                provisional = core.decide_reference_alignment(
                    primary,
                    mesh_reference=comparison_reference,
                    policy=request.policies.reference,
                )
                if provisional.kind is core.ReferenceDecisionKind.RECONFIRM_REQUIRED:
                    confirmation_samples = self._probe_series(
                        request.policies.confirmation_sample_count,
                        envelope,
                    )
                    confirmation = core.validate_probe_series(
                        confirmation_samples,
                        request.policies.probe,
                    )
                    self._emit_series(
                        request.correlation_id, "confirmation", confirmation
                    )

            model = self._advance(model, core.CalibrationState.REFERENCE_DECISION)
            if comparison_reference is not None:
                reference = core.decide_reference_alignment(
                    primary,
                    mesh_reference=comparison_reference,
                    policy=request.policies.reference,
                    confirmation_series=confirmation,
                )
                self.diagnostics.emit(
                    "reference_decision",
                    correlation_id=request.correlation_id,
                    payload={
                        "decision": reference.kind.value,
                        "reason": reference.reason,
                        "current_reference": reference.current_reference,
                        "expected_reference": comparison_reference,
                        "alignment_delta": reference.alignment_delta,
                    },
                )
                if reference.kind is core.ReferenceDecisionKind.HARDWARE_CHANGE_SUSPECTED:
                    model = model.transition(
                        core.CalibrationState.HARDWARE_CHANGE_SUSPECTED
                    )
                    raise OrchestrationAbort("confirmed_large_delta")
                if reference.kind is core.ReferenceDecisionKind.REJECT:
                    raise OrchestrationAbort(reference.reason)
                if reference.kind is core.ReferenceDecisionKind.RECONFIRM_REQUIRED:
                    raise OrchestrationAbort("large_delta_confirmation_missing")

            model = self._advance(model, core.CalibrationState.MESH_DECISION)
            mesh_decision = core.decide_mesh_mode(
                request.mesh_mode,
                request.mesh,
                reference,
            )
            self.diagnostics.emit(
                "mesh_decision",
                correlation_id=request.correlation_id,
                payload={
                    "mode": request.mesh_mode.value,
                    "accepted": mesh_decision.accepted,
                    "action": (
                        mesh_decision.action.value
                        if mesh_decision.action is not None
                        else None
                    ),
                    "reason": mesh_decision.reason,
                    "auto_alignment": mesh_decision.auto_alignment,
                },
            )
            if not mesh_decision.accepted or mesh_decision.action is None:
                raise OrchestrationAbort(mesh_decision.reason)

            if mesh_decision.action in {
                core.MeshAction.USE_SAVED,
                core.MeshAction.USE_SAVED_WITH_ALIGNMENT,
            }:
                if request.mesh.saved_profile is None:
                    raise OrchestrationAbort("saved_mesh_missing")
                self.adapter.load_saved_mesh(request.mesh.saved_profile)
            elif mesh_decision.action is core.MeshAction.BUILD_RUNTIME:
                if request.runtime_mesh_id is None or primary.median is None:
                    raise OrchestrationAbort("runtime_mesh_context_missing")
                self.adapter.build_runtime_mesh(
                    request.runtime_mesh_id,
                    reference=primary.median,
                )
                runtime_mesh_built = True
                model = replace(model, runtime_mesh_id=request.runtime_mesh_id)

            model = self._advance(model, core.CalibrationState.OFFSET_COMPOSITION)
            composed = request.offsets.replace_auto(mesh_decision.auto_alignment)
            target = composed.effective
            if effective_before is None:
                raise OrchestrationAbort("effective_baseline_missing")
            if (
                abs(target - effective_before)
                > request.policies.effective_offset_tolerance
            ):
                self.adapter.set_effective_offset(target)
                offset_written = True
            effective_after = self.adapter.read_effective_offset()
            if (
                abs(effective_after - target)
                > request.policies.effective_offset_tolerance
            ):
                raise OrchestrationAbort("offset_verification_failed")
            model = replace(model, offsets=composed)
            self.diagnostics.emit(
                "offset_composed",
                correlation_id=request.correlation_id,
                payload={
                    "persistent_user": composed.persistent_user,
                    "auto_alignment": composed.auto_alignment,
                    "effective": effective_after,
                },
            )

            model = self._advance(model, core.CalibrationState.READY)
            self.diagnostics.emit(
                "calibration_ready",
                correlation_id=request.correlation_id,
                payload={
                    "effective": effective_after,
                    "mesh_mode": request.mesh_mode.value,
                },
            )
            return CalibrationRunResult(
                model,
                envelope,
                primary,
                confirmation,
                reference,
                mesh_decision,
                tare_residual,
                h7,
                effective_before,
                effective_after,
                cleanup,
            )
        except (OrchestrationAbort, core.CalibrationError, ValueError) as exc:
            reason = self._reason(exc)
            cleanup = self._cleanup(
                request,
                effective_before=effective_before,
                motion_started=motion_started,
                offset_written=offset_written,
                runtime_mesh_built=runtime_mesh_built,
            )
            model = model.abort(
                reason,
                motion_state_allows_retract=motion_started,
            )
            try:
                effective_after = self.adapter.read_effective_offset()
            except core.CalibrationError:
                effective_after = None
            self.diagnostics.emit(
                "calibration_abort",
                correlation_id=request.correlation_id,
                payload={
                    "reason": reason,
                    "state": model.state.value,
                    "offset_reconciled": cleanup["offset_reconciled"],
                    "mesh_reconciled": cleanup["mesh_reconciled"],
                    "retracted": cleanup["retracted"],
                },
            )
            return CalibrationRunResult(
                model,
                envelope,
                primary,
                confirmation,
                reference,
                mesh_decision,
                tare_residual,
                h7,
                effective_before,
                effective_after,
                cleanup,
            )

    def _advance(
        self,
        model: core.CalibrationModel,
        target: core.CalibrationState,
    ) -> core.CalibrationModel:
        model = model.transition(target)
        if self.cancelled is not None and self.cancelled(target):
            raise OrchestrationAbort("cancelled")
        return model

    def _probe_series(
        self,
        count: int,
        envelope: core.SearchEnvelope,
    ) -> tuple[float, ...]:
        values = []
        for _ in range(count):
            values.append(self.adapter.probe_once(envelope))
        return tuple(values)

    def _emit_series(
        self,
        correlation_id: str,
        role: str,
        result: core.ProbeSeriesResult,
    ) -> None:
        self.diagnostics.emit(
            "probe_series",
            correlation_id=correlation_id,
            payload={
                "role": role,
                "status": result.status.value,
                "samples": list(result.samples),
                "median": result.median,
                "spread": result.spread,
                "drift": result.drift,
            },
        )

    def _cleanup(
        self,
        request: CalibrationRunRequest,
        *,
        effective_before: Optional[float],
        motion_started: bool,
        offset_written: bool,
        runtime_mesh_built: bool,
    ) -> Mapping[str, bool]:
        offset_ok = True
        mesh_ok = True
        retract_ok = True

        if offset_written and effective_before is not None:
            try:
                self.adapter.set_effective_offset(effective_before)
                actual = self.adapter.read_effective_offset()
                offset_ok = (
                    abs(actual - effective_before)
                    <= request.policies.effective_offset_tolerance
                )
            except core.CalibrationError:
                offset_ok = False

        if runtime_mesh_built:
            try:
                if request.mesh.saved_profile is not None:
                    self.adapter.load_saved_mesh(request.mesh.saved_profile)
                else:
                    self.adapter.clear_runtime_mesh()
            except core.CalibrationError:
                mesh_ok = False

        if motion_started:
            try:
                self.adapter.safe_retract()
            except core.CalibrationError:
                retract_ok = False

        return {
            "offset_reconciled": offset_ok,
            "mesh_reconciled": mesh_ok,
            "retracted": retract_ok,
        }

    @staticmethod
    def _reason(exc: BaseException) -> str:
        if isinstance(exc, OrchestrationAbort):
            return exc.reason
        mapping = (
            (core.AdapterCancelled, "cancelled"),
            (core.EarlyTrigger, "early_trigger"),
            (core.NoTrigger, "no_trigger"),
            (core.LowerBoundViolation, "lower_bound_violation"),
            (core.CommunicationFailure, "communication_failure"),
            (core.AdapterNotReady, "adapter_not_ready"),
            (core.PolicyError, "policy_error"),
            (core.AdapterError, "adapter_error"),
        )
        for error_type, reason in mapping:
            if isinstance(exc, error_type):
                return reason
        return "invalid_runtime_value"
