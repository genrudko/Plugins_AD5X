from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"


def load_model():
    spec = importlib.util.spec_from_file_location("plugins_ad5x_ifs_contract_model", MODEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load IFS model")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


model = load_model()

READY_RAW = {
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


def idle_operation():
    return {"state": "idle", "action": "", "slot": 0, "error": ""}


class IFSManagerContractTests(unittest.TestCase):
    def test_real_ad5x_shape_is_additively_normalized(self):
        metadata = {
            "active_slot": 1,
            "tool_mapping": [1, 1, 1, 4],
            "slots": {
                1: {"material": "PETG", "color": "#161616"},
                2: {"material": "PLA", "color": "#161616"},
                3: {"material": "PLA", "color": "#F330F9"},
                4: {"material": "TPU", "color": "#161616"},
            },
        }
        module = model.normalize_module(
            READY_RAW,
            metadata,
            print_state="standby",
            filament_at_toolhead=True,
            operation=idle_operation(),
        )

        self.assertEqual(module["active_slot"], 1)
        self.assertEqual(module["runtime_active_slot"], 1)
        self.assertEqual(module["tool_mapping"], [1, 1, 1, 4])
        self.assertEqual(module["write_blocked_reason"], "")
        self.assertEqual(module["capabilities"]["schema_version"], "1.0")

        slot1, slot2, slot3, slot4 = module["slots"]
        self.assertEqual(slot1["spool"]["material"], "PETG")
        self.assertEqual(slot1["appearance"]["colors"], ["#161616"])
        self.assertTrue(slot1["active"])
        self.assertTrue(slot1["permissions"]["unload_slot"])

        self.assertEqual(slot2["spool"]["material"], "PLA")
        self.assertTrue(slot2["permissions"]["select_slot"])
        self.assertTrue(slot2["permissions"]["load_slot"])

        self.assertEqual(slot3["appearance"]["colors"], ["#F330F9"])

        self.assertFalse(slot4["present"])
        self.assertEqual(slot4["metadata_status"], "stale")
        self.assertFalse(slot4["permissions"]["select_slot"])
        self.assertFalse(slot4["permissions"]["load_slot"])

        # Current KlipperScreen proof remains compatible during migration.
        self.assertEqual(slot1["material"], "PETG")
        self.assertEqual(slot1["color"], "#161616")
        self.assertTrue(module["operations"]["select_slot"])
        self.assertTrue(module["operations"]["manage"])

    def test_rich_multicolor_finish_is_frontend_neutral(self):
        metadata = {
            "active_slot": 1,
            "slots": {
                3: {
                    "spool": {
                        "source": "manual",
                        "brand": "ERYONE",
                        "series": "Silk",
                        "name": "Triple Color",
                        "material": "PLA",
                    },
                    "appearance": {
                        "color_mode": "tricolor",
                        "colors": ["#F330F9", "#27C4F4", "#FFD43B"],
                        "finish": "silk",
                    },
                }
            },
        }
        module = model.normalize_module(
            READY_RAW,
            metadata,
            print_state="standby",
            filament_at_toolhead=True,
            operation=idle_operation(),
        )
        slot3 = module["slots"][2]
        self.assertEqual(slot3["spool"]["source"], "manual")
        self.assertEqual(slot3["spool"]["brand"], "ERYONE")
        self.assertEqual(slot3["appearance"]["color_mode"], "tricolor")
        self.assertEqual(
            slot3["appearance"]["colors"],
            ["#F330F9", "#27C4F4", "#FFD43B"],
        )
        self.assertEqual(slot3["appearance"]["finish"], "silk")

    def test_capability_schema_does_not_pretend_unimplemented_integrations_exist(self):
        caps = model.get_ifs_capabilities()
        self.assertTrue(caps["metadata_schema"]["spool_fields"])
        self.assertTrue(caps["metadata_schema"]["multi_color"])
        self.assertTrue(caps["metadata_schema"]["finish"])
        self.assertTrue(caps["integrations"]["flashforge"])
        self.assertTrue(caps["integrations"]["manual_store"])
        self.assertFalse(caps["integrations"]["spoolman"])
        self.assertFalse(caps["integrations"]["slicer"])
        self.assertFalse(caps["integrations"]["rfid"])
        self.assertFalse(caps["mapping"]["endless_spool"])

    def test_paused_print_and_running_operation_fail_closed(self):
        paused = model.normalize_module(
            READY_RAW,
            {"active_slot": 1},
            print_state="paused",
            filament_at_toolhead=True,
            operation=idle_operation(),
        )
        self.assertEqual(paused["write_blocked_reason"], "unsafe_print_state")
        for slot in paused["slots"]:
            self.assertEqual(slot["permissions"]["blocked_reason"], "unsafe_print_state")
            self.assertFalse(slot["permissions"]["load_slot"])
            self.assertFalse(slot["permissions"]["unload_slot"])

        busy = model.normalize_module(
            READY_RAW,
            {"active_slot": 1},
            print_state="standby",
            filament_at_toolhead=True,
            operation={"state": "running", "action": "load_slot", "slot": 2, "error": ""},
        )
        self.assertEqual(busy["write_blocked_reason"], "operation_in_progress")
        for slot in busy["slots"]:
            self.assertEqual(slot["permissions"]["blocked_reason"], "operation_in_progress")

    def test_diagnostics_do_not_compete_with_operational_truth(self):
        raw = dict(READY_RAW)
        raw["active_slot"] = 0
        metadata = {"active_slot": 1, "tool_mapping": [1, 1, 1, 4]}
        module = model.normalize_module(
            raw,
            metadata,
            print_state="standby",
            filament_at_toolhead=True,
            operation=idle_operation(),
        )
        self.assertEqual(module["active_slot"], 1)
        self.assertEqual(module["runtime_active_slot"], 0)
        self.assertEqual(module["diagnostics"]["runtime_active_slot"], 0)
        self.assertEqual(module["diagnostics"]["raw_channel"], 0)
        self.assertEqual(module["tool_mapping"], [1, 1, 1, 4])


if __name__ == "__main__":
    unittest.main()
