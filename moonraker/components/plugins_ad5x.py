# Plugins AD5X - optional Moonraker foundation component
#
# Keep the constructor/load path small and non-blocking. Optional product
# modules may degrade independently; failure of Z Calibration must not make
# Moonraker or the Platform Foundation component unavailable.

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from ..common import RequestType, TransportType

try:
    from . import plugins_ad5x_zcalibration as zcore
except Exception as exc:  # pragma: no cover - deployment/lifecycle coverage
    zcore = None  # type: ignore[assignment]
    _ZCORE_IMPORT_ERROR: Optional[str] = type(exc).__name__
else:
    _ZCORE_IMPORT_ERROR = None


API_VERSION = "1.0"
BACKEND_VERSION = "0.1.2"

SNAPSHOT_ENDPOINT = "/server/plugins_ad5x/snapshot"
Z_RECONCILE_ENDPOINT = "/server/plugins_ad5x/z_calibration/reconcile"
Z_DIAGNOSTICS_ENDPOINT = "/server/plugins_ad5x/z_calibration/diagnostics"
SNAPSHOT_CHANGED_EVENT = "plugins_ad5x:snapshot_changed"
SNAPSHOT_CHANGED_NOTIFY_NAME = "plugins_ad5x_snapshot_changed"
Z_MODULE_SCHEMA_VERSION = "1.0"
Z_DIAGNOSTIC_CAPACITY = 64
Z_EFFECTIVE_OFFSET_TOLERANCE = 1e-6

Z_REMOTE_JOB_START = "plugins_ad5x_z_job_start"
Z_HOOK_OBJECT = "gcode_macro _USER_START_PRINT"
Z_HOOK_MARKER = "plugins_ad5x_z_hook"
_Z_TERMINAL_JOB_EVENTS = {"complete", "cancelled", "error", "standby"}
_Z_START_MODES = {"global", "job", "none"}

_Z_CAPABILITIES = [
    "effective_offset_reconciliation",
    "diagnostic_history",
    "zmod_post_start_adoption",
    "job_lifecycle_cleanup",
    "runtime_hook_detection",
]


