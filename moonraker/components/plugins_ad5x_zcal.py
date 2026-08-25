# Plugins AD5X - standalone Z Calibration observer component
#
# This component is deliberately additive. It does not own the shared
# plugins_ad5x backend host, so it can coexist with an IFS-capable
# plugins_ad5x.py on the same Moonraker runtime.

from __future__ import annotations

import math
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
MODULE_VERSION = "0.1.5"
Z_MODULE_SCHEMA_VERSION = "1.2"

Z_SNAPSHOT_ENDPOINT = "/server/plugins_ad5x/z_calibration/snapshot"
Z_RECONCILE_ENDPOINT = "/server/plugins_ad5x/z_calibration/reconcile"
Z_DIAGNOSTICS_ENDPOINT = "/server/plugins_ad5x/z_calibration/diagnostics"
Z_CHANGED_EVENT = "plugins_ad5x:z_calibration_changed"
Z_CHANGED_NOTIFY_NAME = "plugins_ad5x_z_calibration_changed"

Z_DIAGNOSTIC_CAPACITY = 64
Z_EFFECTIVE_OFFSET_TOLERANCE = 1e-6
ZMOD_SLICER_OFFSET_SENTINEL = 99.0
Z_RC_POLICY_OBJECT = "gcode_macro _AD5X_Z_SAVED_CHECK_POLICY"
Z_RC_POLICY_ID = "zcal-saved-check-v1-20260817"
Z_V6_POLICY_OBJECT = "gcode_macro _ADZ_SAVED_CHECK_POLICY"
Z_V6_ANCHOR_POLICY_ID = "adz-runtime-mesh-anchor-v6-20260825"
Z_MESH_ANCHOR_OBJECT = "ad5x_z_mesh_anchor"
Z_USER_START_CONFIG_KEY = "gcode_macro _user_start_print"
Z_RC_GUARD = "_ADZ_SAVED_CHECK_POLICY"
Z_CC_APPLY = "CC_APPLY_PROFILE"

_Z_TERMINAL_JOB_EVENTS = {"complete", "cancelled", "error", "standby"}
_Z_CAPABILITIES = [
    "effective_offset_provenance",
    "diagnostic_history",
    "zmod_saved_check_observation",
    "runtime_policy_detection",
    "frontend_neutral_snapshot",
    "read_only_reconciliation",
    "job_thermal_provenance",
    "transient_machine_anchor_provenance",
]


def _finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _mapping(parent: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = parent.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"missing or malformed {key}")
    return value


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"false", "0", "off", "no", ""}:
            return False
        if normalized in {"true", "1", "on", "yes"}:
            return True
    return bool(value)


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return _finite(value, "optional_float")


def _normalize_slicer_request(value: Any) -> Optional[float]:
    requested = _optional_float(value)
    if requested is None:
        return None
    if math.isclose(
        requested,
        ZMOD_SLICER_OFFSET_SENTINEL,
        rel_tol=0.0,
        abs_tol=Z_EFFECTIVE_OFFSET_TOLERANCE,
    ):
        return None
    return requested


def _safe_optional_float(value: Any) -> Optional[float]:
    try:
        return _optional_float(value)
    except ValueError:
        return None


def _thermal_match_status(control: Optional[float], metadata: Optional[float]) -> str:
    if control is None and metadata is None:
        return "unavailable"
    if control is None:
        return "metadata_only"
    if metadata is None:
        return "start_print_only"
    return (
        "matched"
        if math.isclose(control, metadata, rel_tol=0.0, abs_tol=0.5)
        else "mismatch"
    )


