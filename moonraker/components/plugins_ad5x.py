# Plugins AD5X - optional Moonraker foundation component

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

from ..common import RequestType, TransportType

try:
    from .plugins_ad5x_ifs_model import (
        IFS_SCHEMA_VERSION,
        build_job_launch_gate,
        build_job_mapping_draft,
        build_job_preview_token,
        build_preprint_plan,
        normalize_appearance,
        normalize_module,
        normalize_spool_metadata,
    )
except ImportError:
    # Minimal test/source-tree compatibility. Production installer deploys the
    # helper beside this managed component and the normal relative import wins.
    _model_path = Path(__file__).with_name("plugins_ad5x_ifs_model.py")
    _model_spec = importlib.util.spec_from_file_location(
        "moonraker.components.plugins_ad5x_ifs_model",
        _model_path,
    )
    if _model_spec is None or _model_spec.loader is None:
        raise
    _model_module = importlib.util.module_from_spec(_model_spec)
    _model_spec.loader.exec_module(_model_module)
    IFS_SCHEMA_VERSION = _model_module.IFS_SCHEMA_VERSION
    build_job_launch_gate = _model_module.build_job_launch_gate
    build_job_mapping_draft = _model_module.build_job_mapping_draft
    build_job_preview_token = _model_module.build_job_preview_token
    build_preprint_plan = _model_module.build_preprint_plan
    normalize_appearance = _model_module.normalize_appearance
    normalize_module = _model_module.normalize_module
    normalize_spool_metadata = _model_module.normalize_spool_metadata

try:
    from .plugins_ad5x_ifs_interop import (
        ORCA_LANE_NAMESPACE,
        build_orca_lane_data_projection,
        get_architecture_profile,
        summarize_orca_projection,
    )
except ImportError:
    _interop_path = Path(__file__).with_name("plugins_ad5x_ifs_interop.py")
    _interop_spec = importlib.util.spec_from_file_location(
        "moonraker.components.plugins_ad5x_ifs_interop",
        _interop_path,
    )
    if _interop_spec is None or _interop_spec.loader is None:
        raise
    _interop_module = importlib.util.module_from_spec(_interop_spec)
    _interop_spec.loader.exec_module(_interop_module)
    ORCA_LANE_NAMESPACE = _interop_module.ORCA_LANE_NAMESPACE
    build_orca_lane_data_projection = _interop_module.build_orca_lane_data_projection
    get_architecture_profile = _interop_module.get_architecture_profile
    summarize_orca_projection = _interop_module.summarize_orca_projection

try:
    from .plugins_ad5x_ifs_spoolman import (
        fallback_filter_library,
        merge_spoolman_binding,
        normalize_spoolman_spool,
        spoolman_binding_id,
        summarize_bindings,
        unbind_spoolman_record,
    )
except ImportError:
    _spoolman_path = Path(__file__).with_name("plugins_ad5x_ifs_spoolman.py")
    _spoolman_spec = importlib.util.spec_from_file_location(
        "moonraker.components.plugins_ad5x_ifs_spoolman", _spoolman_path
    )
    if _spoolman_spec is None or _spoolman_spec.loader is None:
        raise
    _spoolman_module = importlib.util.module_from_spec(_spoolman_spec)
    _spoolman_spec.loader.exec_module(_spoolman_module)
    fallback_filter_library = _spoolman_module.fallback_filter_library
    merge_spoolman_binding = _spoolman_module.merge_spoolman_binding
    normalize_spoolman_spool = _spoolman_module.normalize_spoolman_spool
    spoolman_binding_id = _spoolman_module.spoolman_binding_id
    summarize_bindings = _spoolman_module.summarize_bindings
    unbind_spoolman_record = _spoolman_module.unbind_spoolman_record

API_VERSION = "1.0"
BACKEND_VERSION = "0.2.0"

SNAPSHOT_ENDPOINT = "/server/plugins_ad5x/snapshot"
IFS_ACTION_ENDPOINT = "/server/plugins_ad5x/ifs/action"
IFS_METADATA_ENDPOINT = "/server/plugins_ad5x/ifs/metadata"
IFS_PROVIDER_IDENTITY_ENDPOINT = "/server/plugins_ad5x/ifs/provider/identity"
IFS_JOB_PREVIEW_ENDPOINT = "/server/plugins_ad5x/ifs/job/preview"
IFS_JOB_MAPPING_DRAFT_ENDPOINT = "/server/plugins_ad5x/ifs/job/mapping/draft"
IFS_JOB_LAUNCH_PREPARE_ENDPOINT = "/server/plugins_ad5x/ifs/job/launch/prepare"
IFS_SPOOLMAN_STATUS_ENDPOINT = "/server/plugins_ad5x/ifs/spoolman/status"
IFS_SPOOLMAN_LIBRARY_ENDPOINT = "/server/plugins_ad5x/ifs/spoolman/library"
IFS_SPOOLMAN_BIND_ENDPOINT = "/server/plugins_ad5x/ifs/spoolman/bind"
IFS_SPOOLMAN_UNBIND_ENDPOINT = "/server/plugins_ad5x/ifs/spoolman/unbind"
IFS_SPOOLMAN_REFRESH_ENDPOINT = "/server/plugins_ad5x/ifs/spoolman/refresh"
SNAPSHOT_CHANGED_EVENT = "plugins_ad5x:snapshot_changed"
SNAPSHOT_CHANGED_NOTIFY_NAME = "plugins_ad5x_snapshot_changed"
IFS_OBJECT = "ad5x_ifs"
PRINT_STATS_OBJECT = "print_stats"
HEAD_SENSOR_OBJECT = "filament_switch_sensor head_switch_sensor"
SAVE_VARIABLES_OBJECT = "save_variables"

FFCONFIG_PATH = "/usr/prog/config/Adventurer5M.json"
FILE_MAPPING_PATH = "/usr/data/config/mod_data/file.json"
IFS_METADATA_STORE_PATH = "/opt/config/mod_data/ad5x_custom/ifs_metadata.json"
IFS_METADATA_STORE_MAX_BYTES = 64 * 1024
IFS_PROVIDER_IDENTITY_HARDWARE_ACCEPTED = False

SAFE_FILAMENT_OP_PRINT_STATES = {"standby", "complete", "cancelled", "error"}
SAFE_JOB_PREVIEW_PRINT_STATES = {"standby", "complete", "cancelled", "error"}
IFS_JOB_PREVIEW_COMMAND = "ADIFS_JOB_PREVIEW"
IFS_ACTION_COMMANDS = {
    "select_slot": "SET_EXTRUDER_SLOT SLOT={slot}",
    # Z-Mod's public IFS UI uses IN_ZCOLOR as the provider-level load/unload wrapper.
    "load_slot": "IN_ZCOLOR SLOT={slot} NAPR=0",
    "unload_slot": "IN_ZCOLOR SLOT={slot} NAPR=1",
}


