from __future__ import annotations

import asyncio
import importlib.util
import pathlib
import sys
import types
import unittest
from enum import Flag, auto

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMPONENT_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x.py"


class RequestType(Flag):
    GET = auto()


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

    async def get_object_list(self, default=None):
        return list(self.objects)

    async def subscribe_objects(self, objects, callback=None, default=None):
        self.subscription = objects
        self.callback = callback
        return dict(self.initial)


class FakeServer:
    def __init__(self, klippy_apis):
        self.klippy_apis = klippy_apis
        self.handlers = {}
        self.events = []

    def register_endpoint(self, *_args, **_kwargs):
        pass

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


class PluginsAD5XIFSBackendTests(unittest.TestCase):
    def make_component(self, objects=None, initial=None):
        api = FakeKlippyAPIs(objects, initial)
        server = FakeServer(api)
        component = component_module.load_component(FakeConfig(server))
        return component, server, api

    def test_registers_klippy_lifecycle_handlers_without_polling(self):
        _component, server, _api = self.make_component()
        self.assertEqual(
            set(server.handlers), {"server:klippy_ready", "server:klippy_disconnect"}
        )
        self.assertFalse(hasattr(server, "timer"))

    def test_missing_bridge_is_safe_and_explicit(self):
        component, server, _api = self.make_component(objects=[])
        asyncio.run(server.handlers["server:klippy_ready"]())
        module = component.get_snapshot()["modules"]["ifs"]
        self.assertFalse(module["available"])
        self.assertEqual(module["reason"], "bridge_not_loaded")
        self.assertEqual(component.get_snapshot()["revision"], 2)

    def test_initial_bridge_status_enters_snapshot(self):
        component, server, api = self.make_component(
            objects=["ad5x_ifs"], initial={"ad5x_ifs": READY}
        )
        asyncio.run(server.handlers["server:klippy_ready"]())
        self.assertEqual(api.subscription, {"ad5x_ifs": None})
        self.assertEqual(component.get_snapshot()["modules"]["ifs"], READY)
        self.assertEqual(component.get_snapshot()["revision"], 2)

    def test_semantic_update_invalidates_once(self):
        component, server, api = self.make_component(
            objects=["ad5x_ifs"], initial={"ad5x_ifs": READY}
        )
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

    def test_disconnect_marks_module_unavailable(self):
        component, server, _api = self.make_component(
            objects=["ad5x_ifs"], initial={"ad5x_ifs": READY}
        )
        asyncio.run(server.handlers["server:klippy_ready"]())
        revision = component.get_snapshot()["revision"]
        asyncio.run(server.handlers["server:klippy_disconnect"]())
        module = component.get_snapshot()["modules"]["ifs"]
        self.assertFalse(module["available"])
        self.assertEqual(module["reason"], "klippy_disconnected")
        self.assertEqual(component.get_snapshot()["revision"], revision + 1)


if __name__ == "__main__":
    unittest.main()