def _derive_job_thermal_context(
    status: Mapping[str, Any], metadata: Mapping[str, Any]
) -> Dict[str, Any]:
    print_stats = status.get("print_stats")
    start_print = status.get("gcode_macro _START_PRINT")
    filename = (
        print_stats.get("filename")
        if isinstance(print_stats, Mapping) and isinstance(print_stats.get("filename"), str)
        else None
    )
    if filename == "":
        filename = None
    bed_target = (
        _safe_optional_float(start_print.get("zbed_temp"))
        if isinstance(start_print, Mapping) else None
    )
    extruder_target = (
        _safe_optional_float(start_print.get("zextruder_temp"))
        if isinstance(start_print, Mapping) else None
    )
    meta_bed = _safe_optional_float(metadata.get("first_layer_bed_temp"))
    meta_extruder = _safe_optional_float(metadata.get("first_layer_extr_temp"))
    return {
        "filename": filename,
        "thermal": {
            "control_source": "zmod_start_print",
            "bed_target": bed_target,
            "extruder_target": extruder_target,
            "first_layer_bed_temp": meta_bed,
            "first_layer_extr_temp": meta_extruder,
            "filament_type": metadata.get("filament_type"),
            "filament_name": metadata.get("filament_name"),
            "metadata_available": bool(metadata),
            "bed_status": _thermal_match_status(bed_target, meta_bed),
            "extruder_status": _thermal_match_status(extruder_target, meta_extruder),
        },
    }


def _derive_machine_anchor_context(
    status: Mapping[str, Any],
    measured_delta: Optional[float],
    *,
    tolerance: float = Z_EFFECTIVE_OFFSET_TOLERANCE,
) -> Dict[str, Any]:
    policy_obj = status.get(Z_V6_POLICY_OBJECT)
    policy_id = (
        policy_obj.get("anchor_policy_id") if isinstance(policy_obj, Mapping) else None
    )
    policy_loaded = policy_id == Z_V6_ANCHOR_POLICY_ID
    finalized_valid = True
    try:
        finalized = (
            int(policy_obj.get("machine_anchor_finalized", 0))
            if isinstance(policy_obj, Mapping)
            else 0
        )
    except (TypeError, ValueError):
        finalized = 0
        finalized_valid = False
    if finalized not in (0, 1):
        finalized_valid = False
    anchor_obj = status.get(Z_MESH_ANCHOR_OBJECT)
    context: Dict[str, Any] = {
        "model": (
            "transient_mesh_anchor_v6" if policy_loaded else "legacy_gcode_offset"
        ),
        "policy_id": policy_id,
        "policy_loaded": policy_loaded,
        "runtime_available": isinstance(anchor_obj, Mapping),
        "active": False,
        "finalized": finalized == 1,
        "shift": 0.0,
        "measured_delta": measured_delta,
        "persistent": None,
        "base_profile": None,
        "runtime_profile": None,
        "point_count": 0,
        "status": "legacy_gcode_offset",
        "offset_component": not policy_loaded,
    }
    if not policy_loaded:
        return context
    if not isinstance(anchor_obj, Mapping):
        context["status"] = "runtime_unavailable"
        context["offset_component"] = False
        return context

    active = _boolish(anchor_obj.get("active", False))
    shift = _safe_optional_float(anchor_obj.get("shift"))
    persistent = anchor_obj.get("persistent")
    point_count_valid = True
    try:
        point_count = int(anchor_obj.get("point_count", 0) or 0)
    except (TypeError, ValueError):
        point_count = 0
        point_count_valid = False
    context.update(
        {
            "active": active,
            "shift": 0.0 if shift is None else shift,
            "persistent": persistent,
            "base_profile": anchor_obj.get("base_profile"),
            "runtime_profile": anchor_obj.get("runtime_profile"),
            "point_count": point_count,
            "offset_component": False,
        }
    )
    if not finalized_valid or not point_count_valid or shift is None:
        context["status"] = "runtime_malformed"
    elif persistent is not False:
        context["status"] = "persistence_violation"
    elif active != (finalized == 1):
        context["status"] = "state_mismatch"
    elif (
        active
        and measured_delta is not None
        and abs(shift - measured_delta) > tolerance
    ):
        context["status"] = "shift_mismatch"
    elif active:
        context["status"] = "active"
    elif measured_delta is not None and abs(measured_delta) > tolerance:
        context["status"] = "pending_transfer"
    else:
        context["status"] = "idle"
    return context


def _macro_commands(raw_gcode: Any) -> list[str]:
    if not isinstance(raw_gcode, str):
        raise ValueError("macro gcode must be a string")
    commands: list[str] = []
    for line in raw_gcode.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        commands.append(stripped.split(";", 1)[0].strip())
    return commands


