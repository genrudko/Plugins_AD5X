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
MOONRAKER_PATH = ROOT / "moonraker"
COMPONENTS_PATH = MOONRAKER_PATH / "components"
COMPONENT_PATH = COMPONENTS_PATH / "plugins_ad5x.py"


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
    for name in list(sys.modules):
        if name == "moonraker" or name.startswith("moonraker."):
            del sys.modules[name]

    moonraker_pkg = types.ModuleType("moonraker")
    moonraker_pkg.__path__ = [str(MOONRAKER_PATH)]
    components_pkg = types.ModuleType("moonraker.components")
    components_pkg.__path__ = [str(COMPONENTS_PATH)]
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


class FakeKlippyAPI:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.queries: List[Dict[str, Any]] = []

    async def query_objects(self, objects: Dict[str, Any], default: Any = None) -> Any:
        self.queries.append(objects)
        if isinstance(self.payload, BaseException):
            raise self.payload
        if self.payload is None:
            return default
        return self.payload


class FakeServer:
    def __init__(self, klippy_apis: FakeKlippyAPI | None = None) -> None:
        self.endpoints: List[Dict[str, Any]] = []
        self.notifications: List[Tuple[str, str]] = []
        self.events: List[Tuple[str, Tuple[Any, ...]]] = []
        self.event_handlers: Dict[str, Any] = {}
        self.klippy_apis = klippy_apis

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

    def register_event_handler(self, event_name: str, callback: Any) -> None:
        self.event_handlers[event_name] = callback

    def send_event(self, event_name: str, *args: Any) -> None:
        self.events.append((event_name, args))

    def lookup_component(self, name: str) -> Any:
        if name == "klippy_apis" and self.klippy_apis is not None:
            return self.klippy_apis
        raise KeyError(name)


class FakeConfig:
    def __init__(self, server: FakeServer) -> None:
        self._server = server

    def get_server(self) -> FakeServer:
        return self._server


def ready_payload(
    *,
    offset: float = 0.0,
    print_state: str = "standby",
    homed_axes: str = "xyz",
) -> Dict[str, Any]:
    return {
        "gcode_move": {"homing_origin": [0.0, 0.0, offset]},
        "print_stats": {"state": print_state},
        "toolhead": {"homed_axes": homed_axes},
    }


