from __future__ import annotations

import asyncio
import importlib.util
import json
import pathlib
import sys
import tempfile
import types
import unittest
from enum import Flag, auto

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x.py"


class RequestType(Flag):
    GET = auto()
    POST = auto()


class TransportType(Flag):
    HTTP = auto()
    WEBSOCKET = auto()


def load_module():
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
        "moonraker.components.plugins_ad5x", COMPONENT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


component_module = load_module()


class FakeKlippyAPIs:
    def __init__(self, objects=None, initial=None):
        self.objects = list(objects or [])
        self.initial = dict(initial or {})
        self.callback = None
        self.subscription = None
        self.gcodes = []
        self.query_result = {}

    async def get_object_list(self, default=None):
        return list(self.objects)

    async def subscribe_objects(self, objects, callback=None, default=None):
        self.subscription = objects
        self.callback = callback
        return dict(self.initial)

    async def query_objects(self, objects, default=None):
        return dict(self.query_result)

    async def run_gcode(self, script, default=None):
        self.gcodes.append(script)
        return "ok"


class FakeServer:
    def __init__(self, klippy_apis):
        self.klippy_apis = klippy_apis
        self.handlers = {}
        self.events = []
        self.endpoints = {}

    def register_endpoint(self, path, request_type, handler, **kwargs):
        self.endpoints[path] = (request_type, handler, kwargs)

    def register_notification(self, *_args, **_kwargs):
        pass

    def register_event_handler(self, event, callback):
        self.handlers[event] = callback

    def lookup_component(self, name):
        if name != "klippy_apis":
            raise KeyError(name)
        return self.klippy_apis

    def send_event(self, event, *args):
        self.events.append((event, args))


class FakeConfig:
    def __init__(self, server):
        self.server = server

    def get_server(self):
        return self.server


class FakeRequest:
    def __init__(self, **params):
        self.params = params

    def get_str(self, name):
        return str(self.params[name])

    def get_int(self, name):
        return int(self.params[name])


READY = {
    "available": True,
    "state": "ready",
    "state_code": 5,
    "active_slot": 1,
    "slots": [
        {"slot": 1, "present": True, "stall": False},
        {"slot": 2, "present": True, "stall": False},
        {"slot": 3, "present": True, "stall": False},
        {"slot": 4, "present": False, "stall": False},
    ],
    "silk_mask": 7,
    "raw_channel": 0,
    "insert_slot": 0,
    "need_insert": False,
    "stall": False,
    "stall_mask": 0,
}

HEAD = "filament_switch_sensor head_switch_sensor"


def live_initial(print_state="standby", head=True):
    return {
        "ad5x_ifs": dict(READY),
        "print_stats": {"state": print_state},
        HEAD: {"enabled": True, "filament_detected": head},
    }


def assert_ready_core(testcase, module):
    # Manager v1 is additive: preserve every legacy field/value while allowing
    # normalized spool/appearance/permission fields to coexist inside slots.
    for key, value in READY.items():
        if key != "slots":
            testcase.assertEqual(module[key], value)
            continue
        testcase.assertEqual(len(module["slots"]), len(value))
        for expected, actual in zip(value, module["slots"]):
            for field, expected_value in expected.items():
                testcase.assertEqual(actual[field], expected_value)

    testcase.assertEqual(module["print_state"], "standby")
    testcase.assertTrue(module["filament_at_toolhead"])
    testcase.assertEqual(module["operation"]["state"], "idle")
    testcase.assertTrue(module["operations"]["select_slot"])
    testcase.assertTrue(module["operations"]["load_slot"])
    testcase.assertTrue(module["operations"]["unload_slot"])
    testcase.assertEqual(module["capabilities"]["schema_version"], "1.0")
    testcase.assertEqual(module["capabilities"]["slot_count"], 4)


