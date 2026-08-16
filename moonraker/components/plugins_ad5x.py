# Plugins AD5X - optional Moonraker foundation component

from __future__ import annotations

from typing import Any, Dict

from ..common import RequestType, TransportType

API_VERSION = "1.0"
BACKEND_VERSION = "0.1.2"

SNAPSHOT_ENDPOINT = "/server/plugins_ad5x/snapshot"
SNAPSHOT_CHANGED_EVENT = "plugins_ad5x:snapshot_changed"
SNAPSHOT_CHANGED_NOTIFY_NAME = "plugins_ad5x_snapshot_changed"
IFS_OBJECT = "ad5x_ifs"


class PluginsAD5X:
    def __init__(self, config: Any) -> None:
        self.server = config.get_server()
        self._revision = 1
        self._ifs_raw: Dict[str, Any] = {}
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

    def _apply_ifs_status(self, payload: Dict[str, Any]) -> bool:
        # Klipper subscriptions may deliver partial object updates.  Merge into
        # the last complete state before publishing the canonical module.
        self._ifs_raw.update(payload)
        module = dict(self._ifs_raw)
        module.pop("reason", None)
        return self._set_ifs_module(module)

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
