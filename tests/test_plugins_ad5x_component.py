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
        "moonraker.components.plugins_ad5x", COMPONENT_PATH
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

    async def query_objects(self, objects: Dict[str, Any], default: Any = None) -> Any:
        self.queries.append(objects)
        if isinstance(self.payload, BaseException):
            raise self.payload
        return default if self.payload is None else self.payload

    async def run_gcode(self, script: str, default: Any = None) -> str:
        self.gcode.append(script)
        return "ok"


class FakeServer:
    def __init__(self, klippy_apis: FakeKlippyAPI | None = None) -> None:
        self.endpoints: List[Dict[str, Any]] = []
        self.notifications: List[Tuple[str, str]] = []
        self.events: List[Tuple[str, Tuple[Any, ...]]] = []
        self.event_handlers: Dict[str, Any] = {}
        self.remote_methods: Dict[str, Any] = {}
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

    def register_remote_method(self, name: str, callback: Any) -> None:
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
    persistent: float = -0.03,
    auto: float = 0.014166,
    actual: float | None = None,
    requested_job: float = 99.0,
    screen: bool = False,
    load_zoffset: int = 1,
    mesh_test: int = 3,
    print_leveling: int = 0,
    force_kamp: bool = False,
    force_leveling: bool = False,
    print_state: str = "printing",
    homed_axes: str = "xyz",
    policy_id: str | None = component_module.Z_RC_POLICY_ID,
    hook_commands: list[str] | None = None,
    include_offsets: bool = True,
    include_auto: bool = True,
) -> Dict[str, Any]:
    if actual is None:
        actual = persistent + auto
    variables: Dict[str, Any] = {
        "load_zoffset": load_zoffset,
        "mesh_test": mesh_test,
        "print_leveling": print_leveling,
    }
    if include_offsets:
        variables["gcode_offsets"] = {"z": persistent}
    if hook_commands is None:
        hook_commands = [component_module.Z_CC_APPLY, component_module.Z_RC_GUARD]
    payload: Dict[str, Any] = {
        "gcode_move": {"homing_origin": [0.0, 0.0, actual]},
        "print_stats": {"state": print_state},
        "toolhead": {"homed_axes": homed_axes},
        "save_variables": {"variables": variables},
        "gcode_macro _SCREEN": {"screen": screen},
        "gcode_macro _START_PRINT": {
            "zzoffset": requested_job,
            "zforce_kamp": force_kamp,
            "zforce_leveling": force_leveling,
        },
        "bed_mesh": {"profile_name": "auto"},
        "configfile": {
            "settings": {
                "gcode_macro _user_start_print": {
                    "gcode": "\n".join(hook_commands),
                }
            }
        },
    }
    if include_auto:
        payload["gcode_macro _TEST_POINT"] = {"temp_z_offset": auto}
    if policy_id is not None:
        payload[component_module.Z_RC_POLICY_OBJECT] = {
            "policy_id": policy_id,
            "max_auto_alignment": 0.12,
            "saved_profile": "auto",
            "saved_reference": -1.925833,
            "reference_tolerance": 0.0005,
        }
    return payload


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
                endpoint["transports"], TransportType.HTTP | TransportType.WEBSOCKET
            )
            self.assertNotIn(TransportType.MQTT, endpoint["transports"])
            self.assertNotIn(TransportType.INTERNAL, endpoint["transports"])
            self.assertTrue(endpoint["auth_required"])

    def test_observer_registers_no_z_write_remote_method(self) -> None:
        self.assertEqual(self.server.remote_methods, {})
        self.assertEqual(
            set(self.server.event_handlers),
            {
                "server:klippy_disconnect",
                "server:klippy_ready",
                "job_state:state_changed",
            },
        )

    def test_default_snapshot_is_read_only_and_fail_closed(self) -> None:
        state = self.component.get_snapshot()["modules"]["z_calibration"]["state"]
        calibration = state["calibration"]
        self.assertEqual(calibration["state"], "observer")
        self.assertFalse(calibration["motion_actions_enabled"])
        self.assertEqual(calibration["motion_owner"], "zmod")
        self.assertFalse(calibration["offset_write_enabled"])
        self.assertEqual(state["offset"]["provenance_status"], "unavailable")
        self.assertTrue(state["safety"]["fail_closed"])

    def test_accepted_live_composition_is_explained_without_residual(self) -> None:
        # Owner-accepted RC example: -0.030000 + 0.014166 = -0.015834 mm.
        klippy = FakeKlippyAPI(
            ready_payload(persistent=-0.03, auto=0.014166, actual=-0.015834)
        )
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        snapshot = asyncio.run(component._handle_snapshot(object()))
        state = snapshot["modules"]["z_calibration"]["state"]
        offset = state["offset"]
        provenance = state["provenance"]
        self.assertAlmostEqual(offset["persistent_user"], -0.03)
        self.assertAlmostEqual(offset["auto_alignment"], 0.014166)
        self.assertAlmostEqual(offset["slicer_job"], 0.0)
        self.assertAlmostEqual(offset["live_adjustment"], 0.0)
        self.assertAlmostEqual(offset["external_unknown"], 0.0)
        self.assertAlmostEqual(offset["effective"], -0.015834)
        self.assertEqual(offset["provenance_status"], "reconciled")
        self.assertEqual(
            provenance["sources"]["persistent_user"],
            "save_variables.variables.gcode_offsets.z",
        )
        self.assertEqual(
            provenance["sources"]["auto_alignment"],
            "gcode_macro _TEST_POINT.temp_z_offset",
        )
        self.assertEqual(klippy.gcode, [])

    def test_slicer_z_offset_is_reported_as_requested_but_ignored_on_global_path(self) -> None:
        klippy = FakeKlippyAPI(ready_payload(requested_job=0.075))
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        state = asyncio.run(component._handle_snapshot(object()))["modules"][
            "z_calibration"
        ]["state"]
        self.assertAlmostEqual(state["offset"]["slicer_job"], 0.0)
        self.assertAlmostEqual(state["job"]["requested_slicer_z_offset"], 0.075)
        self.assertEqual(
            state["job"]["slicer_z_offset_effect"],
            "ignored_by_zmod_global_offset_path",
        )
        self.assertTrue(state["provenance"]["rc_path"]["global_offset_path"])

    def test_unattributed_residual_stays_external_unknown_not_live_babystep(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(persistent=-0.03, auto=0.014166, actual=-0.005834)
        )
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        offset = asyncio.run(component._handle_snapshot(object()))["modules"][
            "z_calibration"
        ]["state"]["offset"]
        self.assertAlmostEqual(offset["live_adjustment"], 0.0)
        self.assertAlmostEqual(offset["external_unknown"], 0.01)
        self.assertEqual(offset["provenance_status"], "external_unknown")

    def test_missing_auto_source_is_partial_not_fabricated_zero_provenance(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(
                persistent=-0.03,
                auto=0.014166,
                actual=-0.015834,
                include_auto=False,
            )
        )
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        state = asyncio.run(component._handle_snapshot(object()))["modules"][
            "z_calibration"
        ]["state"]
        self.assertEqual(state["offset"]["provenance_status"], "partial")
        self.assertIn("auto_alignment", state["provenance"]["missing_components"])
        self.assertAlmostEqual(state["offset"]["auto_alignment"], 0.0)
        self.assertAlmostEqual(state["offset"]["external_unknown"], 0.014166)

    def test_missing_saved_global_offset_is_known_implicit_zero(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(
                persistent=0.0,
                auto=0.014166,
                actual=0.014166,
                include_offsets=False,
            )
        )
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        state = asyncio.run(component._handle_snapshot(object()))["modules"][
            "z_calibration"
        ]["state"]
        self.assertEqual(state["offset"]["provenance_status"], "reconciled")
        self.assertEqual(
            state["provenance"]["sources"]["persistent_user"],
            "implicit_zero:LOAD_GCODE_OFFSET",
        )

    def test_non_global_zmod_path_is_not_forced_into_additive_model(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(screen=True, load_zoffset=1, requested_job=-0.13, actual=-0.115834)
        )
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        state = asyncio.run(component._handle_snapshot(object()))["modules"][
            "z_calibration"
        ]["state"]
        self.assertEqual(
            state["offset"]["provenance_status"], "unsupported_zmod_offset_path"
        )
        self.assertAlmostEqual(state["offset"]["persistent_user"], 0.0)
        self.assertAlmostEqual(state["offset"]["slicer_job"], 0.0)
        self.assertFalse(state["provenance"]["rc_path"]["global_offset_path"])

    def test_rc_path_flags_expose_policy_compatibility_without_frontend_math(self) -> None:
        klippy = FakeKlippyAPI(ready_payload())
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        path = asyncio.run(component._handle_snapshot(object()))["modules"][
            "z_calibration"
        ]["state"]["provenance"]["rc_path"]
        self.assertTrue(path["accepted_saved_check_flags"])
        self.assertEqual(path["mesh_test"], 3)
        self.assertEqual(path["print_leveling"], 0)
        self.assertFalse(path["screen"])
        self.assertEqual(path["policy_id"], component_module.Z_RC_POLICY_ID)

    def test_effective_hook_chain_and_policy_identity_are_detected(self) -> None:
        klippy = FakeKlippyAPI(ready_payload())
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        calibration = asyncio.run(component._handle_snapshot(object()))["modules"][
            "z_calibration"
        ]["state"]["calibration"]
        self.assertTrue(calibration["offset_hook_enabled"])
        self.assertEqual(calibration["offset_hook_status"], "loaded")
        self.assertEqual(calibration["integration"]["policy_status"], "loaded")
        self.assertEqual(
            calibration["integration"]["hook_commands"],
            [component_module.Z_CC_APPLY, component_module.Z_RC_GUARD],
        )

    def test_guard_only_expected_chain_is_supported(self) -> None:
        klippy = FakeKlippyAPI(ready_payload(hook_commands=[component_module.Z_RC_GUARD]))
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        calibration = asyncio.run(component._handle_snapshot(object()))["modules"][
            "z_calibration"
        ]["state"]["calibration"]
        self.assertTrue(calibration["offset_hook_enabled"])
        self.assertEqual(calibration["offset_hook_status"], "loaded")

    def test_duplicate_or_foreign_guard_chain_is_not_accepted(self) -> None:
        for commands, expected in (
            (
                [component_module.Z_CC_APPLY, component_module.Z_RC_GUARD, component_module.Z_RC_GUARD],
                "duplicate_guard",
            ),
            (["M117 FOREIGN", component_module.Z_RC_GUARD], "incompatible"),
        ):
            with self.subTest(commands=commands):
                klippy = FakeKlippyAPI(ready_payload(hook_commands=commands))
                component = component_module.load_component(FakeConfig(FakeServer(klippy)))
                calibration = asyncio.run(component._handle_snapshot(object()))["modules"][
                    "z_calibration"
                ]["state"]["calibration"]
                self.assertFalse(calibration["offset_hook_enabled"])
                self.assertEqual(calibration["offset_hook_status"], expected)

    def test_incompatible_or_missing_policy_is_not_reported_loaded(self) -> None:
        for policy_id, expected in (("other-policy", "incompatible"), (None, "absent")):
            with self.subTest(policy_id=policy_id):
                klippy = FakeKlippyAPI(ready_payload(policy_id=policy_id))
                component = component_module.load_component(FakeConfig(FakeServer(klippy)))
                calibration = asyncio.run(component._handle_snapshot(object()))["modules"][
                    "z_calibration"
                ]["state"]["calibration"]
                self.assertFalse(calibration["offset_hook_enabled"])
                self.assertEqual(calibration["offset_hook_status"], "policy_unavailable")
                self.assertEqual(calibration["integration"]["policy_status"], expected)

    def test_reconcile_endpoint_is_authenticated_and_read_only(self) -> None:
        klippy = FakeKlippyAPI(ready_payload())
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        endpoint = next(
            ep
            for ep in server.endpoints
            if ep["endpoint"] == component_module.Z_RECONCILE_ENDPOINT
        )
        result = asyncio.run(endpoint["callback"](object()))
        self.assertTrue(endpoint["auth_required"])
        self.assertEqual(
            result["module"]["state"]["offset"]["provenance_status"], "reconciled"
        )
        self.assertEqual(klippy.gcode, [])

    def test_malformed_klippy_state_degrades_module_not_platform(self) -> None:
        malformed = ready_payload()
        malformed["gcode_move"]["homing_origin"] = [0.0, 0.0]
        server = FakeServer(FakeKlippyAPI(malformed))
        component = component_module.load_component(FakeConfig(server))
        snapshot = asyncio.run(component._handle_snapshot(object()))
        self.assertEqual(snapshot["backend"]["health"], "ok")
        module = snapshot["modules"]["z_calibration"]
        self.assertFalse(module["available"])
        self.assertEqual(module["state"]["safety"]["last_error"], "klippy_query_failed")
        self.assertIsNone(module["state"]["offset"]["effective"])

    def test_klippy_query_exception_clears_stale_effective_state(self) -> None:
        server = FakeServer(FakeKlippyAPI(RuntimeError("disconnect")))
        component = component_module.load_component(FakeConfig(server))
        component._z_offsets = component_module.zcore.OffsetComposition(
            persistent_user=-0.03, auto_alignment=0.01
        )
        snapshot = asyncio.run(component._handle_snapshot(object()))
        offset = snapshot["modules"]["z_calibration"]["state"]["offset"]
        self.assertIsNone(offset["effective"])
        self.assertEqual(offset["provenance_status"], "unavailable")
        self.assertAlmostEqual(offset["known_total"], 0.0)

    def test_diagnostics_records_provenance_not_write_action(self) -> None:
        server = FakeServer(FakeKlippyAPI(ready_payload()))
        component = component_module.load_component(FakeConfig(server))
        asyncio.run(component._handle_z_reconcile(object()))
        result = asyncio.run(component._handle_z_diagnostics(object()))
        self.assertGreaterEqual(len(result["events"]), 1)
        event = result["events"][-1]
        self.assertEqual(event["event_type"], "offset_provenance_reconciled")
        self.assertEqual(event["payload"]["provenance_status"], "reconciled")
        self.assertNotIn("target", event["payload"])

    def test_disconnect_and_job_events_only_invalidate_observed_state(self) -> None:
        klippy = FakeKlippyAPI(ready_payload())
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        asyncio.run(component._handle_snapshot(object()))
        server.event_handlers["server:klippy_disconnect"]()
        snapshot = component.get_snapshot()["modules"]["z_calibration"]
        self.assertFalse(snapshot["available"])
        self.assertEqual(snapshot["state"]["safety"]["last_error"], "klippy_disconnected")
        before = component.get_snapshot()["revision"]
        server.event_handlers["job_state:state_changed"]("cancelled", {}, {"state": "cancelled"})
        self.assertEqual(component.get_snapshot()["revision"], before + 1)
        self.assertEqual(klippy.gcode, [])

    def test_ready_event_refreshes_observer_without_writes(self) -> None:
        klippy = FakeKlippyAPI(ready_payload())
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        asyncio.run(server.event_handlers["server:klippy_ready"]())
        self.assertTrue(component.get_snapshot()["modules"]["z_calibration"]["available"])
        self.assertEqual(klippy.gcode, [])

    def test_backend_version_matches_repository_version(self) -> None:
        repository_version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(component_module.BACKEND_VERSION, repository_version)

    def test_revision_increment_and_invalidation_event(self) -> None:
        self.assertEqual(self.component.get_snapshot()["revision"], 1)
        revision = self.component.invalidate_snapshot()
        self.assertEqual(revision, 2)
        self.assertEqual(
            self.server.events,
            [(component_module.SNAPSHOT_CHANGED_EVENT, ({"revision": 2},))],
        )

    def test_constructor_does_not_query_klippy_or_perform_io(self) -> None:
        klippy = FakeKlippyAPI(ready_payload())
        component_module.load_component(FakeConfig(FakeServer(klippy)))
        self.assertEqual(klippy.queries, [])
        self.assertEqual(klippy.gcode, [])

    def test_component_source_contains_no_production_z_write_or_motion_command(self) -> None:
        source = COMPONENT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("run_gcode", source)
        self.assertNotIn("SET_GCODE_OFFSET Z=", source)
        self.assertNotIn("PROBE ", source)
        self.assertNotIn("G0 ", source)
        self.assertNotIn("G1 ", source)


if __name__ == "__main__":
    unittest.main()