class PluginsAD5X:
    def __init__(self, config: Any) -> None:
        self.server = config.get_server()
        self._revision = 1
        self._ifs_raw: Dict[str, Any] = {}
        self._ifs_metadata: Dict[str, Any] = {}
        self._ifs_module = None
        self._print_state = "unknown"
        self._head_filament = None
        self._provider_print_leveling = None
        self._operation_state = "idle"
        self._operation_action = ""
        self._operation_slot = 0
        self._operation_error = ""
        self._metadata_store_status = self._store_status("missing")
        self._metadata_write_lock = asyncio.Lock()
        self._database = None
        self._spoolman = None
        self._spoolman_error = ""
        self._spoolman_tracking_slot = 0
        self._spoolman_tracking_spool_id = None
        self._last_orca_lane_fingerprint = ""
        self._orca_lane_status = self._new_orca_lane_status(False, "unavailable")
        self._lookup_database_component()

        self.server.register_endpoint(
            SNAPSHOT_ENDPOINT,
            RequestType.GET,
            self._handle_snapshot,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_endpoint(
            IFS_ACTION_ENDPOINT,
            RequestType.POST,
            self._handle_ifs_action,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_endpoint(
            IFS_METADATA_ENDPOINT,
            RequestType.POST,
            self._handle_ifs_metadata,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_endpoint(
            IFS_PROVIDER_IDENTITY_ENDPOINT,
            RequestType.POST,
            self._handle_ifs_provider_identity,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_endpoint(
            IFS_JOB_PREVIEW_ENDPOINT,
            RequestType.POST,
            self._handle_ifs_job_preview,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_endpoint(
            IFS_JOB_MAPPING_DRAFT_ENDPOINT,
            RequestType.POST,
            self._handle_ifs_job_mapping_draft,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        self.server.register_endpoint(
            IFS_JOB_LAUNCH_PREPARE_ENDPOINT,
            RequestType.POST,
            self._handle_ifs_job_launch_prepare,
            transports=TransportType.HTTP | TransportType.WEBSOCKET,
            auth_required=True,
        )
        for endpoint, request_type, handler in (
            (IFS_SPOOLMAN_STATUS_ENDPOINT, RequestType.GET, self._handle_spoolman_status),
            (IFS_SPOOLMAN_LIBRARY_ENDPOINT, RequestType.GET, self._handle_spoolman_library),
            (IFS_SPOOLMAN_BIND_ENDPOINT, RequestType.POST, self._handle_spoolman_bind),
            (IFS_SPOOLMAN_UNBIND_ENDPOINT, RequestType.POST, self._handle_spoolman_unbind),
            (IFS_SPOOLMAN_REFRESH_ENDPOINT, RequestType.POST, self._handle_spoolman_refresh),
        ):
            self.server.register_endpoint(
                endpoint,
                request_type,
                handler,
                transports=TransportType.HTTP | TransportType.WEBSOCKET,
                auth_required=True,
            )

        self.server.register_notification(
            SNAPSHOT_CHANGED_EVENT,
            SNAPSHOT_CHANGED_NOTIFY_NAME,
        )

        # Keep the foundation component importable/testable without Klipper.
        # Real Moonraker provides event handlers; hardware discovery happens only
        # after Klippy reports ready and never blocks component construction.
        if hasattr(self.server, "register_event_handler"):
            self.server.register_event_handler("server:klippy_ready", self._on_klippy_ready)
            self.server.register_event_handler(
                "server:klippy_disconnect", self._on_klippy_disconnect
            )
            self.server.register_event_handler(
                "spoolman:spoolman_status_changed", self._on_spoolman_event
            )
            self.server.register_event_handler(
                "spoolman:active_spool_set", self._on_spoolman_event
            )

    @staticmethod
    def _store_status(status: str, error: str = "") -> Dict[str, Any]:
        return {
            "status": status,
            "schema_version": IFS_SCHEMA_VERSION,
            "error": error,
        }

    @staticmethod
    def _new_orca_lane_status(enabled: bool, state: str, error: str = "") -> Dict[str, Any]:
        return {
            "namespace": ORCA_LANE_NAMESPACE,
            "enabled": enabled,
            "direction": "printer_to_orca",
            "publishable": False,
            "record_count": 0,
            "conflicts": [],
            "fingerprint": "",
            "requires_moonraker_agent": True,
            "target_version": "2.4.2",
            "state": state,
            "error": error,
        }

    def _lookup_database_component(self) -> Any:
        if self._database is not None:
            return self._database
        try:
            self._database = self.server.lookup_component("database")
        except Exception:
            self._database = None
        if self._database is not None and not self._orca_lane_status.get("enabled", False):
            self._orca_lane_status = self._new_orca_lane_status(True, "idle")
        return self._database

    def _lookup_spoolman_component(self) -> Any:
        if self._spoolman is not None:
            return self._spoolman
        try:
            self._spoolman = self.server.lookup_component("spoolman")
        except Exception:
            self._spoolman = None
        return self._spoolman

    def _spoolman_connected(self) -> bool:
        component = self._lookup_spoolman_component()
        if component is None:
            return False
        try:
            return bool(component.connected())
        except Exception:
            return bool(getattr(component, "ws_connected", False))

    def _spoolman_status(self, module: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        component = self._lookup_spoolman_component()
        module = module if isinstance(module, dict) else {}
        slots = module.get("slots") if isinstance(module.get("slots"), list) else []
        bindings = summarize_bindings(slots)
        active_spool_id = getattr(component, "spool_id", None) if component is not None else None
        expected_slot = 0
        expected_spool_id = None
        if self._head_filament is True:
            active_slot = module.get("active_slot")
            if isinstance(active_slot, int) and not isinstance(active_slot, bool):
                for slot in slots:
                    if isinstance(slot, dict) and slot.get("slot") == active_slot:
                        expected_slot = active_slot
                        expected_spool_id = spoolman_binding_id(slot)
                        break
        return {
            "configured": component is not None,
            "connected": self._spoolman_connected(),
            "library_available": component is not None and self._spoolman_connected(),
            "binding_supported": component is not None,
            "consumption_tracking_supported": bool(
                component is not None and hasattr(component, "set_active_spool")
            ),
            "active_spool_id": active_spool_id,
            "expected_active_spool_id": expected_spool_id,
            "expected_active_slot": expected_slot,
            "tracking_slot": self._spoolman_tracking_slot,
            "tracking_spool_id": self._spoolman_tracking_spool_id,
            "bindings": bindings,
            "error": self._spoolman_error,
        }

    async def _spoolman_request(self, path: str) -> Any:
        component = self._lookup_spoolman_component()
        if component is None:
            raise RuntimeError("Spoolman is not configured in Moonraker")
        if not self._spoolman_connected():
            raise RuntimeError("Spoolman is not connected")
        if not path.startswith("/v1/"):
            raise RuntimeError("Invalid Spoolman API path")
        http_client = getattr(component, "http_client", None)
        base_url = getattr(component, "spoolman_url", "")
        if http_client is None or not isinstance(base_url, str) or not base_url:
            raise RuntimeError("Moonraker Spoolman transport is unavailable")
        response = await http_client.request(method="GET", url=f"{base_url}{path}")
        if response.has_error():
            status = getattr(response, "status_code", 500)
            error = str(getattr(response, "error", "") or "Spoolman request failed")
            raise RuntimeError(f"Spoolman HTTP {status}: {error}")
        return response.json()

    async def component_init(self) -> None:
        # Components may load after __init__; resolve optional Spoolman only when
        # Moonraker has completed component construction.
        self._lookup_spoolman_component()

    async def _on_spoolman_event(self, *args: Any) -> None:
        if self._ifs_raw:
            await self._sync_spoolman_active_tracking(self._ifs_module)
            self._set_ifs_module(self._compose_ifs_module())

    async def _sync_spoolman_active_tracking(
        self, module: Optional[Dict[str, Any]] = None
    ) -> None:
        component = self._lookup_spoolman_component()
        if component is None or not hasattr(component, "set_active_spool"):
            return
        module = module if isinstance(module, dict) else self._ifs_module
        module = module if isinstance(module, dict) else {}
        desired_spool_id = None
        desired_slot = 0
        if module.get("available", False) and self._head_filament is True:
            active_slot = module.get("active_slot")
            slots = module.get("slots") if isinstance(module.get("slots"), list) else []
            if isinstance(active_slot, int) and not isinstance(active_slot, bool):
                for slot in slots:
                    if isinstance(slot, dict) and slot.get("slot") == active_slot:
                        desired_spool_id = spoolman_binding_id(slot)
                        desired_slot = active_slot if desired_spool_id is not None else 0
                        break
        try:
            if getattr(component, "spool_id", None) != desired_spool_id:
                # Z-Mod Moonraker already owns extrusion accounting. We only
                # select which bound physical IFS spool receives that accounting.
                component.set_active_spool(desired_spool_id)
            self._spoolman_tracking_spool_id = desired_spool_id
            self._spoolman_tracking_slot = desired_slot
            self._spoolman_error = ""
        except Exception as exc:
            self._spoolman_error = (str(exc) or exc.__class__.__name__)[:240]
        if self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())

    @staticmethod
    def _empty_manual_store() -> Dict[str, Any]:
        return {
            "schema_version": IFS_SCHEMA_VERSION,
            "slots": {},
            "identity_invalidated_slots": [],
        }

    def _decorate_ifs_module(self, module: Dict[str, Any]) -> Dict[str, Any]:
        profile = get_architecture_profile()
        module["architecture_version"] = profile["architecture_version"]
        module["ui"] = dict(profile["ui"])
        module["topology"] = dict(profile["topology"])
        interoperability = dict(profile["interoperability"])
        interoperability["orca_lane_data"] = dict(self._orca_lane_status)
        module["interoperability"] = interoperability
        spoolman_status = self._spoolman_status(module)
        module["spoolman"] = spoolman_status
        provider = module.get("provider")
        provider = dict(provider) if isinstance(provider, dict) else {"name": "zmod"}
        provider["settings"] = {"print_leveling": self._provider_print_leveling, "print_leveling_known": self._provider_print_leveling in (0, 1), "source": "save_variables", "read_only": True}
        module["provider"] = provider

        capabilities = module.get("capabilities")
        if isinstance(capabilities, dict):
            capabilities = dict(capabilities)
            integrations = capabilities.get("integrations")
            if isinstance(integrations, dict):
                integrations = dict(integrations)
                integrations["orca_slicer"] = True
                integrations["spoolman"] = bool(spoolman_status["configured"])
                capabilities["integrations"] = integrations
            metadata_caps = capabilities.get("metadata")
            if isinstance(metadata_caps, dict):
                metadata_caps = dict(metadata_caps)
                metadata_caps["spoolman"] = bool(spoolman_status["configured"])
                capabilities["metadata"] = metadata_caps
            capabilities["spoolman"] = {
                "optional": True,
                "configured": bool(spoolman_status["configured"]),
                "connected": bool(spoolman_status["connected"]),
                "browse_library": True,
                "bind_slot": True,
                "refresh_binding": True,
                "consumption_tracking": bool(
                    spoolman_status["consumption_tracking_supported"]
                ),
            }
            capabilities["ui_expertise"] = {
                "auto": True,
                "hybrid": True,
                "expert": True,
                "canonical": "expert",
            }
            capabilities["interoperability"] = {
                "orca_lane_data": True,
            }
            module["capabilities"] = capabilities
        return module

    def _unavailable_ifs(self, reason: str) -> Dict[str, Any]:
        raw = {
            "available": False,
            "reason": reason,
            "state": "unavailable",
            "state_code": 0,
            "active_slot": 0,
            "slots": [],
            "silk_mask": 0,
            "raw_channel": 0,
            "insert_slot": 0,
            "need_insert": False,
            "stall": False,
            "stall_mask": 0,
        }
        module = normalize_module(
            raw,
            self._ifs_metadata,
            self._print_state,
            self._head_filament,
            {
                "state": self._operation_state,
                "action": self._operation_action,
                "slot": self._operation_slot,
                "error": self._operation_error,
            },
        )
        module["metadata_store"] = dict(self._metadata_store_status)
        return self._decorate_ifs_module(module)

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "api_version": API_VERSION,
            "backend_version": BACKEND_VERSION,
            "revision": self._revision,
            "backend": {
                "health": "ok",
            },
            "modules": (
                {} if self._ifs_module is None else {"ifs": dict(self._ifs_module)}
            ),
        }

    async def _handle_snapshot(self, _web_request: Any) -> Dict[str, Any]:
        # Persistent metadata sources are tiny but live outside Moonraker
        # ownership. Refresh them on demand instead of adding a polling loop.
        await self._refresh_ifs_metadata()
        return self.get_snapshot()

    def invalidate_snapshot(self) -> int:
        self._revision += 1
        self.server.send_event(
            SNAPSHOT_CHANGED_EVENT,
            {"revision": self._revision},
        )
        return self._revision

    def _set_ifs_module(self, module: Dict[str, Any]) -> bool:
        normalized = dict(module)
        if self._ifs_module is not None and normalized == self._ifs_module:
            return False
        self._ifs_module = normalized
        self.invalidate_snapshot()
        return True

    def _set_orca_lane_status(self, status: Dict[str, Any]) -> bool:
        normalized = dict(status)
        if normalized == self._orca_lane_status:
            return False
        self._orca_lane_status = normalized
        if self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())
        elif self._ifs_module is not None:
            module = dict(self._ifs_module)
            interoperability = module.get("interoperability")
            interoperability = dict(interoperability) if isinstance(interoperability, dict) else {}
            interoperability["orca_lane_data"] = dict(self._orca_lane_status)
            module["interoperability"] = interoperability
            self._set_ifs_module(module)
        return True

    async def _publish_orca_lane_data(self, module: Dict[str, Any]) -> None:
        if not isinstance(module, dict) or not module.get("available", False):
            return
        database = self._lookup_database_component()
        if database is None:
            self._set_orca_lane_status(
                self._new_orca_lane_status(False, "unavailable", "moonraker_database_unavailable")
            )
            return

        slots = module.get("slots")
        slots = slots if isinstance(slots, list) else []
        try:
            existing = await database.get_item(ORCA_LANE_NAMESPACE, default={})
            existing = existing if isinstance(existing, dict) else {}
            projection = build_orca_lane_data_projection(slots, existing)
            summary = summarize_orca_projection(projection)
            summary["state"] = "ready"
            summary["error"] = ""

            if not projection.get("publishable", False):
                summary["state"] = "conflict"
                summary["error"] = "duplicate_lane_record"
                self._set_orca_lane_status(summary)
                return

            fingerprint = summary.get("fingerprint", "")
            if fingerprint and fingerprint == self._last_orca_lane_fingerprint:
                summary["state"] = "in_sync"
                self._set_orca_lane_status(summary)
                return

            records = projection.get("records")
            records = records if isinstance(records, dict) else {}
            await database.insert_batch(ORCA_LANE_NAMESPACE, records)
            self._last_orca_lane_fingerprint = fingerprint
            summary["state"] = "published"
            self._set_orca_lane_status(summary)
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            if len(error) > 240:
                error = error[:240]
            status = dict(self._orca_lane_status)
            status.update(
                {
                    "enabled": True,
                    "state": "error",
                    "error": error,
                }
            )
            self._set_orca_lane_status(status)

    def _compose_ifs_module(self) -> Dict[str, Any]:
        module = normalize_module(
            self._ifs_raw,
            self._ifs_metadata,
            self._print_state,
            self._head_filament,
            {
                "state": self._operation_state,
                "action": self._operation_action,
                "slot": self._operation_slot,
                "error": self._operation_error,
            },
        )
        module["metadata_store"] = dict(self._metadata_store_status)
        return self._decorate_ifs_module(module)

    def _apply_ifs_status(self, payload: Dict[str, Any]) -> bool:
        # Klipper subscriptions may deliver partial object updates. Merge into
        # the last complete state before publishing the canonical module.
        self._ifs_raw.update(payload)
        return self._set_ifs_module(self._compose_ifs_module())

    def _apply_aux_status(self, status: Dict[str, Any]) -> bool:
        changed = False
        print_stats = status.get(PRINT_STATS_OBJECT)
        if isinstance(print_stats, dict):
            state = print_stats.get("state")
            if isinstance(state, str) and state and state != self._print_state:
                self._print_state = state
                changed = True

        head = status.get(HEAD_SENSOR_OBJECT)
        if isinstance(head, dict):
            enabled = head.get("enabled", True)
            detected = head.get("filament_detected")
            normalized = bool(detected) if enabled and isinstance(detected, bool) else None
            if normalized != self._head_filament:
                self._head_filament = normalized
                changed = True

        save_variables = status.get(SAVE_VARIABLES_OBJECT)
        if isinstance(save_variables, dict):
            variables = save_variables.get("variables")
            variables = variables if isinstance(variables, dict) else {}
            raw_leveling = variables.get("print_leveling")
            normalized_leveling = raw_leveling if isinstance(raw_leveling, int) and not isinstance(raw_leveling, bool) and raw_leveling in (0, 1) else None
            if normalized_leveling != self._provider_print_leveling:
                self._provider_print_leveling = normalized_leveling
                changed = True
        return changed

    @staticmethod
    def _read_json(path: str) -> Any:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    @staticmethod
    def _manual_record_has_metadata(record: Dict[str, Any]) -> bool:
        spool = record.get("spool") if isinstance(record.get("spool"), dict) else {}
        appearance = (
            record.get("appearance")
            if isinstance(record.get("appearance"), dict)
            else {}
        )
        return bool(
            spool.get("brand")
            or spool.get("series")
            or spool.get("name")
            or spool.get("material")
            or spool.get("variant")
            or spool.get("spoolman_id")
            or spool.get("remaining_g") is not None
            or appearance.get("colors")
            or appearance.get("finish") not in (None, "", "standard")
        )

    @staticmethod
    def _normalize_manual_record(
        spool: Dict[str, Any], appearance: Dict[str, Any]
    ) -> Dict[str, Any]:
        normalized_spool = normalize_spool_metadata(spool)
        normalized_spool["source"] = "manual"
        normalized_appearance = normalize_appearance(None, appearance)
        return {
            "spool": normalized_spool,
            "appearance": normalized_appearance,
        }

    def _read_manual_metadata_store_sync(
        self,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        path = Path(IFS_METADATA_STORE_PATH)
        if not path.exists():
            return self._empty_manual_store(), self._store_status("missing")
        if not path.is_file() or path.is_symlink():
            return self._empty_manual_store(), self._store_status("invalid", "not_regular_file")
        try:
            if path.stat().st_size > IFS_METADATA_STORE_MAX_BYTES:
                return self._empty_manual_store(), self._store_status("invalid", "too_large")
            payload = self._read_json(str(path))
        except json.JSONDecodeError:
            return self._empty_manual_store(), self._store_status("invalid", "invalid_json")
        except OSError:
            return self._empty_manual_store(), self._store_status("invalid", "read_error")

        if not isinstance(payload, dict):
            return self._empty_manual_store(), self._store_status("invalid", "invalid_root")
        if payload.get("schema_version") != IFS_SCHEMA_VERSION:
            return self._empty_manual_store(), self._store_status("invalid", "unsupported_schema")
        raw_slots = payload.get("slots", {})
        if not isinstance(raw_slots, dict):
            return self._empty_manual_store(), self._store_status("invalid", "invalid_slots")
        raw_invalidated = payload.get("identity_invalidated_slots", [])
        if not isinstance(raw_invalidated, list):
            return self._empty_manual_store(), self._store_status("invalid", "invalid_identity_invalidated_slots")
        invalidated_slots: List[int] = []
        for value in raw_invalidated:
            if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 4:
                return self._empty_manual_store(), self._store_status("invalid", "invalid_identity_invalidated_slot")
            if value not in invalidated_slots:
                invalidated_slots.append(value)
        invalidated_slots.sort()

        slots: Dict[str, Dict[str, Any]] = {}
        for raw_slot, raw_record in raw_slots.items():
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError):
                return self._empty_manual_store(), self._store_status("invalid", "invalid_slot_key")
            if slot < 1 or slot > 4 or not isinstance(raw_record, dict):
                return self._empty_manual_store(), self._store_status("invalid", "invalid_slot_record")
            spool = raw_record.get("spool", {})
            appearance = raw_record.get("appearance", {})
            if not isinstance(spool, dict) or not isinstance(appearance, dict):
                return self._empty_manual_store(), self._store_status("invalid", "invalid_slot_record")
            normalized_spool = normalize_spool_metadata(spool)
            if normalized_spool.get("source") == "unknown":
                normalized_spool["source"] = "manual"
            slots[str(slot)] = {
                "spool": normalized_spool,
                "appearance": normalize_appearance(None, appearance),
            }

        return {
            "schema_version": IFS_SCHEMA_VERSION,
            "slots": slots,
            "identity_invalidated_slots": invalidated_slots,
        }, self._store_status("ok")

    def _write_manual_metadata_store_sync(self, store: Dict[str, Any]) -> None:
        path = Path(IFS_METADATA_STORE_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            store,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
        encoded = payload.encode("utf-8")
        if len(encoded) > IFS_METADATA_STORE_MAX_BYTES:
            raise ValueError("metadata store exceeds size limit")

        tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
        try:
            with open(tmp, "w", encoding="utf-8", newline="\n") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(tmp, 0o644)
            os.replace(tmp, path)
            try:
                directory_fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY)
            except OSError:
                directory_fd = -1
            if directory_fd >= 0:
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        finally:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass

    @staticmethod
    def _overlay_manual_metadata(
        metadata: Dict[str, Any], manual_store: Dict[str, Any]
    ) -> None:
        raw_slots = manual_store.get("slots", {})
        if not isinstance(raw_slots, dict) or not raw_slots:
            return
        slots = metadata.setdefault("slots", {})
        if not isinstance(slots, dict):
            slots = {}
            metadata["slots"] = slots

        for raw_slot, record in raw_slots.items():
            if not isinstance(record, dict):
                continue
            try:
                slot = int(raw_slot)
            except (TypeError, ValueError):
                continue
            current = dict(slots.get(slot, {})) if isinstance(slots.get(slot), dict) else {}
            spool = record.get("spool") if isinstance(record.get("spool"), dict) else {}
            appearance = (
                record.get("appearance")
                if isinstance(record.get("appearance"), dict)
                else {}
            )
            current["spool"] = dict(spool)
            current["appearance"] = dict(appearance)
            material = spool.get("material")
            if isinstance(material, str) and material:
                # Keep old frontend flat fields aligned with the effective manual overlay.
                current["material"] = material
            colors = appearance.get("colors")
            if isinstance(colors, list) and colors:
                current["color"] = colors[0]
            slots[slot] = current

    def _read_ifs_metadata_sync(
        self,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        metadata: Dict[str, Any] = {}

        try:
            ffconfig = self._read_json(FFCONFIG_PATH)
            ffm_info = ffconfig.get("FFMInfo", {}) if isinstance(ffconfig, dict) else {}
            if isinstance(ffm_info, dict):
                active_slot = int(ffm_info.get("channel", 0) or 0)
                if 1 <= active_slot <= 4:
                    metadata["active_slot"] = active_slot

                slots: Dict[int, Dict[str, Any]] = {}
                for slot in range(1, 5):
                    slot_data: Dict[str, Any] = {}
                    material = ffm_info.get(f"ffmType{slot}")
                    color = ffm_info.get(f"ffmColor{slot}")
                    if isinstance(material, str) and material:
                        slot_data["material"] = material
                    if isinstance(color, str) and color:
                        slot_data["color"] = color
                    zmod_compat: Dict[str, Any] = {}
                    if isinstance(material, str) and material:
                        zmod_compat["material"] = material
                    if isinstance(color, str) and color:
                        zmod_compat["color"] = color
                    if zmod_compat:
                        slot_data["zmod_compat"] = zmod_compat
                    if slot_data:
                        slots[slot] = slot_data
                if slots:
                    metadata["slots"] = slots
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            # Slot presence/state remains available from the Klipper bridge even
            # when persistent FlashForge metadata cannot be read.
            pass

        try:
            mapping = self._read_json(FILE_MAPPING_PATH)
            if (
                isinstance(mapping, list)
                and mapping
                and all(
                    isinstance(slot, int)
                    and not isinstance(slot, bool)
                    and 1 <= slot <= 4
                    for slot in mapping
                )
            ):
                metadata["tool_mapping"] = list(mapping)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

        manual_store, store_status = self._read_manual_metadata_store_sync()
        if store_status.get("status") != "invalid":
            self._overlay_manual_metadata(metadata, manual_store)
            invalidated = manual_store.get("identity_invalidated_slots", [])
            if isinstance(invalidated, list) and invalidated:
                metadata["identity_invalidated_slots"] = list(invalidated)
        return metadata, store_status

    async def _run_io(self, callback: Any, *args: Any) -> Any:
        try:
            event_loop = self.server.get_event_loop()
        except (AttributeError, TypeError):
            event_loop = None
        if event_loop is not None and hasattr(event_loop, "run_in_thread"):
            return await event_loop.run_in_thread(callback, *args)
        return callback(*args)

    @staticmethod
    def _slot_presence_map(raw_module: Dict[str, Any]) -> Dict[int, bool]:
        result: Dict[int, bool] = {}
        slots = raw_module.get("slots") if isinstance(raw_module, dict) else None
        for item in slots if isinstance(slots, list) else []:
            if not isinstance(item, dict):
                continue
            slot = item.get("slot")
            if isinstance(slot, int) and not isinstance(slot, bool) and 1 <= slot <= 4:
                result[slot] = bool(item.get("present", False))
        return result

    @staticmethod
    def _set_slot_identity_invalidated(store: Dict[str, Any], slot: int, value: bool) -> bool:
        raw = store.get("identity_invalidated_slots", [])
        current = {
            item for item in raw
            if isinstance(item, int) and not isinstance(item, bool) and 1 <= item <= 4
        } if isinstance(raw, list) else set()
        before = set(current)
        if value:
            current.add(slot)
        else:
            current.discard(slot)
        store["identity_invalidated_slots"] = sorted(current)
        return current != before

    async def _invalidate_removed_slot_identities(self, slots_to_clear: List[int]) -> bool:
        slots_to_clear = sorted({slot for slot in slots_to_clear if 1 <= slot <= 4})
        if not slots_to_clear:
            return False
        changed = False
        async with self._metadata_write_lock:
            store, status = await self._run_io(self._read_manual_metadata_store_sync)
            if status.get("status") == "invalid":
                self._metadata_store_status = status
                return False
            records = store.setdefault("slots", {})
            for slot in slots_to_clear:
                removed = records.pop(str(slot), None) is not None
                if removed:
                    changed = True
                    if self._set_slot_identity_invalidated(store, slot, True):
                        changed = True
            if changed:
                await self._run_io(self._write_manual_metadata_store_sync, store)
        if changed:
            await self._refresh_ifs_metadata()
        return changed

    async def _refresh_ifs_metadata(self) -> bool:
        metadata, store_status = await self._run_io(self._read_ifs_metadata_sync)
        metadata_changed = metadata != self._ifs_metadata
        status_changed = store_status != self._metadata_store_status
        if not metadata_changed and not status_changed:
            return False
        self._ifs_metadata = metadata
        self._metadata_store_status = store_status
        if self._ifs_raw:
            changed = self._set_ifs_module(self._compose_ifs_module())
            await self._publish_orca_lane_data(self._ifs_module or {})
            await self._sync_spoolman_active_tracking(self._ifs_module)
            return changed
        return False

    def _operation_begin(self, action: str, slot: int) -> None:
        self._operation_state = "running"
        self._operation_action = action
        self._operation_slot = slot
        self._operation_error = ""
        if self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())

    def _operation_end(self, error: str = "") -> None:
        self._operation_state = "idle"
        self._operation_action = ""
        self._operation_slot = 0
        self._operation_error = error
        if self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())

    def _action_rejection(self, action: str, slot: int, error: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "action": action,
            "slot": slot,
            "error": error,
            "snapshot": self.get_snapshot(),
        }

    def _metadata_rejection(self, slot: int, error: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "slot": slot,
            "error": error,
            "snapshot": self.get_snapshot(),
        }

    def _validate_ifs_action(self, action: str, slot: int) -> str:
        if action not in IFS_ACTION_COMMANDS:
            return f"Unsupported IFS action: {action}"
        if slot < 1 or slot > 4:
            return f"Invalid IFS slot: {slot}"
        module = self._ifs_module if isinstance(self._ifs_module, dict) else {}
        provider_mode = module.get("provider_mode")
        if provider_mode == "native_display":
            return "IFS Manager is suspended while the native display owns IFS"
        if provider_mode not in (None, "", "display_off"):
            return f"IFS provider mode is not supported: {provider_mode}"
        if not module.get("available", False):
            return "IFS is not available"
        if self._ifs_module.get("state") != "ready":
            return f"IFS is not ready: {self._ifs_module.get('state', 'unknown')}"
        if self._operation_state != "idle":
            return "Another IFS operation is already running"
        # Helix hardware research proved Z-Mod filament macros may self-home and
        # move the toolhead. Refuse writes not only while printing but also while
        # PAUSED; unknown/non-idle job states fail closed as well.
        if self._print_state not in SAFE_FILAMENT_OP_PRINT_STATES:
            return f"IFS operations are blocked while print state is {self._print_state}"

        slots = self._ifs_module.get("slots") or []
        slot_data = next(
            (
                item
                for item in slots
                if isinstance(item, dict) and item.get("slot") == slot
            ),
            {},
        )
        present = bool(slot_data.get("present", False))
        active_slot = int(self._ifs_module.get("active_slot") or 0)

        if action in ("select_slot", "load_slot") and not present:
            return f"IFS slot {slot} is empty"
        if action == "load_slot" and active_slot == slot and self._head_filament is True:
            return f"IFS slot {slot} is already loaded at the toolhead"
        if action == "unload_slot":
            if active_slot != slot:
                return "First normal implementation only unloads the active toolhead slot"
            if self._head_filament is not True:
                return "Toolhead filament presence is not confirmed; use Manage/recovery instead"
        return ""

    def _provider_identity_rejection(self, slot: int, error: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "slot": slot,
            "error": error,
            "hardware_accepted": IFS_PROVIDER_IDENTITY_HARDWARE_ACCEPTED,
            "snapshot": self.get_snapshot(),
        }

    def _validate_provider_identity(self, slot: int, material: str, color: str) -> str:
        if slot < 1 or slot > 4:
            return f"Invalid IFS slot: {slot}"
        module = self._ifs_module if isinstance(self._ifs_module, dict) else {}
        provider_mode = module.get("provider_mode")
        if provider_mode == "native_display":
            return "IFS Manager is suspended while the native display owns IFS"
        if provider_mode not in (None, "", "display_off"):
            return f"IFS provider mode is not supported: {provider_mode}"
        if not module.get("available", False) or module.get("state") != "ready":
            return "IFS is not ready"
        if self._operation_state != "idle":
            return "Another IFS operation is already running"
        if self._print_state not in SAFE_FILAMENT_OP_PRINT_STATES:
            return f"IFS provider identity write is blocked while print state is {self._print_state}"
        slots = module.get("slots") or []
        slot_data = next((item for item in slots if isinstance(item, dict) and item.get("slot") == slot), {})
        if not bool(slot_data.get("present", False)):
            return f"IFS slot {slot} is empty"
        provider_material_types = module.get("provider_material_types") or []
        valid_types = {
            value.strip().upper()
            for value in provider_material_types
            if isinstance(value, str) and value.strip() and value.strip() != "?"
        }
        if not valid_types:
            return "Provider-supported material identity is unknown"
        if not material or (valid_types and material not in valid_types):
            return f"Unsupported provider material: {material or 'empty'}"
        if len(color) != 7 or not color.startswith("#"):
            return "Provider color must be #RRGGBB"
        try:
            int(color[1:], 16)
        except ValueError:
            return "Provider color must be #RRGGBB"
        return ""

    async def _handle_ifs_provider_identity(self, web_request: Any) -> Dict[str, Any]:
        try:
            slot = web_request.get_int("slot")
            material = web_request.get_str("material").strip().upper()
            color = web_request.get_str("color").strip().upper()
        except Exception as exc:
            return self._provider_identity_rejection(0, f"Invalid provider identity request: {exc}")
        await self._refresh_ifs_metadata()
        rejection = self._validate_provider_identity(slot, material, color)
        if rejection:
            return self._provider_identity_rejection(slot, rejection)
        if not IFS_PROVIDER_IDENTITY_HARDWARE_ACCEPTED:
            return self._provider_identity_rejection(slot, "hardware_acceptance_required")
        command = f"CHANGE_ZCOLOR SLOT={slot} TYPE={material} HEX={color[1:]}"
        self._operation_begin("set_provider_identity", slot)
        try:
            klippy_apis = self.server.lookup_component("klippy_apis")
            result = await klippy_apis.run_gcode(command)
            self._operation_end()
            await self._refresh_ifs_metadata()
            return {"ok": True, "slot": slot, "material": material, "color": color, "result": result, "hardware_accepted": True, "snapshot": self.get_snapshot()}
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self._operation_end(error)
            return self._provider_identity_rejection(slot, error)

    async def _handle_ifs_metadata(self, web_request: Any) -> Dict[str, Any]:
        try:
            slot = web_request.get_int("slot")
            if slot < 1 or slot > 4:
                raise ValueError(f"Invalid IFS slot: {slot}")
            if hasattr(web_request, "get_boolean"):
                clear = web_request.get_boolean("clear", False)
            else:
                clear = bool(web_request.get("clear", False))
        except Exception as exc:
            return self._metadata_rejection(0, f"Invalid IFS metadata request: {exc}")

        record = None
        if not clear:
            try:
                spool = web_request.get("spool", {})
                appearance = web_request.get("appearance", {})
            except Exception as exc:
                return self._metadata_rejection(slot, f"Invalid IFS metadata request: {exc}")
            if not isinstance(spool, dict) or not isinstance(appearance, dict):
                return self._metadata_rejection(
                    slot, "spool and appearance must be JSON objects"
                )
            record = self._normalize_manual_record(spool, appearance)
            if not self._manual_record_has_metadata(record):
                return self._metadata_rejection(
                    slot, "manual metadata is empty; use clear=true to remove an assignment"
                )

        async with self._metadata_write_lock:
            store, status = await self._run_io(self._read_manual_metadata_store_sync)
            if status.get("status") == "invalid":
                return self._metadata_rejection(
                    slot,
                    f"manual metadata store is invalid: {status.get('error', 'unknown')}",
                )
            slots = store.setdefault("slots", {})
            slot_key = str(slot)
            if clear:
                removed = slots.pop(slot_key, None) is not None
                invalidated = self._set_slot_identity_invalidated(store, slot, True)
                if not removed and not invalidated:
                    await self._refresh_ifs_metadata()
                    return {
                        "ok": True,
                        "slot": slot,
                        "result": "already_clear",
                        "snapshot": self.get_snapshot(),
                    }
                result = "cleared"
            else:
                slots[slot_key] = record
                self._set_slot_identity_invalidated(store, slot, False)
                result = "updated"
            try:
                await self._run_io(self._write_manual_metadata_store_sync, store)
            except Exception as exc:
                return self._metadata_rejection(
                    slot, f"failed to persist manual metadata: {exc}"
                )

        await self._refresh_ifs_metadata()
        return {
            "ok": True,
            "slot": slot,
            "result": result,
            "snapshot": self.get_snapshot(),
        }

    async def _handle_spoolman_status(self, _web_request: Any) -> Dict[str, Any]:
        await self._refresh_ifs_metadata()
        module = self._ifs_module if isinstance(self._ifs_module, dict) else {}
        return {"ok": True, "spoolman": self._spoolman_status(module)}

    async def _spoolman_library_items(
        self, query: str, limit: int, allow_archived: bool
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        if query:
            try:
                params = urlencode({
                    "q": query,
                    "limit": limit,
                    "allow_archived": str(bool(allow_archived)).lower(),
                    "spools_per_filament": min(limit, 10),
                })
                payload = await self._spoolman_request(f"/v1/search?{params}")
                ids: List[int] = []
                for match in payload.get("spools", []) if isinstance(payload, dict) else []:
                    raw = match.get("spool") if isinstance(match, dict) else None
                    if isinstance(raw, dict) and isinstance(raw.get("id"), int):
                        ids.append(raw["id"])
                for match in payload.get("filaments", []) if isinstance(payload, dict) else []:
                    for ref in match.get("spools", []) if isinstance(match, dict) else []:
                        if isinstance(ref, dict) and isinstance(ref.get("id"), int):
                            ids.append(ref["id"])
                result = []
                for spool_id in list(dict.fromkeys(ids))[:limit]:
                    raw = await self._spoolman_request(f"/v1/spool/{spool_id}")
                    if isinstance(raw, dict):
                        result.append(normalize_spoolman_spool(raw))
                if result:
                    return result
            except Exception:
                # Older Spoolman versions do not have /v1/search. Fall back to
                # the stable spool list and local bounded matching.
                pass
        params = urlencode({"allow_archived": str(bool(allow_archived)).lower()})
        payload = await self._spoolman_request(f"/v1/spool?{params}")
        return fallback_filter_library(payload, query, limit)

    async def _handle_spoolman_library(self, web_request: Any) -> Dict[str, Any]:
        try:
            query = web_request.get_str("q", "").strip()
            limit = web_request.get_int("limit", 20)
            allow_archived = web_request.get_boolean("allow_archived", False)
            items = await self._spoolman_library_items(query, limit, allow_archived)
            self._spoolman_error = ""
            return {"ok": True, "query": query, "items": items, "count": len(items)}
        except Exception as exc:
            self._spoolman_error = (str(exc) or exc.__class__.__name__)[:240]
            return {"ok": False, "error": self._spoolman_error, "items": []}

    async def _persist_spoolman_binding(
        self, slot: int, normalized: Dict[str, Any]
    ) -> None:
        async with self._metadata_write_lock:
            store, status = await self._run_io(self._read_manual_metadata_store_sync)
            if status.get("status") == "invalid":
                raise RuntimeError(
                    f"metadata store is invalid: {status.get('error', 'unknown')}"
                )
            slots = store.setdefault("slots", {})
            key = str(slot)
            existing = slots.get(key) if isinstance(slots.get(key), dict) else {}
            slots[key] = merge_spoolman_binding(existing, normalized)
            self._set_slot_identity_invalidated(store, slot, False)
            await self._run_io(self._write_manual_metadata_store_sync, store)
        await self._refresh_ifs_metadata()
        await self._sync_spoolman_active_tracking(self._ifs_module)

    async def _handle_spoolman_bind(self, web_request: Any) -> Dict[str, Any]:
        try:
            slot = web_request.get_int("slot")
            spool_id = web_request.get_int("spool_id")
            allow_archived = web_request.get_boolean("allow_archived", False)
            if slot < 1 or slot > 4 or spool_id <= 0:
                raise ValueError("invalid slot or spool_id")
            raw = await self._spoolman_request(f"/v1/spool/{spool_id}")
            normalized = normalize_spoolman_spool(raw)
            if normalized.get("spoolman_spool_id") != spool_id:
                raise RuntimeError("Spoolman returned an unexpected spool id")
            inventory = normalized.get("inventory")
            if (
                isinstance(inventory, dict)
                and inventory.get("archived", False)
                and not allow_archived
            ):
                raise RuntimeError("Archived Spoolman spool requires allow_archived=true")
            await self._persist_spoolman_binding(slot, normalized)
            self._spoolman_error = ""
            return {
                "ok": True,
                "slot": slot,
                "spool_id": spool_id,
                "binding": normalized,
                "snapshot": self.get_snapshot(),
            }
        except Exception as exc:
            error = (str(exc) or exc.__class__.__name__)[:240]
            self._spoolman_error = error
            return {
                "ok": False,
                "error": error,
                "snapshot": self.get_snapshot(),
            }

    async def _handle_spoolman_unbind(self, web_request: Any) -> Dict[str, Any]:
        try:
            slot = web_request.get_int("slot")
            keep_metadata = web_request.get_boolean("keep_metadata", True)
            if slot < 1 or slot > 4:
                raise ValueError("invalid slot")
            async with self._metadata_write_lock:
                store, status = await self._run_io(self._read_manual_metadata_store_sync)
                if status.get("status") == "invalid":
                    raise RuntimeError(
                        f"metadata store is invalid: {status.get('error', 'unknown')}"
                    )
                slots = store.setdefault("slots", {})
                key = str(slot)
                existing = slots.get(key) if isinstance(slots.get(key), dict) else None
                if existing is None:
                    result = "already_unbound"
                else:
                    spool = existing.get("spool") if isinstance(existing, dict) else {}
                    bound = isinstance(spool, dict) and bool(
                        spool.get("spoolman_spool_id") or spool.get("spoolman_id")
                    )
                    if not bound:
                        result = "already_unbound"
                    else:
                        replacement = unbind_spoolman_record(existing, keep_metadata)
                        if replacement is None:
                            slots.pop(key, None)
                        else:
                            slots[key] = replacement
                        self._set_slot_identity_invalidated(store, slot, True)
                        await self._run_io(self._write_manual_metadata_store_sync, store)
                        result = "unbound"
            await self._refresh_ifs_metadata()
            await self._sync_spoolman_active_tracking(self._ifs_module)
            self._spoolman_error = ""
            return {
                "ok": True,
                "slot": slot,
                "result": result,
                "snapshot": self.get_snapshot(),
            }
        except Exception as exc:
            error = (str(exc) or exc.__class__.__name__)[:240]
            self._spoolman_error = error
            return {"ok": False, "error": error, "snapshot": self.get_snapshot()}

    async def _refresh_spoolman_bindings(self, slot_filter: int = 0) -> Dict[str, Any]:
        updated = 0
        errors: List[Dict[str, Any]] = []
        async with self._metadata_write_lock:
            store, status = await self._run_io(self._read_manual_metadata_store_sync)
            if status.get("status") == "invalid":
                raise RuntimeError(
                    f"metadata store is invalid: {status.get('error', 'unknown')}"
                )
            slots = store.setdefault("slots", {})
            changed = False
            for raw_slot, record in list(slots.items()):
                try:
                    slot = int(raw_slot)
                except (TypeError, ValueError):
                    continue
                if slot_filter and slot != slot_filter:
                    continue
                spool = record.get("spool") if isinstance(record, dict) else {}
                if not isinstance(spool, dict):
                    continue
                spool_id = spool.get("spoolman_spool_id") or spool.get("spoolman_id")
                if isinstance(spool_id, bool) or not isinstance(spool_id, int) or spool_id <= 0:
                    continue
                try:
                    raw = await self._spoolman_request(f"/v1/spool/{spool_id}")
                    normalized = normalize_spoolman_spool(raw)
                    merged = merge_spoolman_binding(record, normalized)
                    if merged != record:
                        slots[raw_slot] = merged
                        changed = True
                        updated += 1
                except Exception as exc:
                    errors.append({
                        "slot": slot,
                        "spool_id": spool_id,
                        "error": (str(exc) or exc.__class__.__name__)[:240],
                    })
            if changed:
                await self._run_io(self._write_manual_metadata_store_sync, store)
        await self._refresh_ifs_metadata()
        await self._sync_spoolman_active_tracking(self._ifs_module)
        return {"updated": updated, "errors": errors}

    async def _handle_spoolman_refresh(self, web_request: Any) -> Dict[str, Any]:
        try:
            slot = web_request.get_int("slot", 0)
            if slot < 0 or slot > 4:
                raise ValueError("invalid slot")
            result = await self._refresh_spoolman_bindings(slot)
            self._spoolman_error = result["errors"][0]["error"] if result["errors"] else ""
            return {
                "ok": not bool(result["errors"]),
                "slot": slot,
                **result,
                "snapshot": self.get_snapshot(),
            }
        except Exception as exc:
            error = (str(exc) or exc.__class__.__name__)[:240]
            self._spoolman_error = error
            return {"ok": False, "error": error, "snapshot": self.get_snapshot()}

    @staticmethod
    def _job_preview_rejection(filename: str, error: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "filename": filename,
            "error": error,
        }

    @staticmethod
    def _job_preview_filename_valid(filename: str) -> bool:
        if not isinstance(filename, str):
            return False
        filename = filename.strip()
        if (
            not filename
            or filename.startswith("/")
            or "\x00" in filename
            or '"' in filename
            or "\n" in filename
            or "\r" in filename
        ):
            return False
        parts = filename.replace("\\", "/").split("/")
        return all(part not in ("", "..") for part in parts)

    async def _handle_ifs_job_preview(self, web_request: Any) -> Dict[str, Any]:
        try:
            filename = web_request.get_str("filename").strip()
        except Exception as exc:
            return self._job_preview_rejection(
                "", f"Invalid IFS job preview request: {exc}"
            )

        if not self._job_preview_filename_valid(filename):
            return self._job_preview_rejection(filename, "Invalid IFS job preview filename")
        module = self._ifs_module if isinstance(self._ifs_module, dict) else {}
        provider_mode = module.get("provider_mode")
        if provider_mode == "native_display":
            return self._job_preview_rejection(
                filename, "IFS Manager is suspended while the native display owns IFS"
            )
        if provider_mode not in (None, "", "display_off"):
            return self._job_preview_rejection(
                filename, f"IFS provider mode is not supported: {provider_mode}"
            )
        if not module.get("available", False):
            return self._job_preview_rejection(filename, "IFS bridge is not available")
        if self._operation_state != "idle":
            return self._job_preview_rejection(
                filename, "IFS operation is already running"
            )
        if self._print_state not in SAFE_JOB_PREVIEW_PRINT_STATES:
            return self._job_preview_rejection(
                filename,
                f"IFS job preview is blocked while print state is {self._print_state}",
            )

        command = f'{IFS_JOB_PREVIEW_COMMAND} FILENAME="{filename}"'
        try:
            klippy_apis = self.server.lookup_component("klippy_apis")
            await klippy_apis.run_gcode(command)
            status = await klippy_apis.query_objects({IFS_OBJECT: None}, default={})
        except Exception as exc:
            return self._job_preview_rejection(
                filename, str(exc) or exc.__class__.__name__
            )

        payload = status.get(IFS_OBJECT) if isinstance(status, dict) else None
        if isinstance(payload, dict):
            self._ifs_raw.update(payload)
            self._set_ifs_module(self._compose_ifs_module())

        module = self._ifs_module if isinstance(self._ifs_module, dict) else {}
        preview = module.get("job_preview")
        if not isinstance(preview, dict) or not preview.get("available", False):
            error = (
                preview.get("error")
                if isinstance(preview, dict)
                else "job_preview_not_published"
            )
            return self._job_preview_rejection(
                filename, f"Z-Mod job preview unavailable: {error or 'unknown'}"
            )

        return {
            "ok": True,
            "filename": filename,
            "job_preview": dict(preview),
            "preview_token": build_job_preview_token(preview),
            "snapshot": self.get_snapshot(),
        }

    async def _handle_ifs_job_mapping_draft(self, web_request: Any) -> Dict[str, Any]:
        """Validate a manual mapping draft. This path never emits G-code."""
        try:
            preview_token = web_request.get_str("preview_token").strip()
            resolved_tool_map = web_request.get("resolved_tool_map", None)
            provider_leveling = web_request.get("leveling", None)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Invalid IFS mapping draft request: {exc}",
                "snapshot": self.get_snapshot(),
            }

        module = self._ifs_module if isinstance(self._ifs_module, dict) else {}
        preview = module.get("job_preview")
        if not module.get("available", False) or not isinstance(preview, dict):
            return {
                "ok": False,
                "error": "IFS job preview is not available",
                "snapshot": self.get_snapshot(),
            }

        draft = build_job_mapping_draft(
            preview,
            resolved_tool_map,
            expected_preview_token=preview_token,
        )
        if draft.get("status") != "ready":
            return {
                "ok": False,
                "error": ",".join(draft.get("blockers") or ["invalid_mapping_draft"]),
                "mapping_draft": draft,
                "snapshot": self.get_snapshot(),
            }

        effective_preview = dict(preview)
        effective_preview["assignments"] = list(draft["assignments"])
        effective_preview["resolved_tool_map"] = list(draft["resolved_tool_map"])
        provider_auto_assign = effective_preview.get("auto_assign")
        effective_preview["auto_assign"] = {
            "flags": 0,
            "any_success": True,
            "material_failure": False,
            "color_failure": False,
            "weak_color": False,
            "duplicate_slot": False,
        }
        plan = build_preprint_plan(
            effective_preview,
            module.get("slots") if isinstance(module.get("slots"), list) else [],
        )
        gate = build_job_launch_gate(
            effective_preview,
            plan,
            module_state=module.get("state")
            if isinstance(module.get("state"), str)
            else "unknown",
            print_state=self._print_state,
            operation_state=self._operation_state,
            provider_leveling=provider_leveling,
        )
        gate["mapping_source"] = "manual"
        gate["provider_preview_token"] = draft["preview_token"]
        gate["draft_token"] = draft["draft_token"]
        return {
            "ok": True,
            "mapping_draft": draft,
            "provider_auto_assign": dict(provider_auto_assign)
            if isinstance(provider_auto_assign, dict)
            else {},
            "preprint_plan": plan,
            "launch_gate": gate,
            "snapshot": self.get_snapshot(),
        }

    async def _handle_ifs_job_launch_prepare(self, web_request: Any) -> Dict[str, Any]:
        """Freshly revalidate a launch candidate without executing PRINT_ZCOLOR."""
        try:
            filename = web_request.get_str("filename").strip()
            preview_token = web_request.get_str("preview_token").strip()
            draft_token = web_request.get_str("draft_token").strip()
            resolved_tool_map = web_request.get("resolved_tool_map", None)
            provider_leveling = web_request.get("leveling", None)
        except Exception as exc:
            return {"ok": False, "revalidated": False, "error": f"Invalid IFS launch prepare request: {exc}", "snapshot": self.get_snapshot()}

        fresh = await self._handle_ifs_job_preview(web_request)
        if not fresh.get("ok", False):
            return {"ok": False, "revalidated": False, "filename": filename, "error": fresh.get("error") or "job_preview_failed", "snapshot": self.get_snapshot()}

        module = self._ifs_module if isinstance(self._ifs_module, dict) else {}
        preview = fresh.get("job_preview")
        preview = preview if isinstance(preview, dict) else {}
        draft = build_job_mapping_draft(preview, resolved_tool_map, expected_preview_token=preview_token)
        if draft.get("status") != "ready":
            return {"ok": False, "revalidated": True, "filename": filename, "error": ",".join(draft.get("blockers") or ["invalid_mapping_draft"]), "mapping_draft": draft, "snapshot": self.get_snapshot()}
        if not draft_token or draft.get("draft_token") != draft_token:
            draft = dict(draft)
            blockers = list(draft.get("blockers") or [])
            if "stale_draft" not in blockers:
                blockers.append("stale_draft")
            draft["status"] = "blocked"
            draft["blockers"] = blockers
            return {"ok": False, "revalidated": True, "filename": filename, "error": "stale_draft", "mapping_draft": draft, "snapshot": self.get_snapshot()}

        effective_preview = dict(preview)
        effective_preview["assignments"] = list(draft["assignments"])
        effective_preview["resolved_tool_map"] = list(draft["resolved_tool_map"])
        effective_preview["auto_assign"] = {"flags": 0, "any_success": True, "material_failure": False, "color_failure": False, "weak_color": False, "duplicate_slot": False}
        plan = build_preprint_plan(effective_preview, module.get("slots") if isinstance(module.get("slots"), list) else [])
        gate = build_job_launch_gate(effective_preview, plan, module_state=module.get("state") if isinstance(module.get("state"), str) else "unknown", print_state=self._print_state, operation_state=self._operation_state, provider_leveling=provider_leveling)
        gate["mapping_source"] = "manual"
        gate["provider_preview_token"] = draft["preview_token"]
        gate["draft_token"] = draft["draft_token"]
        return {"ok": True, "revalidated": True, "filename": filename, "mapping_draft": draft, "preprint_plan": plan, "launch_gate": gate, "snapshot": self.get_snapshot()}

    async def _refresh_live_after_action(self, klippy_apis: Any) -> None:
        objects: Dict[str, Any] = {
            IFS_OBJECT: None,
            PRINT_STATS_OBJECT: ["state"],
            HEAD_SENSOR_OBJECT: ["enabled", "filament_detected"],
        }
        try:
            status = await klippy_apis.query_objects(objects, default={})
        except Exception:
            status = {}
        if isinstance(status, dict):
            payload = status.get(IFS_OBJECT)
            if isinstance(payload, dict):
                self._ifs_raw.update(payload)
            self._apply_aux_status(status)
        await self._refresh_ifs_metadata()
        if self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())
            await self._publish_orca_lane_data(self._ifs_module or {})
            await self._sync_spoolman_active_tracking(self._ifs_module)

    async def _handle_ifs_action(self, web_request: Any) -> Dict[str, Any]:
        try:
            action = web_request.get_str("action")
            slot = web_request.get_int("slot")
        except Exception as exc:
            return self._action_rejection("", 0, f"Invalid IFS action request: {exc}")

        await self._refresh_ifs_metadata()
        rejection = self._validate_ifs_action(action, slot)
        if rejection:
            return self._action_rejection(action, slot, rejection)

        # Selecting the already active lane is a safe no-op and avoids sending a
        # redundant firmware write.
        if action == "select_slot" and int(self._ifs_module.get("active_slot") or 0) == slot:
            return {
                "ok": True,
                "action": action,
                "slot": slot,
                "result": "already_selected",
                "snapshot": self.get_snapshot(),
            }

        command = IFS_ACTION_COMMANDS[action].format(slot=slot)
        self._operation_begin(action, slot)
        try:
            klippy_apis = self.server.lookup_component("klippy_apis")
            result = await klippy_apis.run_gcode(command)
            self._operation_end()
            await self._refresh_live_after_action(klippy_apis)
            return {
                "ok": True,
                "action": action,
                "slot": slot,
                "result": result,
                "snapshot": self.get_snapshot(),
            }
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            self._operation_end(error)
            return self._action_rejection(action, slot, error)

    async def _on_klippy_ready(self) -> None:
        try:
            klippy_apis = self.server.lookup_component("klippy_apis")
            objects = await klippy_apis.get_object_list(default=[])
        except Exception:
            self._ifs_raw.clear()
            self._set_ifs_module(self._unavailable_ifs("klippy_api_error"))
            return

        if IFS_OBJECT not in objects:
            self._ifs_raw.clear()
            self._set_ifs_module(self._unavailable_ifs("bridge_not_loaded"))
            return

        subscription: Dict[str, Any] = {
            IFS_OBJECT: None,
            PRINT_STATS_OBJECT: ["state"],
        }
        if HEAD_SENSOR_OBJECT in objects:
            subscription[HEAD_SENSOR_OBJECT] = ["enabled", "filament_detected"]
        if SAVE_VARIABLES_OBJECT in objects:
            subscription[SAVE_VARIABLES_OBJECT] = ["variables"]

        try:
            initial = await klippy_apis.subscribe_objects(
                subscription,
                callback=self._on_status_update,
                default={},
            )
        except Exception:
            self._ifs_raw.clear()
            self._set_ifs_module(self._unavailable_ifs("bridge_subscribe_error"))
            return

        payload = initial.get(IFS_OBJECT, {}) if isinstance(initial, dict) else {}
        if not isinstance(payload, dict):
            payload = {}
        self._ifs_raw = dict(payload)
        if isinstance(initial, dict):
            self._apply_aux_status(initial)
        await self._refresh_ifs_metadata()
        empty_slots = [
            slot for slot, present in self._slot_presence_map(self._ifs_raw).items()
            if not present
        ]
        if empty_slots:
            await self._invalidate_removed_slot_identities(empty_slots)
        if self._ifs_raw:
            self._apply_ifs_status({})
            await self._publish_orca_lane_data(self._ifs_module or {})
            if self._spoolman_connected():
                await self._refresh_spoolman_bindings()
            else:
                await self._sync_spoolman_active_tracking(self._ifs_module)
        else:
            self._set_ifs_module(self._unavailable_ifs("bridge_empty"))

    async def _on_status_update(
        self, status: Dict[str, Dict[str, Any]], _eventtime: float
    ) -> None:
        previous_print_state = self._print_state
        previous_presence = self._slot_presence_map(self._ifs_raw)
        changed = False
        payload = status.get(IFS_OBJECT)
        if isinstance(payload, dict):
            self._ifs_raw.update(payload)
            current_presence = self._slot_presence_map(self._ifs_raw)
            removed_slots = [
                slot for slot, was_present in previous_presence.items()
                if was_present and current_presence.get(slot) is False
            ]
            if removed_slots:
                await self._invalidate_removed_slot_identities(removed_slots)
            changed = True
        if self._apply_aux_status(status):
            changed = True
        if changed and self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())
            await self._publish_orca_lane_data(self._ifs_module or {})
            await self._sync_spoolman_active_tracking(self._ifs_module)

        if (
            previous_print_state in {"printing", "paused"}
            and self._print_state in {"standby", "complete", "cancelled", "error"}
            and self._spoolman_connected()
        ):
            # Moonraker owns usage accounting. Refresh bound inventory once the
            # job ends so all UI surfaces see the new remaining amounts.
            await self._refresh_spoolman_bindings()

    async def _on_klippy_disconnect(self) -> None:
        self._ifs_raw.clear()
        self._print_state = "unknown"
        self._head_filament = None
        self._provider_print_leveling = None
        self._operation_state = "idle"
        self._operation_action = ""
        self._operation_slot = 0
        self._operation_error = ""
        # Do not clear lane_data here: disconnect/offline is unknown state, not
        # proof that the user physically removed all four spools.
        status = dict(self._orca_lane_status)
        status["state"] = "stale"
        status["error"] = "klippy_disconnected"
        self._orca_lane_status = status
        self._set_ifs_module(self._unavailable_ifs("klippy_disconnected"))


def load_component(config: Any) -> PluginsAD5X:
    return PluginsAD5X(config)