def _detect_rc_integration(status: Mapping[str, Any]) -> tuple[bool, str, Dict[str, Any]]:
    policy_obj = status.get(Z_RC_POLICY_OBJECT)
    if policy_obj is None:
        policy_status = "absent"
        policy_id = None
    elif not isinstance(policy_obj, Mapping):
        policy_status = "malformed"
        policy_id = None
    else:
        policy_id = policy_obj.get("policy_id")
        policy_status = "loaded" if policy_id == Z_RC_POLICY_ID else "incompatible"

    configfile = status.get("configfile")
    if not isinstance(configfile, Mapping):
        return False, "unknown", {
            "policy_status": policy_status,
            "policy_id": policy_id,
            "hook_commands": None,
        }
    settings = configfile.get("settings")
    if not isinstance(settings, Mapping):
        return False, "unknown", {
            "policy_status": policy_status,
            "policy_id": policy_id,
            "hook_commands": None,
        }
    hook = next(
        (
            value
            for key, value in settings.items()
            if str(key).strip().lower() == Z_USER_START_CONFIG_KEY
        ),
        None,
    )
    if hook is None:
        return False, "absent", {
            "policy_status": policy_status,
            "policy_id": policy_id,
            "hook_commands": None,
        }
    if not isinstance(hook, Mapping):
        return False, "malformed", {
            "policy_status": policy_status,
            "policy_id": policy_id,
            "hook_commands": None,
        }
    try:
        commands = _macro_commands(hook.get("gcode"))
    except ValueError:
        return False, "malformed", {
            "policy_status": policy_status,
            "policy_id": policy_id,
            "hook_commands": None,
        }

    guard_count = commands.count(Z_RC_GUARD)
    expected = commands in ([Z_RC_GUARD], [Z_CC_APPLY, Z_RC_GUARD])
    if guard_count > 1:
        hook_status = "duplicate_guard"
    elif expected and policy_status == "loaded":
        hook_status = "loaded"
    elif expected:
        hook_status = "policy_unavailable"
    elif guard_count == 0:
        hook_status = "absent"
    else:
        hook_status = "incompatible"
    return hook_status == "loaded", hook_status, {
        "policy_status": policy_status,
        "policy_id": policy_id,
        "hook_commands": commands,
    }


