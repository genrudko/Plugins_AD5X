from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import re
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


class FakeServerError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class FakeKlippyAPI:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.queries: List[Dict[str, Any]] = []
        self.gcode: List[str] = []
        self.fail_gcode: BaseException | None = None
        self.ignore_gcode_write = False

    async def query_objects(self, objects: Dict[str, Any], default: Any = None) -> Any:
        self.queries.append(objects)
        if isinstance(self.payload, BaseException):
            raise self.payload
        if self.payload is None:
            return default
        return self.payload

    async def run_gcode(self, script: str, default: Any = None) -> str:
        self.gcode.append(script)
        if self.fail_gcode is not None:
            raise self.fail_gcode
        if not self.ignore_gcode_write:
            match = re.fullmatch(
                r"SET_GCODE_OFFSET Z=([-+]?[0-9]+(?:\.[0-9]+)?) MOVE=0",
                script,
            )
            if match and isinstance(self.payload, dict):
                self.payload["gcode_move"]["homing_origin"][2] = float(match.group(1))
        return "ok"


class FakeServer:
    def __init__(
        self,
        klippy_apis: FakeKlippyAPI | None = None,
        *,
        enable_remote_methods: bool = True,
    ) -> None:
        self.endpoints: List[Dict[str, Any]] = []
        self.notifications: List[Tuple[str, str]] = []
        self.events: List[Tuple[str, Tuple[Any, ...]]] = []
        self.event_handlers: Dict[str, Any] = {}
        self.remote_methods: Dict[str, Any] = {}
        self.klippy_apis = klippy_apis
        self.enable_remote_methods = enable_remote_methods

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

    def register_remote_method(self, name: str, callback: Any) -> None:
        if self.enable_remote_methods:
            self.remote_methods[name] = callback

    def send_event(self, event_name: str, *args: Any) -> None:
        self.events.append((event_name, args))

    def lookup_component(self, name: str) -> Any:
        if name == "klippy_apis" and self.klippy_apis is not None:
            return self.klippy_apis
        raise KeyError(name)

    def error(self, message: str, status_code: int = 400) -> FakeServerError:
        return FakeServerError(message, status_code)


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

    def test_notification_klippy_job_and_remote_contract(self) -> None:
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
            {
                "server:klippy_disconnect",
                "server:klippy_ready",
                "job_state:state_changed",
            },
        )
        self.assertEqual(
            set(self.server.remote_methods),
            {"plugins_ad5x_z_job_start"},
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
        self.assertFalse(module["state"]["calibration"]["offset_hook_enabled"])
        self.assertTrue(module["state"]["safety"]["fail_closed"])
        self.assertEqual(module["state"]["safety"]["h7_role"], "secondary")
        self.assertEqual(module["state"]["job"]["phase"], "idle")

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
        self.assertEqual(klippy.gcode, [])

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
        self.assertEqual(klippy.gcode, [])

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
        self.assertEqual(
            module["state"]["safety"]["last_error"], "klippy_query_failed"
        )

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

    def test_global_start_adopts_zmod_baseline_without_rewriting_it(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(offset=-0.13, print_state="printing")
        )
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))

        result = asyncio.run(
            server.remote_methods["plugins_ad5x_z_job_start"](
                mode="global", z_offset=99.0
            )
        )

        state = result["module"]["state"]
        self.assertEqual(result["status"], "applied")
        self.assertEqual(state["job"]["phase"], "active")
        self.assertEqual(state["job"]["mode"], "global")
        self.assertAlmostEqual(state["offset"]["external_unknown"], -0.13)
        self.assertAlmostEqual(state["offset"]["slicer_job"], 0.0)
        self.assertEqual(klippy.gcode, [])

    def test_job_start_adopts_existing_zmod_z_offset_exactly_once(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(offset=-0.07, print_state="printing")
        )
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))

        first = asyncio.run(
            server.remote_methods["plugins_ad5x_z_job_start"](
                mode="job", z_offset=-0.07
            )
        )
        second = asyncio.run(
            server.remote_methods["plugins_ad5x_z_job_start"](
                mode="job", z_offset=-0.07
            )
        )

        self.assertEqual(first["status"], "applied")
        self.assertEqual(second["status"], "already_applied")
        self.assertAlmostEqual(
            second["module"]["state"]["offset"]["slicer_job"], -0.07
        )
        self.assertEqual(klippy.gcode, [])

    def test_auto_alignment_is_added_once_after_zmod_job_baseline(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(offset=-0.07, print_state="printing")
        )
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        component._z_offsets = component_module.zcore.OffsetComposition(
            auto_alignment=0.02
        )

        first = asyncio.run(
            server.remote_methods["plugins_ad5x_z_job_start"](
                mode="job", z_offset=-0.07
            )
        )
        second = asyncio.run(
            server.remote_methods["plugins_ad5x_z_job_start"](
                mode="job", z_offset=-0.07
            )
        )

        self.assertEqual(klippy.gcode, ["SET_GCODE_OFFSET Z=-0.050000000 MOVE=0"])
        self.assertAlmostEqual(
            first["module"]["state"]["offset"]["effective"], -0.05
        )
        self.assertEqual(second["status"], "already_applied")
        self.assertEqual(len(klippy.gcode), 1)

    def test_job_mode_mismatch_fails_before_any_write(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(offset=-0.06, print_state="printing")
        )
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))

        with self.assertRaises(FakeServerError) as ctx:
            asyncio.run(
                server.remote_methods["plugins_ad5x_z_job_start"](
                    mode="job", z_offset=-0.07
                )
            )
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(klippy.gcode, [])
        self.assertEqual(component._z_job["phase"], "idle")

    def test_none_mode_rejects_non_sentinel_parameter(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(offset=0.0, print_state="printing")
        )
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))

        with self.assertRaises(FakeServerError) as ctx:
            asyncio.run(
                server.remote_methods["plugins_ad5x_z_job_start"](
                    mode="none", z_offset=0.01
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(klippy.gcode, [])

    def test_terminal_job_event_clears_auto_job_live_and_external(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(offset=-0.07, print_state="printing")
        )
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        component._z_offsets = component_module.zcore.OffsetComposition(
            auto_alignment=0.02
        )
        asyncio.run(
            server.remote_methods["plugins_ad5x_z_job_start"](
                mode="job", z_offset=-0.07
            )
        )
        component._z_offsets = component._z_offsets.step_live(0.01)

        server.event_handlers["job_state:state_changed"](
            "cancelled", {}, {"state": "cancelled"}
        )

        snapshot = component.get_snapshot()["modules"]["z_calibration"]
        offset = snapshot["state"]["offset"]
        self.assertEqual(snapshot["state"]["job"]["phase"], "idle")
        self.assertAlmostEqual(offset["auto_alignment"], 0.0)
        self.assertAlmostEqual(offset["slicer_job"], 0.0)
        self.assertAlmostEqual(offset["live_adjustment"], 0.0)
        self.assertAlmostEqual(offset["external_unknown"], 0.0)

    def test_disconnect_clears_active_transients_before_reconnect(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(offset=-0.07, print_state="printing")
        )
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        asyncio.run(
            server.remote_methods["plugins_ad5x_z_job_start"](
                mode="job", z_offset=-0.07
            )
        )

        server.event_handlers["server:klippy_disconnect"]()
        self.assertEqual(component._z_job["phase"], "idle")
        self.assertFalse(component.get_snapshot()["modules"]["z_calibration"]["available"])

        klippy.payload = ready_payload(offset=0.0, print_state="standby")
        asyncio.run(server.event_handlers["server:klippy_ready"]())
        self.assertEqual(
            component.get_snapshot()["modules"]["z_calibration"]["state"]["job"]["phase"],
            "idle",
        )

    def test_failed_apply_verification_rolls_back_and_disarms_transients(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(offset=-0.07, print_state="printing")
        )
        klippy.ignore_gcode_write = True
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        component._z_offsets = component_module.zcore.OffsetComposition(
            auto_alignment=0.02
        )

        with self.assertRaises(FakeServerError) as ctx:
            asyncio.run(
                server.remote_methods["plugins_ad5x_z_job_start"](
                    mode="job", z_offset=-0.07
                )
            )
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(component._z_job["phase"], "idle")
        self.assertAlmostEqual(component._z_offsets.auto_alignment, 0.0)
        self.assertAlmostEqual(component._z_offsets.slicer_job, 0.0)
        self.assertEqual(
            klippy.gcode,
            [
                "SET_GCODE_OFFSET Z=-0.050000000 MOVE=0",
                "SET_GCODE_OFFSET Z=0.000000000 MOVE=0",
            ],
        )
        self.assertEqual(
            component._z_last_error,
            "offset_apply_failed_reconciliation_required",
        )

    def test_klippy_disconnect_invalidates_snapshot_and_fails_closed(self) -> None:
        server = FakeServer(FakeKlippyAPI(ready_payload(offset=0.0)))
        component = component_module.load_component(FakeConfig(server))
        asyncio.run(component._handle_snapshot(object()))
        self.assertTrue(
            component.get_snapshot()["modules"]["z_calibration"]["available"]
        )

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
        self.assertEqual(klippy.gcode, [])


if __name__ == "__main__":
    unittest.main()
