from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "klipper" / "extras" / "ad5x_ifs.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ad5x_ifs", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load ad5x_ifs spec")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bridge_module = load_module()


class FakeIfsData:
    def __init__(self):
        self.cur_port = 1
        self.values = {
            "State": 5,
            "Ports": [True, True, True, False],
            "Silk": 7,
            "Chan": 0,
            "Insert": 0,
            "NeedInsert": False,
            "Stall": False,
            "stall_state": 0,
        }

    def get_values(self):
        return dict(self.values)


class FakeZmodIfs:
    def __init__(self):
        self.ifs_data = FakeIfsData()

    def get_ifs_status(self):
        return True


class FakePrinter:
    def __init__(self):
        self.handlers = {}
        self.objects = {"zmod_ifs": FakeZmodIfs()}

    def register_event_handler(self, event, callback):
        self.handlers[event] = callback

    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)


class FakeConfig:
    def __init__(self, printer):
        self.printer = printer

    def get_printer(self):
        return self.printer


class AD5XIFSBridgeTests(unittest.TestCase):
    def setUp(self):
        self.printer = FakePrinter()
        self.bridge = bridge_module.load_config(FakeConfig(self.printer))

    def test_registers_lifecycle_handlers(self):
        self.assertEqual(
            set(self.printer.handlers),
            {"klippy:ready", "klippy:disconnect", "klippy:shutdown"},
        )

    def test_unavailable_before_ready(self):
        status = self.bridge.get_status(0.0)
        self.assertFalse(status["available"])
        self.assertEqual(status["slots"], [])

    def test_ready_exports_normalized_zmod_state(self):
        self.printer.handlers["klippy:ready"]()
        status = self.bridge.get_status(1.0)
        self.assertTrue(status["available"])
        self.assertEqual(status["state"], "ready")
        self.assertEqual(status["state_code"], 5)
        self.assertEqual(status["active_slot"], 1)
        self.assertEqual(status["silk_mask"], 7)
        self.assertEqual(status["raw_channel"], 0)
        self.assertEqual(
            status["slots"],
            [
                {"slot": 1, "present": True, "stall": False},
                {"slot": 2, "present": True, "stall": False},
                {"slot": 3, "present": True, "stall": False},
                {"slot": 4, "present": False, "stall": False},
            ],
        )

    def test_stall_mask_is_per_slot(self):
        self.printer.handlers["klippy:ready"]()
        data = self.printer.objects["zmod_ifs"].ifs_data
        data.values["stall_state"] = 0b0101
        data.values["Stall"] = True
        status = self.bridge.get_status(2.0)
        self.assertTrue(status["stall"])
        self.assertEqual([s["stall"] for s in status["slots"]], [True, False, True, False])

    def test_raw_channel_is_not_used_as_active_slot(self):
        self.printer.handlers["klippy:ready"]()
        data = self.printer.objects["zmod_ifs"].ifs_data
        data.cur_port = 3
        data.values["Chan"] = 0
        status = self.bridge.get_status(3.0)
        self.assertEqual(status["active_slot"], 3)
        self.assertEqual(status["raw_channel"], 0)

    def test_disconnect_returns_unavailable(self):
        self.printer.handlers["klippy:ready"]()
        self.printer.handlers["klippy:disconnect"]()
        self.assertFalse(self.bridge.get_status(4.0)["available"])


if __name__ == "__main__":
    unittest.main()
