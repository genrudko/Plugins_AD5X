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


class FakeSpoolman:
    def __init__(self, spool_id=None, connected=True):
        self.spool_id = spool_id
        self.ws_connected = connected
        self.calls = []

    def connected(self):
        return self.ws_connected

    def set_active_spool(self, spool_id):
        self.calls.append(spool_id)
        self.spool_id = spool_id


class FakeServer:
    def __init__(self, klippy_apis, spoolman=None):
        self.klippy_apis = klippy_apis
        self.spoolman = spoolman
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
        if name == "klippy_apis":
            return self.klippy_apis
        if name == "spoolman" and self.spoolman is not None:
            return self.spoolman
        raise KeyError(name)

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
SAVE_VARIABLES = "save_variables"


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
    def make_component(self, objects=None, initial=None, spoolman=None):
        api = FakeKlippyAPIs(objects, initial)
        server = FakeServer(api, spoolman=spoolman)
        component = component_module.load_component(FakeConfig(server))
        return component, server, api

    def make_live_component(self, print_state="standby", head=True, spoolman=None):
        return self.make_component(
            objects=["ad5x_ifs", HEAD],
            initial=live_initial(print_state, head),
            spoolman=spoolman,
        )

    def test_registers_lifecycle_and_action_endpoint_without_polling(self):
        _component, server, _api = self.make_component()
        self.assertEqual(
            set(server.handlers),
            {
                "server:klippy_ready",
                "server:klippy_disconnect",
                "spoolman:spoolman_status_changed",
                "spoolman:active_spool_set",
            },
        )
        self.assertEqual(
            server.endpoints[component_module.IFS_ACTION_ENDPOINT][0], RequestType.POST
        )
        self.assertFalse(hasattr(server, "timer"))

    def test_provider_print_leveling_is_read_only_optional_snapshot_state(self):
        initial = live_initial()
        initial[SAVE_VARIABLES] = {"variables": {"print_leveling": 1}}
        component, server, api = self.make_component(objects=["ad5x_ifs", HEAD, SAVE_VARIABLES], initial=initial)
        asyncio.run(server.handlers["server:klippy_ready"]())
        self.assertEqual(api.subscription[SAVE_VARIABLES], ["variables"])
        settings = component.get_snapshot()["modules"]["ifs"]["provider"]["settings"]
        self.assertEqual(settings["print_leveling"], 1)
        self.assertTrue(settings["print_leveling_known"])
        self.assertEqual(settings["source"], "save_variables")
        self.assertTrue(settings["read_only"])
        self.assertEqual(api.gcodes, [])

    def test_provider_print_leveling_updates_fail_soft_without_write(self):
        initial = live_initial()
        initial[SAVE_VARIABLES] = {"variables": {"print_leveling": 0}}
        component, server, api = self.make_component(objects=["ad5x_ifs", HEAD, SAVE_VARIABLES], initial=initial)
        asyncio.run(server.handlers["server:klippy_ready"]())
        asyncio.run(component._on_status_update({SAVE_VARIABLES: {"variables": {"print_leveling": 1}}}, 1.0))
        settings = component.get_snapshot()["modules"]["ifs"]["provider"]["settings"]
        self.assertEqual(settings["print_leveling"], 1)
        self.assertTrue(settings["print_leveling_known"])
        asyncio.run(component._on_status_update({SAVE_VARIABLES: {"variables": {"print_leveling": 2}}}, 2.0))
        settings = component.get_snapshot()["modules"]["ifs"]["provider"]["settings"]
        self.assertIsNone(settings["print_leveling"])
        self.assertFalse(settings["print_leveling_known"])
        self.assertEqual(api.gcodes, [])

    def test_spoolman_is_optional_and_absent_does_not_reduce_ifs(self):
        component, server, _api = self.make_live_component(spoolman=None)
        asyncio.run(server.handlers["server:klippy_ready"]())
        module = component.get_snapshot()["modules"]["ifs"]
        self.assertFalse(module["capabilities"]["integrations"]["spoolman"])
        self.assertFalse(module["spoolman"]["configured"])
        self.assertTrue(module["available"])

    def test_spoolman_configured_is_exposed_as_optional_capability(self):
        spoolman = FakeSpoolman()
        component, server, _api = self.make_live_component(spoolman=spoolman)
        asyncio.run(server.handlers["server:klippy_ready"]())
        module = component.get_snapshot()["modules"]["ifs"]
        self.assertTrue(module["capabilities"]["integrations"]["spoolman"])
        self.assertTrue(module["capabilities"]["spoolman"]["optional"])
        self.assertTrue(module["capabilities"]["spoolman"]["consumption_tracking"])
        self.assertTrue(module["spoolman"]["configured"])
        self.assertTrue(module["spoolman"]["connected"])

    def test_active_ifs_slot_drives_native_moonraker_spoolman_tracking(self):
        spoolman = FakeSpoolman()
        component, server, _api = self.make_live_component(spoolman=spoolman)
        asyncio.run(server.handlers["server:klippy_ready"]())
        component._ifs_metadata = {
            "active_slot": 1,
            "slots": {
                1: {
                    "spool": {
                        "source": "spoolman",
                        "spoolman_spool_id": 42,
                        "spoolman_filament_id": 77,
                    }
                }
            },
        }
        component._set_ifs_module(component._compose_ifs_module())
        asyncio.run(component._sync_spoolman_active_tracking(component._ifs_module))
        self.assertEqual(spoolman.calls[-1], 42)
        self.assertEqual(spoolman.spool_id, 42)
        module = component.get_snapshot()["modules"]["ifs"]
        self.assertEqual(module["spoolman"]["tracking_slot"], 1)
        self.assertEqual(module["spoolman"]["tracking_spool_id"], 42)

        component._ifs_metadata = {
            "active_slot": 2,
            "slots": {
                2: {
                    "spool": {
                        "source": "spoolman",
                        "spoolman_spool_id": 99,
                    }
                }
            },
        }
        component._set_ifs_module(component._compose_ifs_module())
        asyncio.run(component._sync_spoolman_active_tracking(component._ifs_module))
        self.assertEqual(spoolman.calls[-1], 99)
        self.assertEqual(spoolman.spool_id, 99)

    def test_tracking_clears_when_toolhead_filament_is_not_confirmed(self):
        spoolman = FakeSpoolman(spool_id=42)
        component, server, _api = self.make_live_component(head=False, spoolman=spoolman)
        asyncio.run(server.handlers["server:klippy_ready"]())
        self.assertIsNone(spoolman.spool_id)
        self.assertIn(None, spoolman.calls)

    def test_tracking_does_not_repeat_same_native_active_spool_write(self):
        spoolman = FakeSpoolman(spool_id=42)
        component, server, _api = self.make_live_component(spoolman=spoolman)
        asyncio.run(server.handlers["server:klippy_ready"]())
        spoolman.calls.clear()
        component._ifs_metadata = {
            "active_slot": 1,
            "slots": {1: {"spool": {"spoolman_spool_id": 42}}},
        }
        component._set_ifs_module(component._compose_ifs_module())
        asyncio.run(component._sync_spoolman_active_tracking(component._ifs_module))
        self.assertEqual(spoolman.calls, [42])
        spoolman.calls.clear()
        asyncio.run(component._sync_spoolman_active_tracking(component._ifs_module))
        self.assertEqual(spoolman.calls, [])

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

    def test_native_display_suspends_ifs_actions_and_preview_without_gcode(self):
        native = {
            "ad5x_ifs": {
                "available": False,
                "state": "maintenance_suspended",
                "reason": "native_display_active",
                "provider_mode": "native_display",
                "maintenance_suspended": True,
                "state_code": 0,
                "active_slot": 0,
                "slots": [],
            },
            "print_stats": {"state": "standby"},
            HEAD: {"enabled": True, "filament_detected": False},
        }
        component, server, api = self.make_component(
            objects=["ad5x_ifs", HEAD], initial=native
        )
        asyncio.run(server.handlers["server:klippy_ready"]())
        module = component.get_snapshot()["modules"]["ifs"]
        self.assertFalse(module["available"])
        self.assertEqual(module["state"], "maintenance_suspended")
        self.assertEqual(module["provider_mode"], "native_display")
        self.assertTrue(module["maintenance_suspended"])
        self.assertFalse(module["provider"]["ifs_manager_supported"])
        self.assertEqual(module["write_blocked_reason"], "maintenance_suspended")
        self.assertFalse(module["operations"]["select_slot"])
        self.assertFalse(module["operations"]["load_slot"])
        self.assertFalse(module["operations"]["unload_slot"])
        self.assertFalse(module["operations"]["preview_job"])

        action = asyncio.run(
            component._handle_ifs_action(FakeRequest(action="load_slot", slot=1))
        )
        self.assertFalse(action["ok"])
        self.assertIn("suspended", action["error"])

        preview = asyncio.run(
            component._handle_ifs_job_preview(FakeRequest(filename="demo.gcode"))
        )
        self.assertFalse(preview["ok"])
        self.assertIn("suspended", preview["error"])
        self.assertEqual(api.gcodes, [])

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
        self.assertEqual(api.gcodes[-1], "IN_ZCOLOR SLOT=2 NAPR=0")

        result = asyncio.run(
            component._handle_ifs_action(FakeRequest(action="unload_slot", slot=1))
        )
        self.assertTrue(result["ok"])
        self.assertEqual(api.gcodes[-1], "IN_ZCOLOR SLOT=1 NAPR=1")

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
                self.assertNotIn("material", module["slots"][3])
                self.assertIsNone(module["slots"][3]["spool"]["spoolman_spool_id"])
                self.assertEqual(module["slots"][3]["spool"]["material"], "")
                self.assertEqual(module["slots"][3]["metadata_status"], "stale")
                self.assertEqual(module["slots"][3]["current_identity_status"], "empty")
                self.assertTrue(module["slots"][3]["stale_metadata_available"])
        finally:
            component_module.FFCONFIG_PATH = old_ffconfig
            component_module.FILE_MAPPING_PATH = old_mapping

    def test_startup_empty_slot_clears_stale_persisted_binding(self):
        component, server, api = self.make_live_component()
        store = {
            "schema_version": "1.0",
            "slots": {"4": {
                "spool": {"source": "spoolman", "name": "Gone", "spoolman_spool_id": 88},
                "appearance": {"colors": ["#112233"], "finish": "standard"},
            }},
            "identity_invalidated_slots": [],
        }
        def read_store():
            return json.loads(json.dumps(store)), {"status": "ok", "error": ""}
        def write_store(value):
            store.clear(); store.update(json.loads(json.dumps(value)))
        component._read_manual_metadata_store_sync = read_store
        component._write_manual_metadata_store_sync = write_store
        asyncio.run(server.handlers["server:klippy_ready"]())
        self.assertNotIn("4", store["slots"])
        self.assertIn(4, store["identity_invalidated_slots"])
        slot4 = component.get_snapshot()["modules"]["ifs"]["slots"][3]
        self.assertEqual(slot4["current_identity_status"], "empty")
        self.assertIsNone(slot4["spool"]["spoolman_spool_id"])
        inserted = [dict(item) for item in READY["slots"]]
        inserted[3]["present"] = True
        asyncio.run(api.callback({"ad5x_ifs": {"slots": inserted}}, 3.0))
        slot4 = component.get_snapshot()["modules"]["ifs"]["slots"][3]
        self.assertEqual(slot4["current_identity_status"], "unassigned")
        self.assertIsNone(slot4["spool"]["spoolman_spool_id"])

    def test_physical_spool_removal_invalidates_binding_and_does_not_resurrect(self):
        component, server, api = self.make_live_component()
        store = {
            "schema_version": "1.0",
            "slots": {
                "2": {
                    "spool": {
                        "source": "spoolman",
                        "name": "Old spool",
                        "material": "PLA",
                        "spoolman_spool_id": 42,
                        "spoolman_filament_id": 77,
                    },
                    "appearance": {"colors": ["#AA0000"], "finish": "standard"},
                }
            },
            "identity_invalidated_slots": [],
        }

        def read_store():
            return json.loads(json.dumps(store)), {"status": "ok", "error": ""}

        def write_store(value):
            store.clear()
            store.update(json.loads(json.dumps(value)))

        component._read_manual_metadata_store_sync = read_store
        component._write_manual_metadata_store_sync = write_store
        asyncio.run(server.handlers["server:klippy_ready"]())
        slot2 = component.get_snapshot()["modules"]["ifs"]["slots"][1]
        self.assertEqual(slot2["spool"]["spoolman_spool_id"], 42)

        removed_slots = [dict(item) for item in READY["slots"]]
        removed_slots[1]["present"] = False
        asyncio.run(api.callback({"ad5x_ifs": {"slots": removed_slots}}, 1.0))
        self.assertNotIn("2", store["slots"])
        self.assertIn(2, store["identity_invalidated_slots"])
        slot2 = component.get_snapshot()["modules"]["ifs"]["slots"][1]
        self.assertFalse(slot2["present"])
        self.assertIsNone(slot2["spool"]["spoolman_spool_id"])
        self.assertEqual(slot2["current_identity_status"], "empty")

        inserted_slots = [dict(item) for item in removed_slots]
        inserted_slots[1]["present"] = True
        asyncio.run(api.callback({"ad5x_ifs": {"slots": inserted_slots}}, 2.0))
        slot2 = component.get_snapshot()["modules"]["ifs"]["slots"][1]
        self.assertTrue(slot2["present"])
        self.assertIsNone(slot2["spool"]["spoolman_spool_id"])
        self.assertEqual(slot2["current_identity_status"], "unassigned")

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
