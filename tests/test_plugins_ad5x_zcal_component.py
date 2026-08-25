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
COMPONENT_PATH = COMPONENTS_PATH / "plugins_ad5x_zcal.py"


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
        "moonraker.components.plugins_ad5x_zcal", COMPONENT_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load standalone ZCal component")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


component_module = load_component_module()


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
    persistent: float = -0.03,
    auto: float = 0.014166,
    actual: float | None = None,
    requested_job: float = 99.0,
    print_state: str = "printing",
    homed_axes: str = "xyz",
    hook_commands: list[str] | None = None,
) -> Dict[str, Any]:
    if actual is None:
        actual = persistent + auto
    if hook_commands is None:
        hook_commands = [component_module.Z_CC_APPLY, component_module.Z_RC_GUARD]
    return {
        "gcode_move": {"homing_origin": [0.0, 0.0, actual]},
        "print_stats": {"state": print_state},
        "toolhead": {"homed_axes": homed_axes},
        "save_variables": {
            "variables": {
                "load_zoffset": 1,
                "mesh_test": 3,
                "print_leveling": 0,
                "gcode_offsets": {"z": persistent},
            }
        },
        "gcode_macro _TEST_POINT": {"temp_z_offset": auto},
        "gcode_macro _SCREEN": {"screen": False},
        "gcode_macro _START_PRINT": {
            "zzoffset": requested_job,
            "zforce_kamp": False,
            "zforce_leveling": False,
        },
        component_module.Z_RC_POLICY_OBJECT: {
            "policy_id": component_module.Z_RC_POLICY_ID,
            "max_auto_alignment": 0.12,
            "saved_profile": "auto",
            "saved_reference": -1.925833,
            "reference_tolerance": 0.0005,
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


class PluginsAD5XZCalComponentTests(unittest.TestCase):
    def endpoint(self, server: FakeServer, path: str) -> Dict[str, Any]:
        return next(ep for ep in server.endpoints if ep["endpoint"] == path)

    def test_registration_is_additive_and_does_not_claim_shared_snapshot(self) -> None:
        server = FakeServer()
        component_module.load_component(FakeConfig(server))
        endpoints = {entry["endpoint"]: entry for entry in server.endpoints}
        self.assertEqual(
            set(endpoints),
            {
                component_module.Z_SNAPSHOT_ENDPOINT,
                component_module.Z_RECONCILE_ENDPOINT,
                component_module.Z_DIAGNOSTICS_ENDPOINT,
            },
        )
        self.assertNotIn("/server/plugins_ad5x/snapshot", endpoints)
        self.assertEqual(
            endpoints[component_module.Z_SNAPSHOT_ENDPOINT]["request_types"],
            RequestType.GET,
        )
        self.assertEqual(
            endpoints[component_module.Z_RECONCILE_ENDPOINT]["request_types"],
            RequestType.POST,
        )
        self.assertEqual(
            endpoints[component_module.Z_DIAGNOSTICS_ENDPOINT]["request_types"],
            RequestType.GET,
        )
        for endpoint in endpoints.values():
            self.assertTrue(endpoint["auth_required"])
            self.assertEqual(
                endpoint["transports"], TransportType.HTTP | TransportType.WEBSOCKET
            )

    def test_accepted_live_composition_is_explained_without_writes(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(persistent=-0.03, auto=0.014166, actual=-0.015834)
        )
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        snapshot = asyncio.run(component._handle_snapshot(object()))
        state = snapshot["module"]["state"]
        offset = state["offset"]
        self.assertAlmostEqual(offset["persistent_user"], -0.03)
        self.assertAlmostEqual(offset["auto_alignment"], 0.014166)
        self.assertAlmostEqual(offset["slicer_job"], 0.0)
        self.assertAlmostEqual(offset["live_adjustment"], 0.0)
        self.assertAlmostEqual(offset["external_unknown"], 0.0)
        self.assertAlmostEqual(offset["effective"], -0.015834)
        self.assertEqual(offset["provenance_status"], "reconciled")
        self.assertIsNone(state["job"]["requested_slicer_z_offset"])
        self.assertEqual(
            state["job"]["slicer_z_offset_effect"],
            "ignored_by_zmod_global_offset_path",
        )
        self.assertTrue(state["runtime"]["effective_valid"])
        self.assertEqual(klippy.gcode, [])

    def test_zmod_99_sentinel_is_not_exposed_as_slicer_offset(self) -> None:
        klippy = FakeKlippyAPI(ready_payload(requested_job=99.0))
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        state = asyncio.run(component._handle_snapshot(object()))["module"]["state"]
        self.assertIsNone(state["job"]["requested_slicer_z_offset"])
        self.assertIsNone(state["provenance"]["requested_slicer_z_offset"])
        self.assertAlmostEqual(state["offset"]["slicer_job"], 0.0)

    def test_explicit_slicer_offset_is_observed_but_not_composed_on_global_path(self) -> None:
        klippy = FakeKlippyAPI(ready_payload(requested_job=0.05))
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        state = asyncio.run(component._handle_snapshot(object()))["module"]["state"]
        self.assertAlmostEqual(state["job"]["requested_slicer_z_offset"], 0.05)
        self.assertAlmostEqual(
            state["provenance"]["requested_slicer_z_offset"], 0.05
        )
        self.assertEqual(
            state["job"]["slicer_z_offset_effect"],
            "ignored_by_zmod_global_offset_path",
        )
        self.assertAlmostEqual(state["offset"]["slicer_job"], 0.0)

    def test_reconcile_is_read_only_and_records_diagnostic(self) -> None:
        klippy = FakeKlippyAPI(ready_payload())
        server = FakeServer(klippy)
        component = component_module.load_component(FakeConfig(server))
        result = asyncio.run(component._handle_z_reconcile(object()))
        state = result["module"]["state"]
        self.assertEqual(state["offset"]["provenance_status"], "reconciled")
        self.assertTrue(state["calibration"]["offset_hook_enabled"])
        self.assertEqual(state["calibration"]["offset_hook_status"], "loaded")
        diagnostics = asyncio.run(component._handle_z_diagnostics(object()))
        self.assertGreaterEqual(len(diagnostics["events"]), 1)
        self.assertEqual(
            diagnostics["events"][-1]["event_type"],
            "offset_provenance_reconciled",
        )
        self.assertEqual(klippy.gcode, [])

    def test_unattributed_residual_stays_external_unknown(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(persistent=-0.03, auto=0.014166, actual=-0.005834)
        )
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        state = asyncio.run(component._handle_snapshot(object()))["module"]["state"]
        self.assertAlmostEqual(state["offset"]["live_adjustment"], 0.0)
        self.assertAlmostEqual(state["offset"]["external_unknown"], 0.01)
        self.assertEqual(state["offset"]["provenance_status"], "external_unknown")

    def test_post_restart_unhomed_state_does_not_fabricate_effective_or_residual(self) -> None:
        klippy = FakeKlippyAPI(
            ready_payload(
                persistent=-0.016,
                auto=0.0,
                actual=0.0,
                print_state="standby",
                homed_axes="",
            )
        )
        component = component_module.load_component(FakeConfig(FakeServer(klippy)))
        state = asyncio.run(component._handle_snapshot(object()))["module"]["state"]
        self.assertAlmostEqual(state["offset"]["persistent_user"], -0.016)
        self.assertAlmostEqual(state["offset"]["live_adjustment"], 0.0)
        self.assertAlmostEqual(state["offset"]["external_unknown"], 0.0)
        self.assertIsNone(state["offset"]["effective"])
        self.assertEqual(state["offset"]["provenance_status"], "not_homed")
        self.assertEqual(state["provenance"]["status"], "not_homed")
        self.assertIsNone(state["provenance"]["actual_effective"])
        self.assertAlmostEqual(state["provenance"]["reported_homing_origin_z"], 0.0)
        self.assertEqual(
            state["provenance"]["sources"]["effective"],
            "unavailable:not_homed",
        )
        self.assertEqual(
            state["provenance"]["sources"]["live_adjustment"],
            "not_attributable:not_homed",
        )
        self.assertEqual(
            state["provenance"]["sources"]["external_unknown"],
            "not_evaluated:not_homed",
        )
        self.assertFalse(state["runtime"]["effective_valid"])
        self.assertIsNone(state["job"]["requested_slicer_z_offset"])

    def test_constructor_has_no_klippy_io(self) -> None:
        klippy = FakeKlippyAPI(ready_payload())
        component_module.load_component(FakeConfig(FakeServer(klippy)))
        self.assertEqual(klippy.queries, [])
        self.assertEqual(klippy.gcode, [])

    def test_source_contains_no_z_write_or_motion_command(self) -> None:
        source = COMPONENT_PATH.read_text(encoding="utf-8")
        self.assertNotIn("run_gcode", source)
        self.assertNotIn("SET_GCODE_OFFSET Z=", source)
        self.assertNotIn("PROBE ", source)
        self.assertNotIn("G0 ", source)
        self.assertNotIn("G1 ", source)


if __name__ == "__main__":
    unittest.main()