class PluginsAD5XComponentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FakeServer()
        self.component = component_module.load_component(FakeConfig(self.server))

    def endpoint(self, path: str) -> Dict[str, Any]:
        return next(ep for ep in self.server.endpoints if ep["endpoint"] == path)

    def test_loader_returns_component(self) -> None:
        self.assertIsInstance(self.component, component_module.PluginsAD5X)
        self.assertIsNotNone(component_module.zcore)

    def test_endpoint_registration_contract(self) -> None:
        self.assertEqual(len(self.server.endpoints), 3)
        expected = {
            "/server/plugins_ad5x/snapshot": RequestType.GET,
            "/server/plugins_ad5x/z_calibration/reconcile": RequestType.POST,
            "/server/plugins_ad5x/z_calibration/diagnostics": RequestType.GET,
        }
        for path, method in expected.items():
            endpoint = self.endpoint(path)
            self.assertEqual(endpoint["request_types"], method)
            self.assertEqual(
                endpoint["transports"],
                TransportType.HTTP | TransportType.WEBSOCKET,
            )
            self.assertNotIn(TransportType.MQTT, endpoint["transports"])
            self.assertNotIn(TransportType.INTERNAL, endpoint["transports"])
            self.assertTrue(endpoint["auth_required"])

        rpc_method = (
            self.endpoint("/server/plugins_ad5x/snapshot")["endpoint"]
            .strip("/")
            .replace("/", ".")
        )
        self.assertEqual(rpc_method, "server.plugins_ad5x.snapshot")

    def test_notification_and_klippy_event_contract(self) -> None:
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
        self.assertEqual(
            set(self.server.event_handlers),
            {"server:klippy_disconnect", "server:klippy_ready"},
        )

    def test_snapshot_keeps_platform_healthy_when_klippy_unavailable(self) -> None:
        snapshot = asyncio.run(self.component._handle_snapshot(object()))
        self.assertEqual(snapshot["api_version"], "1.0")
        self.assertEqual(snapshot["backend_version"], "0.1.2")
        self.assertEqual(snapshot["revision"], 1)
        self.assertEqual(snapshot["backend"], {"health": "ok"})
        module = snapshot["modules"]["z_calibration"]
        self.assertEqual(module["support"], "supported")
        self.assertTrue(module["enabled"])
        self.assertEqual(module["presence"], "present")
        self.assertFalse(module["available"])
        self.assertEqual(module["health"], "degraded")
        self.assertFalse(module["state"]["calibration"]["motion_actions_enabled"])
        self.assertTrue(module["state"]["safety"]["fail_closed"])
        self.assertEqual(module["state"]["safety"]["h7_role"], "secondary")

    def test_backend_version_matches_repository_version(self) -> None:
        repository_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(component_module.BACKEND_VERSION, repository_version)

    def test_live_snapshot_reconciles_actual_offset_without_gcode_write(self) -> None:
        klippy = FakeKlippyAPI(ready_payload(offset=-0.13))
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))

        snapshot = asyncio.run(component._handle_snapshot(object()))
        module = snapshot["modules"]["z_calibration"]
        offset = module["state"]["offset"]

        self.assertTrue(module["available"])
        self.assertEqual(module["health"], "ok")
        self.assertAlmostEqual(offset["known_total"], 0.0)
        self.assertAlmostEqual(offset["external_unknown"], -0.13)
        self.assertAlmostEqual(offset["effective"], -0.13)
        self.assertEqual(offset["provenance_status"], "external_unknown")
        self.assertEqual(module["state"]["runtime"]["print_state"], "standby")
        self.assertEqual(module["state"]["runtime"]["homed_axes"], "xyz")
        self.assertEqual(len(klippy.queries), 1)
        self.assertEqual(
            klippy.queries[0],
            {
                "gcode_move": ["homing_origin"],
                "print_stats": ["state"],
                "toolhead": ["homed_axes"],
            },
        )
        self.assertFalse(hasattr(klippy, "run_gcode"))

    def test_reconcile_endpoint_is_authenticated_read_only_action(self) -> None:
        klippy = FakeKlippyAPI(ready_payload(offset=0.04))
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        endpoint = next(
            ep
            for ep in server.endpoints
            if ep["endpoint"] == "/server/plugins_ad5x/z_calibration/reconcile"
        )

        result = asyncio.run(endpoint["callback"](object()))
        self.assertTrue(endpoint["auth_required"])
        self.assertEqual(result["revision"], 1)
        self.assertAlmostEqual(
            result["module"]["state"]["offset"]["external_unknown"],
            0.04,
        )
        self.assertFalse(hasattr(klippy, "run_gcode"))

    def test_matching_known_composition_reconciles_without_unknown(self) -> None:
        klippy = FakeKlippyAPI(ready_payload(offset=0.006))
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        component._z_offsets = component_module.zcore.OffsetComposition(
            auto_alignment=0.036,
            persistent_user=-0.03,
        )

        snapshot = asyncio.run(component._handle_snapshot(object()))
        offset = snapshot["modules"]["z_calibration"]["state"]["offset"]
        self.assertAlmostEqual(offset["known_total"], 0.006)
        self.assertAlmostEqual(offset["external_unknown"], 0.0)
        self.assertAlmostEqual(offset["effective"], 0.006)
        self.assertEqual(offset["provenance_status"], "reconciled")

    def test_malformed_klippy_state_degrades_module_not_platform(self) -> None:
        malformed = ready_payload(offset=0.0)
        malformed["gcode_move"]["homing_origin"] = [0.0, 0.0]
        server = FakeServer(FakeKlippyAPI(malformed))
        component = component_module.load_component(FakeConfig(server))

        snapshot = asyncio.run(component._handle_snapshot(object()))
        self.assertEqual(snapshot["backend"]["health"], "ok")
        module = snapshot["modules"]["z_calibration"]
        self.assertFalse(module["available"])
        self.assertEqual(module["health"], "degraded")
        self.assertEqual(module["state"]["safety"]["last_error"], "klippy_query_failed")

    def test_klippy_query_exception_degrades_without_stale_effective_value(self) -> None:
        server = FakeServer(FakeKlippyAPI(RuntimeError("disconnect")))
        component = component_module.load_component(FakeConfig(server))
        component._z_offsets = component_module.zcore.OffsetComposition(
            external_unknown=0.2
        )

        snapshot = asyncio.run(component._handle_snapshot(object()))
        offset = snapshot["modules"]["z_calibration"]["state"]["offset"]
        self.assertIsNone(offset["effective"])
        self.assertEqual(offset["provenance_status"], "unavailable")

    def test_diagnostics_records_reconciliation_and_is_bounded_backend_view(self) -> None:
        server = FakeServer(FakeKlippyAPI(ready_payload(offset=-0.125)))
        component = component_module.load_component(FakeConfig(server))
        asyncio.run(component._handle_z_reconcile(object()))
        result = asyncio.run(component._handle_z_diagnostics(object()))

        self.assertEqual(result["schema_version"], "1.0")
        self.assertGreaterEqual(len(result["events"]), 1)
        last = result["events"][-1]
        self.assertEqual(last["event_type"], "offset_reconciled")
        self.assertAlmostEqual(last["payload"]["actual_effective"], -0.125)
        self.assertIn("external_unknown", last["payload"])

    def test_klippy_disconnect_invalidates_snapshot_and_fails_closed(self) -> None:
        server = FakeServer(FakeKlippyAPI(ready_payload(offset=0.0)))
        component = component_module.load_component(FakeConfig(server))
        asyncio.run(component._handle_snapshot(object()))
        self.assertTrue(component.get_snapshot()["modules"]["z_calibration"]["available"])

        server.event_handlers["server:klippy_disconnect"]()
        snapshot = component.get_snapshot()
        self.assertEqual(snapshot["revision"], 2)
        self.assertFalse(snapshot["modules"]["z_calibration"]["available"])
        self.assertEqual(
            snapshot["modules"]["z_calibration"]["state"]["safety"]["last_error"],
            "klippy_disconnected",
        )
        self.assertEqual(
            server.events[-1],
            (
                "plugins_ad5x:snapshot_changed",
                ({"revision": 2},),
            ),
        )

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

    def test_constructor_does_not_query_klippy_or_perform_io(self) -> None:
        klippy = FakeKlippyAPI(ready_payload(offset=0.0))
        component_module.load_component(FakeConfig(FakeServer(klippy)))
        self.assertEqual(klippy.queries, [])


if __name__ == "__main__":
    unittest.main()
