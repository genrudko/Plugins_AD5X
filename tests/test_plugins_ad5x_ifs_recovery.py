from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"

def load_model():
    spec = importlib.util.spec_from_file_location("plugins_ad5x_ifs_recovery_model", MODEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load IFS model")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

model = load_model()

class IFSRecoveryPreviewTests(unittest.TestCase):
    def test_source_verified_primitives_are_preview_only(self):
        recovery = model.build_recovery_preview("ready", 5, False, 0)
        self.assertTrue(recovery["read_only"])
        self.assertFalse(recovery["execution_enabled"])
        self.assertFalse(recovery["hardware_accepted"])
        self.assertEqual(recovery["status"], "idle")
        commands = [item["provider_command"] for item in recovery["primitives"]]
        self.assertEqual(commands, ["IFS_F15", "IFS_F112", "IFS_F18", "IFS_F39"])
        self.assertTrue(all(item["source_verified"] for item in recovery["primitives"]))
        self.assertTrue(all(not item["execution_enabled"] for item in recovery["primitives"]))
        self.assertEqual(recovery["provider_sequences"]["driver_error_retry"], ["IFS_F15"])
        self.assertEqual(recovery["provider_sequences"]["timeout_cleanup"], ["IFS_F112", "IFS_F18"])

    def test_driver_error_and_insert_are_evidence_not_execution(self):
        recovery = model.build_recovery_preview("error", 127, True, 3)
        self.assertEqual(recovery["status"], "driver_error")
        self.assertTrue(recovery["evidence"]["driver_error"])
        self.assertTrue(recovery["evidence"]["need_insert"])
        self.assertEqual(recovery["evidence"]["insert_slot"], 3)
        self.assertFalse(recovery["execution_enabled"])

    def test_native_display_suspends_recovery_preview(self):
        recovery = model.build_recovery_preview("maintenance_suspended", 127, True, 2, "native_display")
        self.assertEqual(recovery["status"], "suspended")
        self.assertFalse(recovery["execution_enabled"])

    def test_stall_mask_does_not_manufacture_recovery_advice(self):
        raw = {"available": True, "state": "ready", "state_code": 5, "active_slot": 1, "slots": [{"slot": 1, "present": True, "stall": True}], "stall_mask": 1, "need_insert": False, "insert_slot": 0}
        module = model.normalize_module(raw, {}, "standby", True, {"state": "idle", "action": "", "slot": 0, "error": ""})
        self.assertEqual(module["diagnostics"]["stall_mask"], 1)
        self.assertEqual(module["recovery"]["status"], "idle")
        self.assertNotIn("recommended_action", module["recovery"])
        self.assertFalse(module["capabilities"]["actions"]["recovery"])
        self.assertTrue(module["capabilities"]["recovery"]["preview"])
        self.assertFalse(module["capabilities"]["recovery"]["execute"])

if __name__ == "__main__":
    unittest.main()
