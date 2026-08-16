# Plugins AD5X - optional Moonraker foundation component

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Dict

from ..common import RequestType, TransportType

try:
    from .plugins_ad5x_ifs_model import normalize_module
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
    normalize_module = _model_module.normalize_module

API_VERSION = "1.0"
BACKEND_VERSION = "0.1.4"

SNAPSHOT_ENDPOINT = "/server/plugins_ad5x/snapshot"
IFS_ACTION_ENDPOINT = "/server/plugins_ad5x/ifs/action"
SNAPSHOT_CHANGED_EVENT = "plugins_ad5x:snapshot_changed"
SNAPSHOT_CHANGED_NOTIFY_NAME = "plugins_ad5x_snapshot_changed"
IFS_OBJECT = "ad5x_ifs"
PRINT_STATS_OBJECT = "print_stats"
HEAD_SENSOR_OBJECT = "filament_switch_sensor head_switch_sensor"

FFCONFIG_PATH = "/usr/prog/config/Adventurer5M.json"
FILE_MAPPING_PATH = "/usr/data/config/mod_data/file.json"

SAFE_FILAMENT_OP_PRINT_STATES = {"standby", "complete", "cancelled", "error"}
IFS_ACTION_COMMANDS = {
    "select_slot": "SET_EXTRUDER_SLOT SLOT={slot}",
    "load_slot": "INSERT_PRUTOK_IFS PRUTOK={slot}",
    # Z-Mod's stock toolhead-unload wrapper: it owns heat/cut/trash/cooldown semantics.
    "unload_slot": "_IFS_REMOVE_CURRENT_PRUTOK",
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
        self._operation_state = "idle"
        self._operation_action = ""
        self._operation_slot = 0
        self._operation_error = ""

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
        return normalize_module(
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
        # The two metadata files are tiny but live outside Moonraker ownership.
        # Refresh them on demand instead of adding a steady-state polling loop.
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

    def _compose_ifs_module(self) -> Dict[str, Any]:
        return normalize_module(
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
        return changed

    @staticmethod
    def _read_json(path: str) -> Any:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)

    def _read_ifs_metadata_sync(self) -> Dict[str, Any]:
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
                and all(isinstance(slot, int) and 1 <= slot <= 4 for slot in mapping)
            ):
                metadata["tool_mapping"] = list(mapping)
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass

        return metadata

    async def _refresh_ifs_metadata(self) -> bool:
        try:
            event_loop = self.server.get_event_loop()
        except (AttributeError, TypeError):
            event_loop = None

        if event_loop is not None and hasattr(event_loop, "run_in_thread"):
            metadata = await event_loop.run_in_thread(self._read_ifs_metadata_sync)
        else:
            # Test/minimal compatibility path. Real Moonraker takes the
            # run_in_thread branch above.
            metadata = self._read_ifs_metadata_sync()

        if metadata == self._ifs_metadata:
            return False
        self._ifs_metadata = metadata
        if self._ifs_raw:
            return self._set_ifs_module(self._compose_ifs_module())
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

    def _validate_ifs_action(self, action: str, slot: int) -> str:
        if action not in IFS_ACTION_COMMANDS:
            return f"Unsupported IFS action: {action}"
        if slot < 1 or slot > 4:
            return f"Invalid IFS slot: {slot}"
        if self._ifs_module is None or not self._ifs_module.get("available", False):
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
        if self._ifs_raw:
            self._apply_ifs_status({})
        else:
            self._set_ifs_module(self._unavailable_ifs("bridge_empty"))

    async def _on_status_update(
        self, status: Dict[str, Dict[str, Any]], _eventtime: float
    ) -> None:
        changed = False
        payload = status.get(IFS_OBJECT)
        if isinstance(payload, dict):
            self._ifs_raw.update(payload)
            changed = True
        if self._apply_aux_status(status):
            changed = True
        if changed and self._ifs_raw:
            self._set_ifs_module(self._compose_ifs_module())

    async def _on_klippy_disconnect(self) -> None:
        self._ifs_raw.clear()
        self._print_state = "unknown"
        self._head_filament = None
        self._operation_state = "idle"
        self._operation_action = ""
        self._operation_slot = 0
        self._operation_error = ""
        self._set_ifs_module(self._unavailable_ifs("klippy_disconnected"))


def load_component(config: Any) -> PluginsAD5X:
    return PluginsAD5X(config)
