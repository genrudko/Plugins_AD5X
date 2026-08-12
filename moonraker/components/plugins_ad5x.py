# Plugins AD5X - optional Moonraker foundation component
#
# This file is deployed into Moonraker's components package.  Keep the
# implementation deliberately small: Platform Foundation has no hardware
# providers, background jobs, polling loops, database, or blocking I/O.

from __future__ import annotations

from typing import Any, Dict

from ..common import RequestType, TransportType

API_VERSION = "1.0"
# Deployment may ultimately use either a symlink or a copy.  A copied component
# cannot reliably discover the Plugins AD5X repository root at runtime, so the
# release version is embedded here and guarded against the repository VERSION
# file by an automated test.
BACKEND_VERSION = "0.1.2"

SNAPSHOT_ENDPOINT = "/server/plugins_ad5x/snapshot"
SNAPSHOT_CHANGED_EVENT = "plugins_ad5x:snapshot_changed"
SNAPSHOT_CHANGED_NOTIFY_NAME = "plugins_ad5x_snapshot_changed"


class PluginsAD5X:
    def __init__(self, config: Any) -> None:
        self.server = config.get_server()
        self._revision = 1

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

    def get_snapshot(self) -> Dict[str, Any]:
        return {
            "api_version": API_VERSION,
            "backend_version": BACKEND_VERSION,
            "revision": self._revision,
            "backend": {
                "health": "ok",
            },
            "modules": {},
        }

    async def _handle_snapshot(self, _web_request: Any) -> Dict[str, Any]:
        return self.get_snapshot()

    def invalidate_snapshot(self) -> int:
        """Mark the current snapshot stale after a semantic state change."""
        self._revision += 1
        self.server.send_event(
            SNAPSHOT_CHANGED_EVENT,
            {"revision": self._revision},
        )
        return self._revision


def load_component(config: Any) -> PluginsAD5X:
    return PluginsAD5X(config)
