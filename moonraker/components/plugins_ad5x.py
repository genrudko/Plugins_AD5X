# Plugins AD5X - optional Moonraker foundation component

from __future__ import annotations

import json
from typing import Any, Dict

from ..common import RequestType, TransportType

API_VERSION = "1.0"
BACKEND_VERSION = "0.1.2"

SNAPSHOT_ENDPOINT = "/server/plugins_ad5x/snapshot"
SNAPSHOT_CHANGED_EVENT = "plugins_ad5x:snapshot_changed"
SNAPSHOT_CHANGED_NOTIFY_NAME = "plugins_ad5x_snapshot_changed"
IFS_OBJECT = "ad5x_ifs"

FFCONFIG_PATH = "/usr/prog/config/Adventurer5M.json"
FILE_MAPPING_PATH = "/usr/data/config/mod_data/file.json"


class PluginsAD5X:
    def __init__(self, config: Any) -> None:
        self.server = config.get_server()
        self._revision = 1
        self._ifs_raw: Dict[str, Any] = {}
        self._ifs_metadata: Dict[str, Any] = {}
        self._ifs_module = None

        self.server.register_endpoint(
            SNAPSHOT_ENDPOINT,
            RequestType.GET,
            self._handle_snapshot,
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

    @staticmethod
    def _unavailable_ifs(reason: str) -> Dict[str, Any]:
        return {
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
        module = dict(self._ifs_raw)
        module.pop("reason", None)

        slot_meta = self._ifs_metadata.get("slots", {})
        raw_slots = module.get("slots")
        if isinstance(raw_slots, list) and slot_meta:
            enriched_slots = []
            for raw_slot in raw_slots:
                if not isinstance(raw_slot, dict):
                    continue
                item = dict(raw_slot)
                slot = item.get("slot")
                metadata = slot_meta.get(slot)
                if isinstance(metadata, dict):
                    item.update(metadata)
                enriched_slots.append(item)
            module["slots"] = enriched_slots

        configured_active_slot = self._ifs_metadata.get("active_slot")
        if isinstance(configured_active_slot, int) and configured_active_slot > 0:
            runtime_active_slot = module.get("active_slot", 0)
            module["runtime_active_slot"] = runtime_active_slot
            module["active_slot"] = configured_active_slot

        tool_mapping = self._ifs_metadata.get("tool_mapping")
        if isinstance(tool_mapping, list):
            module["tool_mapping"] = list(tool_mapping)

        return module

    def _apply_ifs_status(self, payload: Dict[str, Any]) -> bool:
        # Klipper subscriptions may deliver partial object updates. Merge into
        # the last complete state before publishing the canonical module.
        self._ifs_raw.update(payload)
        return self._set_ifs_module(self._compose_ifs_module())

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

        try:
            initial = await klippy_apis.subscribe_objects(
                {IFS_OBJECT: None},
                callback=self._on_ifs_status_update,
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
        await self._refresh_ifs_metadata()
        if self._ifs_raw:
            self._apply_ifs_status({})
        else:
            self._set_ifs_module(self._unavailable_ifs("bridge_empty"))

    async def _on_ifs_status_update(
        self, status: Dict[str, Dict[str, Any]], _eventtime: float
    ) -> None:
        payload = status.get(IFS_OBJECT)
        if isinstance(payload, dict):
            self._apply_ifs_status(payload)

    async def _on_klippy_disconnect(self) -> None:
        self._ifs_raw.clear()
        self._set_ifs_module(self._unavailable_ifs("klippy_disconnected"))


def load_component(config: Any) -> PluginsAD5X:
    return PluginsAD5X(config)
