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


class FakeGcode:
    def __init__(self):
        self.commands = {}

    def register_command(self, name, callback):
        self.commands[name] = callback


class FakeZmodColor:
    def __init__(self):
        self.file_colors = [(9, "#ABCDEF", "OLD")]
        self.calls = []

    def get_used_colors(self, gcmd):
        self.calls.append(("scan", gcmd.get("FILENAME", "")))
        return [
            (0, "#f330f9", "pla"),
            (1, "#161616", "petg"),
        ]

    def get_printer_data_detail(self):
        self.calls.append(("detail",))
        return 200, {"fake": True}

    def parse_printer_response(self, response):
        self.calls.append(("parse", response))
        return [
            {"ID": "1", "Material": "PETG", "Color": "dark", "HEX": "161616"},
            {"ID": "2", "Material": "PLA", "Color": "magenta", "HEX": "F330F9"},
            {"ID": "3", "Material": "PLA", "Color": "blue", "HEX": "27C4F4"},
        ]

    def get_auto_tool_assignments(
        self, gcmd, orig_tools, raw_slots, output_text, one_based_indexes
    ):
        self.calls.append(("assign", list(raw_slots), one_based_indexes))
        self.assert_preview_file_colors = list(self.file_colors)
        orig_tools[0] = 2
        orig_tools[1] = 1
        output_text.append("// canonical Z-Mod assignment")
        return bridge_module.AUTO_ASSIGN_ANY_SUCCESS | bridge_module.AUTO_ASSIGN_COLOR_WEAK


class FakePrinter:
    def __init__(self):
        self.handlers = {}
        self.gcode = FakeGcode()
        self.zmod_color = FakeZmodColor()
        self.objects = {
            "gcode": self.gcode,
            "zmod_ifs": FakeZmodIfs(),
            "zmod_color": self.zmod_color,
        }

    def register_event_handler(self, event, callback):
        self.handlers[event] = callback

    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)


class FakeConfig:
    def __init__(self, printer):
        self.printer = printer

    def get_printer(self):
        return self.printer


class FakeCommand:
    def __init__(self, filename):
        self.filename = filename
        self.responses = []

    def get(self, name, default=None):
        return self.filename if name == "FILENAME" else default

    def respond_raw(self, message):
        self.responses.append(str(message))

    @staticmethod
    def error(message):
        return ValueError(str(message))


class AD5XIFSBridgeTests(unittest.TestCase):
    def setUp(self):
        self.printer = FakePrinter()
        self.bridge = bridge_module.load_config(FakeConfig(self.printer))

    def test_registers_lifecycle_handlers_and_preview_command(self):
        self.assertEqual(
            set(self.printer.handlers),
            {"klippy:ready", "klippy:disconnect", "klippy:shutdown"},
        )
        self.assertIn(bridge_module.JOB_PREVIEW_COMMAND, self.printer.gcode.commands)

    def test_unavailable_before_ready(self):
        status = self.bridge.get_status(0.0)
        self.assertFalse(status["available"])
        self.assertEqual(status["slots"], [])
        self.assertFalse(status["job_preview"]["available"])

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

    def test_job_preview_delegates_scan_and_matching_to_zmod_without_persisting(self):
        self.printer.handlers["klippy:ready"]()
        original_file_colors = list(self.printer.zmod_color.file_colors)

        gcmd = FakeCommand("3mf/model/demo/Metadata/plate_1.gcode")
        self.bridge.cmd_JOB_PREVIEW(gcmd)

        preview = self.bridge.get_status(2.0)["job_preview"]
        self.assertTrue(preview["available"])
        self.assertEqual(preview["source"], "zmod")
        self.assertEqual(preview["filename"], gcmd.filename)
        self.assertEqual(
            preview["requirements"],
            [
                {"tool": 0, "color": "#F330F9", "material": "PLA"},
                {"tool": 1, "color": "#161616", "material": "PETG"},
            ],
        )
        self.assertEqual(
            preview["assignments"],
            [{"tool": 0, "slot": 2}, {"tool": 1, "slot": 1}],
        )
        self.assertEqual(preview["allowed_tool_count"], 2)
        self.assertEqual(preview["resolved_tool_map"], [2, 1])
        self.assertTrue(preview["auto_assign"]["any_success"])
        self.assertTrue(preview["auto_assign"]["weak_color"])
        self.assertFalse(preview["auto_assign"]["material_failure"])
        self.assertIn("canonical Z-Mod assignment", preview["messages"][-1])
        self.assertEqual(gcmd.responses, ["AD5X_IFS_JOB_PREVIEW_OK"])

        # Preview temporarily supplies file_colors to the canonical matcher and
        # restores the source object's previous state afterwards.
        self.assertEqual(
            self.printer.zmod_color.assert_preview_file_colors,
            [(0, "#f330f9", "pla"), (1, "#161616", "petg")],
        )
        self.assertEqual(self.printer.zmod_color.file_colors, original_file_colors)

    def test_job_preview_rejects_path_escape_before_calling_zmod(self):
        self.printer.handlers["klippy:ready"]()
        with self.assertRaises(ValueError):
            self.bridge.cmd_JOB_PREVIEW(FakeCommand("../config/printer.cfg"))
        self.assertEqual(self.printer.zmod_color.calls, [])

    def test_job_preview_fails_explicitly_without_zmod_color(self):
        self.printer.objects.pop("zmod_color")
        self.printer.handlers["klippy:ready"]()
        with self.assertRaises(ValueError):
            self.bridge.cmd_JOB_PREVIEW(FakeCommand("demo.gcode"))
        preview = self.bridge.get_status(2.0)["job_preview"]
        self.assertFalse(preview["available"])
        self.assertEqual(preview["error"], "zmod_color_unavailable")

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

    def test_disconnect_returns_unavailable_and_clears_preview(self):
        self.printer.handlers["klippy:ready"]()
        self.bridge.cmd_JOB_PREVIEW(FakeCommand("demo.gcode"))
        self.printer.handlers["klippy:disconnect"]()
        status = self.bridge.get_status(4.0)
        self.assertFalse(status["available"])
        self.assertFalse(status["job_preview"]["available"])
        self.assertEqual(status["job_preview"]["error"], "klippy_disconnected")


if __name__ == "__main__":
    unittest.main()