class PluginsAD5X:
    def __init__(self, config: Any) -> None:
        self.server = config.get_server()
        getboolean = getattr(config, "getboolean", None)
        self._z_write_enabled = (
            bool(getboolean("z_offset_writes_enabled", False))
            if callable(getboolean)
            else False
        )
        self._revision = 1
        self._z_runtime_signature: Optional[tuple[Any, ...]] = None
        self._z_last_error: Optional[str] = None
        self._z_last_actual: Optional[float] = None
        self._z_hook_loaded = False
        self._z_hook_status = "unknown"
        self._z_offsets = zcore.OffsetComposition() if zcore is not None else None
        self._z_diagnostics = (
            zcore.BoundedDiagnosticLog(Z_DIAGNOSTIC_CAPACITY)
            if zcore is not None
            else None
        )
        self._z_runtime: Dict[str, Any] = {
            "klippy": "unknown",
            "print_state": "unknown",
            "homed_axes": "",
        }
        self._z_job: Dict[str, Any] = {
            "phase": "idle",
            "mode": None,
            "source_z_offset": None,
            "baseline_effective": None,
            "applied_target": None,
        }

        transports = TransportType.HTTP | TransportType.WEBSOCKET
        self.server.register_endpoint(
            SNAPSHOT_ENDPOINT,
            RequestType.GET,
            self._handle_snapshot,
            transports=transports,
            auth_required=True,
        )
        self.server.register_endpoint(
            Z_RECONCILE_ENDPOINT,
            RequestType.POST,
            self._handle_z_reconcile,
            transports=transports,
            auth_required=True,
        )
        self.server.register_endpoint(
            Z_DIAGNOSTICS_ENDPOINT,
            RequestType.GET,
            self._handle_z_diagnostics,
            transports=transports,
            auth_required=True,
        )
        self.server.register_notification(
            SNAPSHOT_CHANGED_EVENT,
            SNAPSHOT_CHANGED_NOTIFY_NAME,
        )

        register_event_handler = getattr(self.server, "register_event_handler", None)
        if callable(register_event_handler):
            register_event_handler(
                "server:klippy_disconnect", self._handle_klippy_disconnect
            )
            register_event_handler("server:klippy_ready", self._handle_klippy_ready)
            register_event_handler(
                "job_state:state_changed", self._handle_job_state_changed
            )

        register_remote_method = getattr(self.server, "register_remote_method", None)
        if callable(register_remote_method):
            register_remote_method(Z_REMOTE_JOB_START, self._remote_z_job_start)

    def _z_module_snapshot(self) -> Dict[str, Any]:
        core_available = zcore is not None and self._z_offsets is not None
        runtime_available = core_available and self._z_runtime.get("klippy") == "ready"
        health = "ok" if runtime_available and not self._z_last_error else "degraded"
        if not core_available:
            unavailable_reason = "core_unavailable"
        elif self._z_last_error:
            unavailable_reason = self._z_last_error
        elif not runtime_available:
            unavailable_reason = "klippy_unavailable"
        else:
            unavailable_reason = None

        if self._z_offsets is None:
            offset_state: Dict[str, Any] = {
                "auto_alignment": 0.0,
                "persistent_user": 0.0,
                "slicer_job": 0.0,
                "live_adjustment": 0.0,
                "external_unknown": 0.0,
                "known_total": 0.0,
                "effective": None,
                "provenance_status": "unavailable",
            }
        else:
            offset_state = {
                "auto_alignment": self._z_offsets.auto_alignment,
                "persistent_user": self._z_offsets.persistent_user,
                "slicer_job": self._z_offsets.slicer_job,
                "live_adjustment": self._z_offsets.live_adjustment,
                "external_unknown": self._z_offsets.external_unknown,
                "known_total": self._z_offsets.known_total,
                "effective": self._z_offsets.effective if runtime_available else None,
                "provenance_status": (
                    "external_unknown"
                    if runtime_available
                    and abs(self._z_offsets.external_unknown)
                    > Z_EFFECTIVE_OFFSET_TOLERANCE
                    else "reconciled" if runtime_available else "unavailable"
                ),
            }

        return {
            "schema_version": Z_MODULE_SCHEMA_VERSION,
            "support": "supported",
            "enabled": True,
            "presence": "present",
            "available": runtime_available,
            "health": health,
            "capabilities": list(_Z_CAPABILITIES),
            "state": {
                "calibration": {
                    "state": "idle",
                    "motion_actions_enabled": False,
                    "offset_hook_enabled": self._z_hook_loaded,
                    "offset_hook_status": self._z_hook_status,
                    "offset_write_enabled": self._z_write_enabled,
                },
                "offset": offset_state,
                "job": dict(self._z_job),
                "runtime": dict(self._z_runtime),
                "safety": {
                    "fail_closed": True,
                    "h7_role": "secondary",
                    "last_error": unavailable_reason,
                },
            },
        }

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "api_version": API_VERSION,
            "backend_version": BACKEND_VERSION,
            "revision": self._revision,
            "backend": {"health": "ok"},
            "modules": {"z_calibration": self._z_module_snapshot()},
        }

    async def _handle_snapshot(self, _web_request: Any) -> Dict[str, Any]:
        await self._refresh_z_runtime()
        return self.get_snapshot()

    async def _handle_z_reconcile(self, _web_request: Any) -> Dict[str, Any]:
        await self._refresh_z_runtime(force_diagnostic=True)
        return {"revision": self._revision, "module": self._z_module_snapshot()}

    async def _handle_z_diagnostics(self, _web_request: Any) -> Dict[str, Any]:
        events = []
        if self._z_diagnostics is not None:
            events = [
                {
                    "schema_version": event.schema_version,
                    "sequence": event.sequence,
                    "timestamp": event.timestamp,
                    "correlation_id": event.correlation_id,
                    "event_type": event.event_type,
                    "payload": dict(event.payload),
                }
                for event in self._z_diagnostics.recent()
            ]
        return {"schema_version": Z_MODULE_SCHEMA_VERSION, "events": events}

    async def _refresh_z_runtime(self, *, force_diagnostic: bool = False) -> None:
        if zcore is None or self._z_offsets is None:
            self._set_z_runtime_unavailable(
                "core_unavailable",
                detail=_ZCORE_IMPORT_ERROR,
                force_diagnostic=force_diagnostic,
            )
            return
        lookup_component = getattr(self.server, "lookup_component", None)
        if not callable(lookup_component):
            self._set_z_runtime_unavailable(
                "klippy_api_unavailable", force_diagnostic=force_diagnostic
            )
            return
        try:
            klippy_apis = lookup_component("klippy_apis")
            status = await klippy_apis.query_objects(
                {
                    "gcode_move": ["homing_origin"],
                    "print_stats": ["state"],
                    "toolhead": ["homed_axes"],
                },
                default=None,
            )
            actual, print_state, homed_axes = self._parse_klippy_z_state(status)
            hook_loaded, hook_status = await self._detect_z_hook(klippy_apis)
            previous_external = self._z_offsets.external_unknown
            previous_hook_status = self._z_hook_status
            self._z_offsets = self._z_offsets.reconcile_actual(
                actual, tolerance=Z_EFFECTIVE_OFFSET_TOLERANCE
            )
            self._z_last_actual = actual
            self._z_hook_loaded = hook_loaded
            self._z_hook_status = hook_status
            self._z_runtime = {
                "klippy": "ready",
                "print_state": print_state,
                "homed_axes": homed_axes,
            }
            if self._z_last_error in {
                "klippy_disconnected",
                "klippy_query_failed",
                "klippy_api_unavailable",
            }:
                self._z_last_error = None
            signature = (
                "ready",
                print_state,
                homed_axes,
                round(actual, 9),
                round(self._z_offsets.external_unknown, 9),
                hook_loaded,
                hook_status,
            )
            semantic_change = signature != self._z_runtime_signature
            self._z_runtime_signature = signature
            if self._z_diagnostics is not None and (
                force_diagnostic
                or semantic_change
                or previous_hook_status != hook_status
                or abs(previous_external - self._z_offsets.external_unknown)
                > Z_EFFECTIVE_OFFSET_TOLERANCE
            ):
                self._z_diagnostics.emit(
                    "offset_reconciled",
                    correlation_id="runtime",
                    payload={
                        "actual_effective": actual,
                        "known_total": self._z_offsets.known_total,
                        "external_unknown": self._z_offsets.external_unknown,
                        "print_state": print_state,
                        "homed_axes": homed_axes,
                        "offset_hook_status": hook_status,
                    },
                )
        except Exception as exc:
            self._set_z_runtime_unavailable(
                "klippy_query_failed",
                detail=type(exc).__name__,
                force_diagnostic=force_diagnostic,
            )

    async def _detect_z_hook(self, klippy_apis: Any) -> tuple[bool, str]:
        """Detect the optional Klipper hook without degrading the whole module."""
        try:
            status = await klippy_apis.query_objects(
                {Z_HOOK_OBJECT: [Z_HOOK_MARKER]},
                default=None,
            )
        except Exception:
            return False, "unknown"
        if not isinstance(status, Mapping):
            return False, "unknown"
        macro = status.get(Z_HOOK_OBJECT)
        if macro is None:
            return False, "absent"
        if not isinstance(macro, Mapping):
            return False, "malformed"
        marker = macro.get(Z_HOOK_MARKER)
        if marker == 1:
            return True, "loaded"
        if marker is None:
            return False, "absent"
        return False, "incompatible"

    @staticmethod
    def _parse_klippy_z_state(status: Any) -> tuple[float, str, str]:
        if not isinstance(status, Mapping):
            raise ValueError("Klippy object query did not return a mapping")
        gcode_move = status.get("gcode_move")
        print_stats = status.get("print_stats")
        toolhead = status.get("toolhead")
        if not isinstance(gcode_move, Mapping):
            raise ValueError("missing gcode_move status")
        if not isinstance(print_stats, Mapping):
            raise ValueError("missing print_stats status")
        if not isinstance(toolhead, Mapping):
            raise ValueError("missing toolhead status")
        origin = gcode_move.get("homing_origin")
        if not isinstance(origin, (list, tuple)) or len(origin) < 3:
            raise ValueError("invalid gcode_move.homing_origin")
        actual = float(origin[2])
        if zcore is not None:
            actual = zcore._finite(actual, "actual_effective")
        print_state = print_stats.get("state")
        homed_axes = toolhead.get("homed_axes")
        if not isinstance(print_state, str) or not print_state:
            raise ValueError("invalid print_stats.state")
        if not isinstance(homed_axes, str):
            raise ValueError("invalid toolhead.homed_axes")
        return actual, print_state, homed_axes

    def _set_z_runtime_unavailable(
        self,
        reason: str,
        *,
        detail: Optional[str] = None,
        force_diagnostic: bool = False,
    ) -> None:
        signature = ("unavailable", reason, detail)
        semantic_change = signature != self._z_runtime_signature
        self._z_runtime_signature = signature
        self._z_last_error = reason
        self._z_last_actual = None
        self._z_hook_loaded = False
        self._z_hook_status = "unknown"
        self._z_runtime = {
            "klippy": "unavailable",
            "print_state": "unknown",
            "homed_axes": "",
        }
        if self._z_diagnostics is not None and (semantic_change or force_diagnostic):
            payload: Dict[str, Any] = {"reason": reason}
            if detail:
                payload["detail"] = detail
            self._z_diagnostics.emit(
                "runtime_unavailable",
                correlation_id="runtime",
                payload=payload,
            )

    def _server_error(self, message: str, status_code: int = 400) -> Exception:
        factory = getattr(self.server, "error", None)
        if callable(factory):
            return factory(message, status_code)
        return RuntimeError(message)

    async def _remote_z_job_start(
        self, mode: str = "none", z_offset: float = 99.0
    ) -> Dict[str, Any]:
        """Adopt Z-Mod's completed START_PRINT offset and add owned deltas once."""
        if zcore is None or self._z_offsets is None:
            raise self._server_error("Z calibration core is unavailable", 503)
        mode = str(mode).strip().lower()
        if mode not in _Z_START_MODES:
            raise self._server_error(f"Unsupported Z start mode: {mode}", 400)
        source_z = zcore._finite(float(z_offset), "source_z_offset")

        fingerprint = (mode, round(source_z, 9))
        if self._z_job.get("phase") == "active":
            active_fingerprint = (
                self._z_job.get("mode"),
                round(float(self._z_job.get("source_z_offset", 99.0)), 9),
            )
            if active_fingerprint != fingerprint:
                raise self._server_error(
                    "A different Z job lifecycle is already active", 409
                )
            await self._refresh_z_runtime(force_diagnostic=True)
            if not self._z_hook_loaded:
                raise self._server_error(
                    "Plugins AD5X Z lifecycle hook is not loaded", 409
                )
            return {
                "status": "already_applied",
                "revision": self._revision,
                "module": self._z_module_snapshot(),
            }

        await self._refresh_z_runtime(force_diagnostic=True)
        if self._z_runtime.get("klippy") != "ready" or self._z_last_actual is None:
            raise self._server_error("Klippy is not ready for Z adoption", 503)
        if not self._z_hook_loaded:
            raise self._server_error(
                "Plugins AD5X Z lifecycle hook is not loaded", 409
            )
        print_state = self._z_runtime.get("print_state")
        if print_state not in {"standby", "printing"}:
            raise self._server_error(
                f"Z start adoption is invalid while print state is {print_state}", 409
            )

        baseline = self._z_last_actual
        previous = self._z_offsets
        if mode == "global":
            if abs(previous.persistent_user) > Z_EFFECTIVE_OFFSET_TOLERANCE:
                raise self._server_error(
                    "Plugins persistent trim conflicts with Z-Mod global offset ownership",
                    409,
                )
            adopted = zcore.OffsetComposition(
                auto_alignment=previous.auto_alignment,
                persistent_user=0.0,
                slicer_job=0.0,
                live_adjustment=0.0,
                external_unknown=baseline,
            )
        elif mode == "job":
            if source_z == 99.0:
                raise self._server_error(
                    "Job Z-offset mode requires an explicit Z_OFFSET value", 400
                )
            if abs(baseline - source_z) > Z_EFFECTIVE_OFFSET_TOLERANCE:
                raise self._server_error(
                    "Observed Z-Mod job offset does not match START_PRINT Z_OFFSET", 409
                )
            adopted = zcore.OffsetComposition(
                auto_alignment=previous.auto_alignment,
                persistent_user=previous.persistent_user,
                slicer_job=source_z,
                live_adjustment=0.0,
                external_unknown=0.0,
            )
        else:
            if source_z != 99.0:
                raise self._server_error(
                    "No-offset mode requires the Z-Mod sentinel Z_OFFSET=99", 400
                )
            adopted = zcore.OffsetComposition(
                auto_alignment=previous.auto_alignment,
                persistent_user=previous.persistent_user,
                slicer_job=0.0,
                live_adjustment=0.0,
                external_unknown=baseline,
            )

        target = adopted.effective
        fallback_target = 0.0 if mode == "job" else baseline
        needs_write = abs(target - baseline) > Z_EFFECTIVE_OFFSET_TOLERANCE
        if needs_write and not self._z_write_enabled:
            self._z_last_error = "offset_write_gate_closed"
            if self._z_diagnostics is not None:
                self._z_diagnostics.emit(
                    "offset_write_blocked",
                    correlation_id="job",
                    payload={
                        "mode": mode,
                        "baseline_effective": baseline,
                        "requested_target": target,
                    },
                )
            raise self._server_error(
                "Plugins AD5X Z-offset writes are disabled pending hardware acceptance",
                409,
            )

        self._z_offsets = adopted
        try:
            if needs_write:
                klippy_apis = self.server.lookup_component("klippy_apis")
                script = f"SET_GCODE_OFFSET Z={target:.9f} MOVE=0"
                await klippy_apis.run_gcode(script)
                if self._z_diagnostics is not None:
                    self._z_diagnostics.emit(
                        "offset_apply_requested",
                        correlation_id="job",
                        payload={
                            "mode": mode,
                            "baseline_effective": baseline,
                            "target_effective": target,
                        },
                    )
                await self._refresh_z_runtime(force_diagnostic=True)
                if (
                    self._z_last_actual is None
                    or abs(self._z_last_actual - target)
                    > Z_EFFECTIVE_OFFSET_TOLERANCE
                ):
                    raise RuntimeError("offset_apply_verification_failed")
            self._z_job = {
                "phase": "active",
                "mode": mode,
                "source_z_offset": source_z,
                "baseline_effective": baseline,
                "applied_target": target,
            }
            self._z_last_error = None
            if self._z_diagnostics is not None:
                self._z_diagnostics.emit(
                    "job_start_adopted",
                    correlation_id="job",
                    payload={
                        "mode": mode,
                        "source_z_offset": source_z,
                        "baseline_effective": baseline,
                        "target_effective": target,
                        "auto_alignment": adopted.auto_alignment,
                        "persistent_user": adopted.persistent_user,
                        "slicer_job": adopted.slicer_job,
                        "external_unknown": adopted.external_unknown,
                    },
                )
            self.invalidate_snapshot()
            return {
                "status": "applied",
                "revision": self._revision,
                "module": self._z_module_snapshot(),
            }
        except Exception as exc:
            await self._best_effort_z_rollback(
                fallback_target, previous=previous, reason=type(exc).__name__
            )
            raise self._server_error(
                "Z offset composition failed; fallback/reconciliation was attempted",
                503,
            )

    async def _best_effort_z_rollback(
        self, target: float, *, previous: Any, reason: str
    ) -> None:
        rollback_ok = False
        try:
            klippy_apis = self.server.lookup_component("klippy_apis")
            await klippy_apis.run_gcode(
                f"SET_GCODE_OFFSET Z={float(target):.9f} MOVE=0"
            )
            await self._refresh_z_runtime(force_diagnostic=True)
            rollback_ok = (
                self._z_last_actual is not None
                and abs(self._z_last_actual - float(target))
                <= Z_EFFECTIVE_OFFSET_TOLERANCE
            )
        except Exception:
            rollback_ok = False
        self._z_offsets = previous.clear_transient()
        self._z_job = {
            "phase": "idle",
            "mode": None,
            "source_z_offset": None,
            "baseline_effective": None,
            "applied_target": None,
        }
        self._z_last_error = (
            "offset_apply_failed"
            if rollback_ok
            else "offset_apply_failed_reconciliation_required"
        )
        if self._z_diagnostics is not None:
            self._z_diagnostics.emit(
                "offset_apply_failed",
                correlation_id="job",
                payload={
                    "reason": reason,
                    "fallback_target": float(target),
                    "fallback_verified": rollback_ok,
                },
            )
        self.invalidate_snapshot()

    def _handle_job_state_changed(
        self,
        event: Any,
        _prev_stats: Optional[Mapping[str, Any]] = None,
        _new_stats: Optional[Mapping[str, Any]] = None,
    ) -> None:
        name = self._job_event_name(event)
        if name not in _Z_TERMINAL_JOB_EVENTS:
            return
        if self._z_job.get("phase") != "active":
            return
        self._clear_z_job_transients(name)

    @staticmethod
    def _job_event_name(event: Any) -> str:
        value = getattr(event, "value", event)
        text = str(value).strip().lower()
        if "." in text:
            text = text.rsplit(".", 1)[-1]
        return text

    def _clear_z_job_transients(self, reason: str) -> None:
        if self._z_offsets is not None:
            self._z_offsets = self._z_offsets.clear_transient()
        self._z_job = {
            "phase": "idle",
            "mode": None,
            "source_z_offset": None,
            "baseline_effective": None,
            "applied_target": None,
        }
        self._z_last_error = None
        if self._z_diagnostics is not None:
            self._z_diagnostics.emit(
                "job_transients_cleared",
                correlation_id="job",
                payload={"reason": reason},
            )
        self.invalidate_snapshot()

    def _handle_klippy_disconnect(self, *_args: Any) -> None:
        if self._z_job.get("phase") == "active":
            self._clear_z_job_transients("klippy_disconnect")
        self._set_z_runtime_unavailable("klippy_disconnected")
        self.invalidate_snapshot()

    async def _handle_klippy_ready(self, *_args: Any) -> None:
        before = self._z_runtime_signature
        await self._refresh_z_runtime()
        if self._z_runtime_signature != before:
            self.invalidate_snapshot()

    def invalidate_snapshot(self) -> int:
        self._revision += 1
        self.server.send_event(
            SNAPSHOT_CHANGED_EVENT, {"revision": self._revision}
        )
        return self._revision


def load_component(config: Any) -> PluginsAD5X:
    return PluginsAD5X(config)