def _derive_zmod_provenance(
    status: Mapping[str, Any], *, tolerance: float = Z_EFFECTIVE_OFFSET_TOLERANCE
) -> tuple[Any, Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """Explain only provenance proven on the accepted Z-Mod saved+check path."""
    if zcore is None:
        raise ValueError("z calibration core unavailable")

    gcode_move = _mapping(status, "gcode_move")
    origin = gcode_move.get("homing_origin")
    if not isinstance(origin, (list, tuple)) or len(origin) < 3:
        raise ValueError("invalid gcode_move.homing_origin")
    reported_homing_origin_z = _finite(origin[2], "reported_homing_origin_z")

    toolhead = _mapping(status, "toolhead")
    homed_axes = toolhead.get("homed_axes")
    if not isinstance(homed_axes, str):
        raise ValueError("invalid toolhead.homed_axes")
    z_homed = "z" in homed_axes.lower()
    actual_effective = reported_homing_origin_z if z_homed else None

    save_variables = _mapping(status, "save_variables")
    variables = _mapping(save_variables, "variables")
    screen_macro = status.get("gcode_macro _SCREEN")
    start_macro = status.get("gcode_macro _START_PRINT")
    test_point = status.get("gcode_macro _TEST_POINT")

    screen = screen_macro.get("screen") if isinstance(screen_macro, Mapping) else None
    load_zoffset = int(variables.get("load_zoffset", 1))
    mesh_test = int(variables.get("mesh_test", 1))
    print_leveling = int(variables.get("print_leveling", 0))
    force_kamp = (
        _boolish(start_macro.get("zforce_kamp", False))
        if isinstance(start_macro, Mapping)
        else False
    )
    force_leveling = (
        _boolish(start_macro.get("zforce_leveling", False))
        if isinstance(start_macro, Mapping)
        else False
    )
    requested_job = (
        _normalize_slicer_request(start_macro.get("zzoffset"))
        if isinstance(start_macro, Mapping)
        else None
    )

    auto_known = isinstance(test_point, Mapping) and "temp_z_offset" in test_point
    native_delta = (
        _finite(test_point.get("temp_z_offset"), "temp_z_offset")
        if auto_known
        else 0.0
    )
    machine_anchor = _derive_machine_anchor_context(
        status, native_delta if auto_known else None, tolerance=tolerance
    )
    v6_anchor_model = bool(machine_anchor["policy_loaded"])
    auto_alignment = 0.0 if v6_anchor_model else native_delta

    global_path = screen is False and load_zoffset == 1
    persistent_known = False
    persistent_user = 0.0
    persistent_source = "not_active_on_current_zmod_path"
    slicer_source = "not_attributable"
    slicer_effect = "unknown"
    if global_path:
        raw_offsets = variables.get("gcode_offsets")
        if raw_offsets is None:
            persistent_user = 0.0
            persistent_known = True
            persistent_source = "implicit_zero:LOAD_GCODE_OFFSET"
        elif isinstance(raw_offsets, Mapping):
            persistent_user = _finite(raw_offsets.get("z", 0.0), "gcode_offsets.z")
            persistent_known = True
            persistent_source = "save_variables.variables.gcode_offsets.z"
        else:
            persistent_source = "malformed:save_variables.variables.gcode_offsets"
        slicer_source = "forced_zero:zmod_global_offset_path"
        slicer_effect = "ignored_by_zmod_global_offset_path"

    composition = zcore.OffsetComposition(
        auto_alignment=auto_alignment,
        persistent_user=persistent_user if persistent_known else 0.0,
        slicer_job=0.0,
        live_adjustment=0.0,
    )
    anchor_status = str(machine_anchor["status"])
    reconcile_actual = (
        actual_effective is not None
        and (not v6_anchor_model or anchor_status in {"active", "idle"})
    )
    if reconcile_actual:
        composition = composition.reconcile_actual(actual_effective, tolerance=tolerance)

    missing_known = []
    if not v6_anchor_model and not auto_known:
        missing_known.append("auto_alignment")
    if not persistent_known:
        missing_known.append("persistent_user")

    anchor_fault_status = {
        "runtime_unavailable": "machine_anchor_runtime_unavailable",
        "runtime_malformed": "machine_anchor_runtime_malformed",
        "persistence_violation": "machine_anchor_persistence_violation",
        "state_mismatch": "machine_anchor_state_mismatch",
        "shift_mismatch": "machine_anchor_shift_mismatch",
        "pending_transfer": "machine_anchor_pending",
    }
    if not global_path:
        provenance_status = "unsupported_zmod_offset_path"
    elif v6_anchor_model and anchor_status in anchor_fault_status:
        provenance_status = anchor_fault_status[anchor_status]
    elif missing_known:
        provenance_status = "partial"
    elif not z_homed:
        provenance_status = "not_homed"
    elif abs(composition.external_unknown) > tolerance:
        provenance_status = "external_unknown"
    else:
        provenance_status = "reconciled"

    policy_obj = status.get(Z_RC_POLICY_OBJECT)
    policy_id = policy_obj.get("policy_id") if isinstance(policy_obj, Mapping) else None
    active_profile = None
    bed_mesh = status.get("bed_mesh")
    if isinstance(bed_mesh, Mapping):
        active_profile = bed_mesh.get("profile_name")

    rc_path = {
        "global_offset_path": global_path,
        "screen": screen,
        "load_zoffset": load_zoffset,
        "mesh_test": mesh_test,
        "print_leveling": print_leveling,
        "force_kamp": force_kamp,
        "force_leveling": force_leveling,
        "policy_id": policy_id,
        "policy_identity_ok": policy_id == Z_RC_POLICY_ID,
        "active_mesh_profile": active_profile,
        "machine_anchor_model": machine_anchor["model"],
        "machine_anchor_status": machine_anchor["status"],
        "machine_anchor_base_profile": machine_anchor["base_profile"],
        "accepted_saved_check_flags": (
            global_path
            and mesh_test == 3
            and print_leveling == 0
            and not force_kamp
            and not force_leveling
            and policy_id == Z_RC_POLICY_ID
        ),
    }
    sources = {
        "effective": (
            "gcode_move.homing_origin.z" if z_homed else "unavailable:not_homed"
        ),
        "persistent_user": persistent_source,
        "auto_alignment": (
            "not_in_gcode_offset:v6_transient_mesh_anchor"
            if v6_anchor_model
            else (
                "gcode_macro _TEST_POINT.temp_z_offset"
                if auto_known else "unavailable"
            )
        ),
        "machine_anchor": (
            "ad5x_z_mesh_anchor.shift"
            if v6_anchor_model and machine_anchor["runtime_available"]
            else (
                "unavailable:v6_runtime" if v6_anchor_model
                else "not_separate:legacy_gcode_offset"
            )
        ),
        "slicer_job": slicer_source,
        "live_adjustment": (
            "not_attributable:not_homed"
            if not z_homed
            else (
                "derived_zero:no_residual"
                if abs(composition.external_unknown) <= tolerance
                else "not_attributable:residual_is_external_unknown"
            )
        ),
        "external_unknown": (
            "not_evaluated:not_homed" if not z_homed else "reconciliation_residual"
        ),
    }
    provenance = {
        "status": provenance_status,
        "model": "zmod-saved-check-observer-v1",
        "sources": sources,
        "missing_components": missing_known,
        "actual_effective": actual_effective,
        "reported_homing_origin_z": reported_homing_origin_z,
        "requested_slicer_z_offset": requested_job,
        "slicer_z_offset_effect": slicer_effect,
        "rc_path": rc_path,
        "machine_anchor": dict(machine_anchor),
    }
    runtime = {
        "actual_effective": actual_effective,
        "reported_homing_origin_z": reported_homing_origin_z,
        "effective_valid": z_homed,
        "print_state": _mapping(status, "print_stats").get("state"),
        "homed_axes": homed_axes,
    }
    job = {
        "phase": runtime["print_state"],
        "requested_slicer_z_offset": requested_job,
        "slicer_z_offset_effect": slicer_effect,
    }
    return composition, provenance, runtime, job


class PluginsAD5XZCalibration:
    def __init__(self, config: Any) -> None:
        self.server = config.get_server()
        self._revision = 1
        self._z_runtime_signature: Optional[tuple[Any, ...]] = None
        self._z_last_error: Optional[str] = None
        self._z_hook_loaded = False
        self._z_hook_status = "unknown"
        self._z_integration: Dict[str, Any] = {
            "policy_status": "unknown",
            "policy_id": None,
            "hook_commands": None,
        }
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
            "effective_valid": False,
        }
        self._z_job: Dict[str, Any] = {
            "phase": "unknown",
            "requested_slicer_z_offset": None,
            "slicer_z_offset_effect": "unknown",
        }
        self._z_provenance: Dict[str, Any] = {
            "status": "unavailable",
            "model": "zmod-saved-check-observer-v1",
            "sources": {},
            "missing_components": [],
            "actual_effective": None,
            "reported_homing_origin_z": None,
            "requested_slicer_z_offset": None,
            "slicer_z_offset_effect": "unknown",
            "rc_path": {},
            "machine_anchor": {
                "model": "unknown",
                "policy_loaded": False,
                "runtime_available": False,
                "active": False,
                "finalized": False,
                "shift": 0.0,
                "status": "unavailable",
                "offset_component": False,
            },
        }

        transports = TransportType.HTTP | TransportType.WEBSOCKET
        self.server.register_endpoint(
            Z_SNAPSHOT_ENDPOINT,
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
        self.server.register_notification(Z_CHANGED_EVENT, Z_CHANGED_NOTIFY_NAME)

        register_event_handler = getattr(self.server, "register_event_handler", None)
        if callable(register_event_handler):
            register_event_handler(
                "server:klippy_disconnect", self._handle_klippy_disconnect
            )
            register_event_handler("server:klippy_ready", self._handle_klippy_ready)
            register_event_handler(
                "job_state:state_changed", self._handle_job_state_changed
            )

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
            effective_valid = bool(self._z_runtime.get("effective_valid", False))
            offset_state = {
                "auto_alignment": self._z_offsets.auto_alignment,
                "persistent_user": self._z_offsets.persistent_user,
                "slicer_job": self._z_offsets.slicer_job,
                "live_adjustment": self._z_offsets.live_adjustment,
                "external_unknown": self._z_offsets.external_unknown,
                "known_total": self._z_offsets.known_total,
                "effective": (
                    self._z_offsets.effective
                    if runtime_available and effective_valid
                    else None
                ),
                "effective_offset": (
                    self._z_offsets.effective
                    if runtime_available and effective_valid
                    else None
                ),
                "provenance_status": (
                    self._z_provenance.get("status", "unavailable")
                    if runtime_available
                    else "unavailable"
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
                    "state": "observer",
                    "motion_actions_enabled": False,
                    "motion_owner": "zmod",
                    "offset_hook_enabled": self._z_hook_loaded,
                    "offset_hook_status": self._z_hook_status,
                    "offset_write_enabled": False,
                    "integration": dict(self._z_integration),
                },
                "offset": offset_state,
                "machine_anchor": dict(
                    self._z_provenance.get("machine_anchor", {})
                ),
                "provenance": dict(self._z_provenance),
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
            "module_version": MODULE_VERSION,
            "revision": self._revision,
            "module": self._z_module_snapshot(),
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
                    "print_stats": ["state", "filename"],
                    "toolhead": ["homed_axes"],
                    "save_variables": ["variables"],
                    "gcode_macro _TEST_POINT": ["temp_z_offset"],
                    "gcode_macro _SCREEN": ["screen"],
                    "gcode_macro _START_PRINT": [
                        "zzoffset",
                        "zforce_kamp",
                        "zforce_leveling",
                        "zbed_temp",
                        "zextruder_temp",
                    ],
                    Z_RC_POLICY_OBJECT: [
                        "policy_id",
                        "max_auto_alignment",
                        "saved_profile",
                        "saved_reference",
                        "reference_tolerance",
                    ],
                    Z_V6_POLICY_OBJECT: [
                        "anchor_policy_id",
                        "max_machine_anchor",
                        "machine_anchor_finalized",
                    ],
                    Z_MESH_ANCHOR_OBJECT: [
                        "active",
                        "shift",
                        "base_profile",
                        "runtime_profile",
                        "point_count",
                        "persistent",
                        "max_abs_shift",
                    ],
                    "bed_mesh": ["profile_name"],
                    "configfile": ["settings"],
                },
                default=None,
            )
            if not isinstance(status, Mapping):
                raise ValueError("Klippy object query did not return a mapping")
            offsets, provenance, runtime, job = _derive_zmod_provenance(status)
            metadata: Mapping[str, Any] = {}
            thermal_context = _derive_job_thermal_context(status, metadata)
            filename = thermal_context.get("filename")
            if isinstance(filename, str) and filename:
                try:
                    file_manager = lookup_component("file_manager")
                    get_file_metadata = getattr(file_manager, "get_file_metadata", None)
                    if callable(get_file_metadata):
                        raw_metadata = get_file_metadata(filename)
                        if isinstance(raw_metadata, Mapping):
                            metadata = raw_metadata
                except Exception:
                    metadata = {}
            job.update(_derive_job_thermal_context(status, metadata))
            print_state = runtime.get("print_state")
            homed_axes = runtime.get("homed_axes")
            if not isinstance(print_state, str) or not print_state:
                raise ValueError("invalid print_stats.state")
            if not isinstance(homed_axes, str):
                raise ValueError("invalid toolhead.homed_axes")
            hook_loaded, hook_status, integration = _detect_rc_integration(status)

            previous_status = self._z_provenance.get("status")
            previous_hook_status = self._z_hook_status
            self._z_offsets = offsets
            self._z_provenance = provenance
            self._z_hook_loaded = hook_loaded
            self._z_hook_status = hook_status
            self._z_integration = integration
            self._z_runtime = {
                "klippy": "ready",
                "print_state": print_state,
                "homed_axes": homed_axes,
                "effective_valid": bool(runtime.get("effective_valid", False)),
            }
            self._z_job = job
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
                bool(runtime.get("effective_valid", False)),
                round(offsets.effective, 9),
                round(offsets.persistent_user, 9),
                round(offsets.auto_alignment, 9),
                round(offsets.external_unknown, 9),
                provenance.get("status"),
                hook_status,
                provenance.get("requested_slicer_z_offset"),
                provenance.get("machine_anchor", {}).get("status"),
                provenance.get("machine_anchor", {}).get("active"),
                provenance.get("machine_anchor", {}).get("finalized"),
                provenance.get("machine_anchor", {}).get("shift"),
                provenance.get("machine_anchor", {}).get("measured_delta"),
                job.get("filename"),
                job.get("thermal", {}).get("bed_target"),
                job.get("thermal", {}).get("extruder_target"),
                job.get("thermal", {}).get("first_layer_bed_temp"),
                job.get("thermal", {}).get("first_layer_extr_temp"),
                job.get("thermal", {}).get("bed_status"),
                job.get("thermal", {}).get("extruder_status"),
            )
            semantic_change = signature != self._z_runtime_signature
            self._z_runtime_signature = signature
            if self._z_diagnostics is not None and (
                force_diagnostic
                or semantic_change
                or previous_status != provenance.get("status")
                or previous_hook_status != hook_status
            ):
                self._z_diagnostics.emit(
                    "offset_provenance_reconciled",
                    correlation_id="runtime",
                    payload={
                        "actual_effective": provenance.get("actual_effective"),
                        "reported_homing_origin_z": provenance.get(
                            "reported_homing_origin_z"
                        ),
                        "persistent_user": offsets.persistent_user,
                        "auto_alignment": offsets.auto_alignment,
                        "slicer_job": offsets.slicer_job,
                        "live_adjustment": offsets.live_adjustment,
                        "external_unknown": offsets.external_unknown,
                        "provenance_status": provenance.get("status"),
                        "offset_hook_status": hook_status,
                        "requested_slicer_z_offset": provenance.get(
                            "requested_slicer_z_offset"
                        ),
                        "job_thermal": dict(job.get("thermal", {})),
                        "machine_anchor": dict(
                            provenance.get("machine_anchor", {})
                        ),
                    },
                )
        except Exception as exc:
            self._set_z_runtime_unavailable(
                "klippy_query_failed",
                detail=type(exc).__name__,
                force_diagnostic=force_diagnostic,
            )

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
        self._z_hook_loaded = False
        self._z_hook_status = "unknown"
        self._z_integration = {
            "policy_status": "unknown",
            "policy_id": None,
            "hook_commands": None,
        }
        if zcore is not None:
            self._z_offsets = zcore.OffsetComposition()
        self._z_provenance = {
            "status": "unavailable",
            "model": "zmod-saved-check-observer-v1",
            "sources": {},
            "missing_components": [],
            "actual_effective": None,
            "reported_homing_origin_z": None,
            "requested_slicer_z_offset": None,
            "slicer_z_offset_effect": "unknown",
            "rc_path": {},
            "machine_anchor": {
                "model": "unknown",
                "policy_loaded": False,
                "runtime_available": False,
                "active": False,
                "finalized": False,
                "shift": 0.0,
                "status": "unavailable",
                "offset_component": False,
            },
        }
        self._z_runtime = {
            "klippy": "unavailable",
            "print_state": "unknown",
            "homed_axes": "",
            "effective_valid": False,
        }
        self._z_job = {
            "phase": "unknown",
            "requested_slicer_z_offset": None,
            "slicer_z_offset_effect": "unknown",
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

    def _handle_klippy_disconnect(self, *_args: Any) -> None:
        self._set_z_runtime_unavailable("klippy_disconnected", force_diagnostic=True)
        self.invalidate_snapshot()

    async def _handle_klippy_ready(self, *_args: Any) -> None:
        await self._refresh_z_runtime(force_diagnostic=True)
        self.invalidate_snapshot()

    def _handle_job_state_changed(self, *args: Any) -> None:
        state = None
        for item in args:
            if isinstance(item, str):
                state = item
            elif isinstance(item, Mapping) and isinstance(item.get("state"), str):
                state = item.get("state")
        if state in _Z_TERMINAL_JOB_EVENTS:
            self._z_job = {
                "phase": state,
                "requested_slicer_z_offset": None,
                "slicer_z_offset_effect": "unknown",
            }
        self.invalidate_snapshot()

    def invalidate_snapshot(self) -> int:
        self._revision += 1
        send_event = getattr(self.server, "send_event", None)
        if callable(send_event):
            send_event(Z_CHANGED_EVENT, {"revision": self._revision})
        return self._revision


def load_component(config: Any) -> PluginsAD5XZCalibration:
    return PluginsAD5XZCalibration(config)
