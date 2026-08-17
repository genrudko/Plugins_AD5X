from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"


def load_model():
    spec = importlib.util.spec_from_file_location("plugins_ad5x_ifs_preprint_model", MODEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load IFS model")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


model = load_model()


def slot(number, *, present, material, colors, metadata_status="assigned"):
    return {
        "slot": number,
        "present": present,
        "metadata_status": metadata_status,
        "spool": {
            "source": "manual",
            "brand": "Test",
            "series": "",
            "name": "",
            "material": material,
            "variant": "",
            "spoolman_id": None,
            "remaining_g": None,
        },
        "appearance": {
            "color_mode": "solid" if len(colors) <= 1 else "tricolor",
            "colors": colors,
            "finish": "standard",
        },
    }


class IFSPreprintPlanTests(unittest.TestCase):
    def setUp(self):
        self.slots = [
            slot(1, present=True, material="PETG", colors=["#161616"]),
            slot(2, present=True, material="PLA", colors=["#161616"]),
            slot(3, present=True, material="PLA", colors=["#F330F9", "#27C4F4", "#FFD43B"]),
            slot(4, present=False, material="TPU", colors=["#161616"], metadata_status="stale"),
        ]

    def test_ready_plan_joins_requirements_assignments_and_slot_metadata(self):
        preview = {
            "available": True,
            "source": "zmod",
            "filename": "demo.gcode",
            "requirements": [
                {"tool": 0, "color": "#F330F9", "material": "PLA"},
                {"tool": 1, "color": "#161616", "material": "PETG"},
            ],
            "assignments": [
                {"tool": 0, "slot": 3},
                {"tool": 1, "slot": 1},
            ],
            "auto_assign": {
                "flags": 1,
                "any_success": True,
                "material_failure": False,
                "color_failure": False,
                "weak_color": False,
                "duplicate_slot": False,
            },
            "messages": [],
            "error": "",
        }
        plan = model.build_preprint_plan(preview, self.slots)
        self.assertTrue(plan["available"])
        self.assertEqual(plan["source"], "zmod")
        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["warnings"], [])
        self.assertEqual(plan["summary"], {"required_tools": 2, "assigned_tools": 2, "ready_tools": 2})

        row0 = plan["rows"][0]
        self.assertEqual(row0["tool"], 0)
        self.assertEqual(row0["requirement"], {"material": "PLA", "color": "#F330F9"})
        self.assertEqual(row0["assignment"]["slot"], 3)
        self.assertTrue(row0["assignment"]["present"])
        self.assertEqual(row0["assignment"]["spool"]["material"], "PLA")
        self.assertEqual(row0["state"], "ready")

    def test_unassigned_tool_blocks_plan_without_inventing_match(self):
        preview = {
            "available": True,
            "source": "zmod",
            "filename": "demo.gcode",
            "requirements": [{"tool": 2, "color": "#FFFFFF", "material": "PLA"}],
            "assignments": [],
            "auto_assign": {
                "flags": 0,
                "any_success": False,
                "material_failure": False,
                "color_failure": False,
                "weak_color": False,
                "duplicate_slot": False,
            },
            "messages": [],
            "error": "",
        }
        plan = model.build_preprint_plan(preview, self.slots)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["rows"][0]["state"], "unassigned")
        self.assertIsNone(plan["rows"][0]["assignment"])
        self.assertIn("unassigned_tool", plan["warnings"])

    def test_assignment_to_physically_empty_slot_blocks_plan(self):
        preview = {
            "available": True,
            "source": "zmod",
            "filename": "demo.gcode",
            "requirements": [{"tool": 0, "color": "#161616", "material": "TPU"}],
            "assignments": [{"tool": 0, "slot": 4}],
            "auto_assign": {"flags": 1, "any_success": True},
            "messages": [],
            "error": "",
        }
        plan = model.build_preprint_plan(preview, self.slots)
        self.assertEqual(plan["status"], "blocked")
        self.assertEqual(plan["rows"][0]["state"], "slot_empty")
        self.assertFalse(plan["rows"][0]["assignment"]["present"])
        self.assertIn("assigned_slot_empty", plan["warnings"])

    def test_zmod_global_quality_flags_are_preserved_as_global_warnings(self):
        preview = {
            "available": True,
            "source": "zmod",
            "filename": "demo.gcode",
            "requirements": [
                {"tool": 0, "color": "#F330F9", "material": "PLA"},
                {"tool": 1, "color": "#161616", "material": "PLA"},
            ],
            "assignments": [{"tool": 0, "slot": 3}, {"tool": 1, "slot": 2}],
            "auto_assign": {
                "flags": 25,
                "any_success": True,
                "material_failure": False,
                "color_failure": False,
                "weak_color": True,
                "duplicate_slot": True,
            },
            "messages": ["Z-Mod says weak/duplicate"],
            "error": "",
        }
        plan = model.build_preprint_plan(preview, self.slots)
        self.assertEqual(plan["status"], "warning")
        self.assertIn("weak_color", plan["warnings"])
        self.assertIn("duplicate_slot", plan["warnings"])
        self.assertEqual([row["state"] for row in plan["rows"]], ["ready", "ready"])
        # The current Z-Mod API only exposes aggregate quality flags, so the
        # frontend-neutral model must not fabricate per-tool weak/duplicate data.
        for row in plan["rows"]:
            self.assertNotIn("weak_color", row)
            self.assertNotIn("duplicate_slot", row)

    def test_material_or_color_failure_blocks_even_when_zmod_proposes_slots(self):
        for flag in ("material_failure", "color_failure"):
            with self.subTest(flag=flag):
                auto = {
                    "flags": 3,
                    "any_success": True,
                    "material_failure": False,
                    "color_failure": False,
                    "weak_color": False,
                    "duplicate_slot": False,
                }
                auto[flag] = True
                preview = {
                    "available": True,
                    "source": "zmod",
                    "filename": "demo.gcode",
                    "requirements": [{"tool": 0, "color": "#F330F9", "material": "PLA"}],
                    "assignments": [{"tool": 0, "slot": 3}],
                    "auto_assign": auto,
                    "messages": [],
                    "error": "",
                }
                plan = model.build_preprint_plan(preview, self.slots)
                self.assertEqual(plan["status"], "blocked")
                self.assertIn(flag, plan["warnings"])

    def test_missing_file_metadata_remains_unknown_not_inferred_from_spool(self):
        preview = {
            "available": True,
            "source": "zmod",
            "filename": "demo.gcode",
            "requirements": [{"tool": 0, "color": "", "material": ""}],
            "assignments": [{"tool": 0, "slot": 1}],
            "auto_assign": {
                "flags": 5,
                "any_success": True,
                "material_failure": False,
                "color_failure": True,
                "weak_color": False,
                "duplicate_slot": False,
            },
            "messages": [],
            "error": "",
        }
        plan = model.build_preprint_plan(preview, self.slots)
        self.assertEqual(plan["rows"][0]["requirement"], {"material": "", "color": ""})
        self.assertEqual(plan["rows"][0]["assignment"]["spool"]["material"], "PETG")
        self.assertEqual(plan["status"], "blocked")

    def test_unavailable_preview_stays_unavailable(self):
        plan = model.build_preprint_plan(
            {"available": False, "source": "zmod", "error": "not_scanned"}, self.slots
        )
        self.assertFalse(plan["available"])
        self.assertEqual(plan["status"], "unavailable")
        self.assertEqual(plan["rows"], [])
        self.assertEqual(plan["error"], "not_scanned")


if __name__ == "__main__":
    unittest.main()
