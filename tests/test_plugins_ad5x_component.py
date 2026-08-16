from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest
from enum import Flag, auto
from typing import Any, Dict, List, Tuple


ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x.py"


class RequestType(Flag):
    GET = auto()
    POST = auto()
    DELETE = auto()


class TransportType(Flag):
    HTTP = auto()
    WEBSOCKET = auto()
    MQTT = auto()
    INTERNAL = auto()


def load_component_module():
    moonraker_pkg = types.ModuleType("moonraker")
    moonraker_pkg.__path__ = []
    components_pkg = types.ModuleType("moonraker.components")
    components_pkg.__path__ = []
    common_module = types.ModuleType("moonraker.common")
    common_module.RequestType = RequestType
    common_module.TransportType = TransportType

    sys.modules["moonraker"] = moonraker_pkg
    sys.modules["moonraker.components"] = components_pkg
    sys.modules["moonraker.common"] = common_module

    spec = importlib.util.spec_from_file_location(
        "moonraker.components.plugins_ad5x",
        COMPONENT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load plugins_ad5x component spec")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


component_module = load_component_module()


class FakeServer:
    def __init__(self) -> None:
        self.endpoints: List[Dict[str, Any]] = []
        self.notifications: List[Tuple[str, str]] = []
        self.events: List[Tuple[str, Tuple[Any, ...]]] = []

    def register_endpoint(
        self,
        endpoint: str,
        request_types: RequestType,
        callback: Any,
        transports: TransportType,
        auth_required: bool = True,
        **_kwargs: Any,
    ) -> None:
        self.endpoints.append(
            {
                "endpoint": endpoint,
                "request_types": request_types,
                "callback": callback,
                "transports": transports,
                "auth_required": auth_required,
            }
        )

    def register_notification(self, event_name: str, notify_name: str) -> None:
        self.notifications.append((event_name, notify_name))

    def send_event(self, event_name: str, *args: Any) -> None:
        self.events.append((event_name, args))


class FakeConfig:
    def __init__(self, server: FakeServer) -> None:
        self._server = server

    def get_server(self) -> FakeServer:
        return self._server


class PluginsAD5XComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FakeServer()
        self.component = component_module.load_component(FakeConfig(self.server))

    def test_loader_returns_component(self) -> None:
        self.assertIsInstance(self.component, component_module.PluginsAD5X)

    def test_endpoint_registration_contract(self) -> None:
        endpoints = {entry["endpoint"]: entry for entry in self.server.endpoints}
        self.assertEqual(
            set(endpoints),
            {
                component_module.SNAPSHOT_ENDPOINT,
                component_module.IFS_ACTION_ENDPOINT,
            },
        )

        snapshot = endpoints[component_module.SNAPSHOT_ENDPOINT]
        self.assertEqual(snapshot["request_types"], RequestType.GET)
        action = endpoints[component_module.IFS_ACTION_ENDPOINT]
        self.assertEqual(action["request_types"], RequestType.POST)

        for endpoint in (snapshot, action):
            self.assertEqual(
                endpoint["transports"],
                TransportType.HTTP | TransportType.WEBSOCKET,
            )
            self.assertNotIn(TransportType.MQTT, endpoint["transports"])
            self.assertNotIn(TransportType.INTERNAL, endpoint["transports"])
            self.assertTrue(endpoint["auth_required"])

        snapshot_rpc = snapshot["endpoint"].strip("/").replace("/", ".")
        action_rpc = action["endpoint"].strip("/").replace("/", ".")
        self.assertEqual(snapshot_rpc, "server.plugins_ad5x.snapshot")
        self.assertEqual(action_rpc, "server.plugins_ad5x.ifs.action")

    def test_notification_registration_contract(self) -> None:
        self.assertEqual(
            self.server.notifications,
            [
                (
                    "plugins_ad5x:snapshot_changed",
                    "plugins_ad5x_snapshot_changed",
                )
            ],
        )
        wire_method = "notify_" + self.server.notifications[0][1]
        self.assertEqual(wire_method, "notify_plugins_ad5x_snapshot_changed")

    def test_snapshot_contract(self) -> None:
        snapshot = asyncio.run(self.component._handle_snapshot(object()))
        self.assertEqual(
            snapshot,
            {
                "api_version": "1.0",
                "backend_version": component_module.BACKEND_VERSION,
                "revision": 1,
                "backend": {"health": "ok"},
                "modules": {},
            },
        )

    def test_backend_version_matches_repository_version(self) -> None:
        repository_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(component_module.BACKEND_VERSION, repository_version)

    def test_revision_increment_and_invalidation_event(self) -> None:
        self.assertEqual(self.component.get_snapshot()["revision"], 1)
        revision = self.component.invalidate_snapshot()
        self.assertEqual(revision, 2)
        self.assertEqual(self.component.get_snapshot()["revision"], 2)
        self.assertEqual(
            self.server.events,
            [
                (
                    "plugins_ad5x:snapshot_changed",
                    ({"revision": 2},),
                )
            ],
        )

    def test_revision_is_process_local_state_only(self) -> None:
        self.component.invalidate_snapshot()
        fresh_component = component_module.load_component(FakeConfig(FakeServer()))
        self.assertEqual(fresh_component.get_snapshot()["revision"], 1)

    def test_basic_snapshot_has_no_hardware_dependencies(self) -> None:
        # FakeConfig/FakeServer intentionally expose only the Moonraker interfaces
        # required by the foundation component. Successful load and snapshot prove
        # there is no direct Klipper/hardware/USB/GPIO/macro dependency at import.
        snapshot = self.component.get_snapshot()
        self.assertEqual(snapshot["backend"]["health"], "ok")
        self.assertEqual(snapshot["modules"], {})


if __name__ == "__main__":
    unittest.main()