class PluginsAD5XIFSBackendTests(unittest.TestCase):
    def make_component(self, objects=None, initial=None):
        api = FakeKlippyAPIs(objects, initial)
        server = FakeServer(api)
        component = component_module.load_component(FakeConfig(server))
        return component, server, api

    def make_live_component(self, print_state="standby", head=True):
        return self.make_component(
            objects=["ad5x_ifs", HEAD],
            initial=live_initial(print_state, head),
        )

    def test_registers_lifecycle_and_action_endpoint_without_polling(self):
        _component, server, _api = self.make_component()
        self.assertEqual(
            set(server.handlers), {"server:klippy_ready", "server:klippy_disconnect"}
        )
        self.assertEqual(
            server.endpoints[component_module.IFS_ACTION_ENDPOINT][0], RequestType.POST
        )
        self.assertFalse(hasattr(server, "timer"))

    def test_missing_bridge_is_safe_and_explicit(self):
        component, server, _api = self.make_component(objects=[])
        asyncio.run(server.handlers["server:klippy_ready"]())
        module = component.get_snapshot()["modules"]["ifs"]
        self.assertFalse(module["available"])
        self.assertEqual(module["reason"], "bridge_not_loaded")
        self.assertEqual(module["capabilities"]["schema_version"], "1.0")
        self.assertEqual(component.get_snapshot()["revision"], 2)

    def test_initial_bridge_status_enters_snapshot_with_aux_state(self):
        component, server, api = self.make_live_component()
        asyncio.run(server.handlers["server:klippy_ready"]())
        self.assertEqual(
            api.subscription,
            {
                "ad5x_ifs": None,
                "print_stats": ["state"],
                HEAD: ["enabled", "filament_detected"],
            },
        )
        assert_ready_core(self, component.get_snapshot()["modules"]["ifs"])

    def test_semantic_update_invalidates_once(self):
        component, server, api = self.make_live_component()
        asyncio.run(server.handlers["server:klippy_ready"]())
        server.events.clear()
        revision = component.get_snapshot()["revision"]
        asyncio.run(api.callback({"ad5x_ifs": {"stall": True, "stall_mask": 1}}, 1.0))
        self.assertEqual(component.get_snapshot()["revision"], revision + 1)
        self.assertTrue(component.get_snapshot()["modules"]["ifs"]["stall"])
        self.assertEqual(len(server.events), 1)
        asyncio.run(api.callback({"ad5x_ifs": {"stall": True, "stall_mask": 1}}, 2.0))
        self.assertEqual(component.get_snapshot()["revision"], revision + 1)
        self.assertEqual(len(server.events), 1)

    def test_aux_updates_are_push_normalized(self):
        component, server, api = self.make_live_component()
        asyncio.run(server.handlers["server:klippy_ready"]())
        asyncio.run(
            api.callback(
                {
                    "print_stats": {"state": "paused"},
                    HEAD: {"enabled": True, "filament_detected": False},
                },
                2.0,
            )
        )
        module = component.get_snapshot()["modules"]["ifs"]
        self.assertEqual(module["print_state"], "paused")
        self.assertFalse(module["filament_at_toolhead"])
        self.assertEqual(module["write_blocked_reason"], "unsafe_print_state")
        for slot in module["slots"]:
            self.assertEqual(slot["permissions"]["blocked_reason"], "unsafe_print_state")

    def test_disconnect_marks_module_unavailable(self):
        component, server, _api = self.make_live_component()
        asyncio.run(server.handlers["server:klippy_ready"]())
        revision = component.get_snapshot()["revision"]
        asyncio.run(server.handlers["server:klippy_disconnect"]())
        module = component.get_snapshot()["modules"]["ifs"]
        self.assertFalse(module["available"])
        self.assertEqual(module["reason"], "klippy_disconnected")
        self.assertEqual(module["write_blocked_reason"], "ifs_not_ready")
        self.assertEqual(component.get_snapshot()["revision"], revision + 1)

    def test_select_load_and_active_unload_translate_to_zmod_commands(self):
        component, server, api = self.make_live_component()
        asyncio.run(server.handlers["server:klippy_ready"]())

        result = asyncio.run(
            component._handle_ifs_action(FakeRequest(action="select_slot", slot=2))
        )
        self.assertTrue(result["ok"])
        self.assertEqual(api.gcodes[-1], "SET_EXTRUDER_SLOT SLOT=2")

        result = asyncio.run(
            component._handle_ifs_action(FakeRequest(action="load_slot", slot=2))
        )
        self.assertTrue(result["ok"])
        self.assertEqual(api.gcodes[-1], "INSERT_PRUTOK_IFS PRUTOK=2")

        result = asyncio.run(
            component._handle_ifs_action(FakeRequest(action="unload_slot", slot=1))
        )
        self.assertTrue(result["ok"])
        self.assertEqual(api.gcodes[-1], "_IFS_REMOVE_CURRENT_PRUTOK")

    def test_paused_and_printing_fail_closed_without_gcode(self):
        for state in ("paused", "printing", "unknown"):
            with self.subTest(state=state):
                component, server, api = self.make_live_component(print_state=state)
                asyncio.run(server.handlers["server:klippy_ready"]())
                result = asyncio.run(
                    component._handle_ifs_action(FakeRequest(action="load_slot", slot=2))
                )
                self.assertFalse(result["ok"])
                self.assertIn("blocked", result["error"])
                self.assertEqual(api.gcodes, [])

    def test_unload_non_active_or_unconfirmed_head_fails_closed(self):
        component, server, api = self.make_live_component(head=True)
        asyncio.run(server.handlers["server:klippy_ready"]())
        result = asyncio.run(
            component._handle_ifs_action(FakeRequest(action="unload_slot", slot=2))
        )
        self.assertFalse(result["ok"])
        self.assertEqual(api.gcodes, [])

        component, server, api = self.make_live_component(head=False)
        asyncio.run(server.handlers["server:klippy_ready"]())
        result = asyncio.run(
            component._handle_ifs_action(FakeRequest(action="unload_slot", slot=1))
        )
        self.assertFalse(result["ok"])
        self.assertIn("Toolhead", result["error"])
        self.assertEqual(api.gcodes, [])

    def test_empty_slot_cannot_select_or_load(self):
        component, server, api = self.make_live_component()
        asyncio.run(server.handlers["server:klippy_ready"]())
        for action in ("select_slot", "load_slot"):
            result = asyncio.run(
                component._handle_ifs_action(FakeRequest(action=action, slot=4))
            )
            self.assertFalse(result["ok"])
        self.assertEqual(api.gcodes, [])

    def test_metadata_enriches_slots_active_slot_and_tool_mapping(self):
        old_ffconfig = component_module.FFCONFIG_PATH
        old_mapping = component_module.FILE_MAPPING_PATH
        try:
            with tempfile.TemporaryDirectory() as td:
                root = pathlib.Path(td)
                ffconfig = root / "Adventurer5M.json"
                mapping = root / "file.json"
                ffconfig.write_text(
                    json.dumps(
                        {
                            "FFMInfo": {
                                "channel": 3,
                                "ffmType1": "PETG",
                                "ffmColor1": "#161616",
                                "ffmType2": "PLA",
                                "ffmColor2": "#161616",
                                "ffmType3": "PLA",
                                "ffmColor3": "#F330F9",
                                "ffmType4": "TPU",
                                "ffmColor4": "#161616",
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                mapping.write_text(json.dumps([1, 1, 1, 4]), encoding="utf-8")
                component_module.FFCONFIG_PATH = str(ffconfig)
                component_module.FILE_MAPPING_PATH = str(mapping)

                component, server, _api = self.make_live_component()
                asyncio.run(server.handlers["server:klippy_ready"]())
                module = component.get_snapshot()["modules"]["ifs"]

                self.assertEqual(module["runtime_active_slot"], 1)
                self.assertEqual(module["active_slot"], 3)
                self.assertEqual(module["tool_mapping"], [1, 1, 1, 4])
                self.assertEqual(module["slots"][0]["material"], "PETG")
                self.assertEqual(module["slots"][0]["spool"]["material"], "PETG")
                self.assertEqual(module["slots"][0]["spool"]["source"], "flashforge")
                self.assertEqual(module["slots"][2]["color"], "#F330F9")
                self.assertEqual(module["slots"][2]["appearance"]["colors"], ["#F330F9"])
                self.assertFalse(module["slots"][3]["present"])
                self.assertEqual(module["slots"][3]["material"], "TPU")
                self.assertEqual(module["slots"][3]["metadata_status"], "stale")
        finally:
            component_module.FFCONFIG_PATH = old_ffconfig
            component_module.FILE_MAPPING_PATH = old_mapping

    def test_snapshot_request_refreshes_metadata_without_polling(self):
        old_ffconfig = component_module.FFCONFIG_PATH
        old_mapping = component_module.FILE_MAPPING_PATH
        try:
            with tempfile.TemporaryDirectory() as td:
                root = pathlib.Path(td)
                ffconfig = root / "Adventurer5M.json"
                mapping = root / "file.json"
                ffconfig.write_text(
                    json.dumps(
                        {
                            "FFMInfo": {
                                "channel": 1,
                                "ffmType1": "PLA",
                                "ffmColor1": "#111111",
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                mapping.write_text(json.dumps([1]), encoding="utf-8")
                component_module.FFCONFIG_PATH = str(ffconfig)
                component_module.FILE_MAPPING_PATH = str(mapping)

                component, server, _api = self.make_live_component()
                asyncio.run(server.handlers["server:klippy_ready"]())
                revision = component.get_snapshot()["revision"]

                data = json.loads(ffconfig.read_text(encoding="utf-8"))
                data["FFMInfo"]["ffmType1"] = "ABS"
                ffconfig.write_text(json.dumps(data), encoding="utf-8")

                snapshot = asyncio.run(component._handle_snapshot(None))
                slot = snapshot["modules"]["ifs"]["slots"][0]
                self.assertEqual(slot["material"], "ABS")
                self.assertEqual(slot["spool"]["material"], "ABS")
                self.assertEqual(snapshot["revision"], revision + 1)
        finally:
            component_module.FFCONFIG_PATH = old_ffconfig
            component_module.FILE_MAPPING_PATH = old_mapping

    def test_invalid_metadata_fails_soft_and_preserves_live_state(self):
        old_ffconfig = component_module.FFCONFIG_PATH
        old_mapping = component_module.FILE_MAPPING_PATH
        try:
            with tempfile.TemporaryDirectory() as td:
                root = pathlib.Path(td)
                ffconfig = root / "Adventurer5M.json"
                mapping = root / "file.json"
                ffconfig.write_text("not-json", encoding="utf-8")
                mapping.write_text(json.dumps([0, 99]), encoding="utf-8")
                component_module.FFCONFIG_PATH = str(ffconfig)
                component_module.FILE_MAPPING_PATH = str(mapping)

                component, server, _api = self.make_live_component()
                asyncio.run(server.handlers["server:klippy_ready"]())
                module = component.get_snapshot()["modules"]["ifs"]
                assert_ready_core(self, module)
        finally:
            component_module.FFCONFIG_PATH = old_ffconfig
            component_module.FILE_MAPPING_PATH = old_mapping


if __name__ == "__main__":
    unittest.main()
