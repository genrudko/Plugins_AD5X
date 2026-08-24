from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"


def load_model():
    spec = importlib.util.spec_from_file_location("plugins_ad5x_ifs_launch_model", MODEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load IFS model")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


model = load_model()


def preview(*, weak=False, duplicate=False, material_failure=False, color_failure=False):
    return {
        "available": True,
        "source": "zmod",
        "filename": "3mf/model/demo/Metadata/plate_1.gcode",
        "requirements": [
            {"tool": 0, "color": "#F330F9", "material": "PLA"},
            {"tool": 1, "color": "#161616", "material": "PETG"},
        ],
        "assignments": [
            {"tool": 0, "slot": 3},
            {"tool": 1, "slot": 1},
        ],
        "allowed_tool_count": 2,
        "resolved_tool_map": [3, 1],
        "auto_assign": {
            "flags": 1,
            "any_success": True,
            "material_failure": material_failure,
            "color_failure": color_failure,
            "weak_color": weak,
            "duplicate_slot": duplicate,
        },
        "messages": [],
        "error": "",
    }


def slots(*, slot3_present=True):
    return [
        {"slot": 1, "present": True, "metadata_status": "assigned", "spool": {"material": "PETG"}, "appearance": {"colors": ["#161616"]}},
        {"slot": 2, "present": True, "metadata_status": "assigned", "spool": {"material": "PLA"}, "appearance": {"colors": ["#161616"]}},
        {"slot": 3, "present": slot3_present, "metadata_status": "assigned" if slot3_present else "stale", "spool": {"material": "PLA"}, "appearance": {"colors": ["#F330F9", "#27C4F4", "#FFD43B"]}},
        {"slot": 4, "present": False, "metadata_status": "stale", "spool": {"material": "TPU"}, "appearance": {"colors": ["#161616"]}},
    ]


class IFSLaunchContractTests(unittest.TestCase):
    def test_preview_token_is_stable_for_semantically_identical_preview(self):
        first = preview()
        second = {
            "error": "",
            "messages": [],
            "assignments": list(first["assignments"]),
            "allowed_tool_count": first["allowed_tool_count"],
            "resolved_tool_map": list(first["resolved_tool_map"]),
            "requirements": list(first["requirements"]),
            "source": "zmod",
            "filename": first["filename"],
            "available": True,
            "auto_assign": dict(first["auto_assign"]),
        }
        self.assertEqual(model.build_job_preview_token(first), model.build_job_preview_token(second))
        self.assertRegex(model.build_job_preview_token(first), r"^[0-9a-f]{64}$")

    def test_preview_token_changes_when_mapping_or_file_requirement_changes(self):
        original = preview()
        remapped = preview()
        remapped["assignments"][0] = {"tool": 0, "slot": 2}
        recolored = preview()
        recolored["requirements"][0] = {"tool": 0, "color": "#FFFFFF", "material": "PLA"}
        self.assertNotEqual(model.build_job_preview_token(original), model.build_job_preview_token(remapped))
        self.assertNotEqual(model.build_job_preview_token(original), model.build_job_preview_token(recolored))

    def test_ready_plan_is_launch_candidate_but_write_capability_stays_disabled(self):
        source = preview()
        plan = model.build_preprint_plan(source, slots())
        gate = model.build_job_launch_gate(
            source,
            plan,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )
        self.assertTrue(gate["candidate"])
        self.assertFalse(gate["write_enabled"])
        self.assertEqual(gate["blockers"], ["launch_write_not_enabled"])
        self.assertEqual(gate["warnings"], [])
        self.assertEqual(gate["preview_token"], model.build_job_preview_token(source))

    def test_weak_or_duplicate_match_is_not_silently_promoted_to_ready_launch(self):
        for flag in ("weak", "duplicate"):
            with self.subTest(flag=flag):
                source = preview(**{flag: True})
                plan = model.build_preprint_plan(source, slots())
                gate = model.build_job_launch_gate(
                    source,
                    plan,
                    module_state="ready",
                    print_state="standby",
                    operation_state="idle",
                )
                self.assertFalse(gate["candidate"])
                self.assertFalse(gate["write_enabled"])
                expected = "weak_color" if flag == "weak" else "duplicate_slot"
                self.assertIn(expected, gate["warnings"])
                self.assertIn("plan_not_strict_ready", gate["blockers"])

    def test_material_or_color_failure_blocks_launch(self):
        for key in ("material_failure", "color_failure"):
            with self.subTest(key=key):
                source = preview(**{key: True})
                plan = model.build_preprint_plan(source, slots())
                gate = model.build_job_launch_gate(
                    source,
                    plan,
                    module_state="ready",
                    print_state="standby",
                    operation_state="idle",
                )
                self.assertFalse(gate["candidate"])
                self.assertIn(key, gate["blockers"])

    def test_physical_slot_change_after_preview_blocks_launch_even_with_same_token(self):
        source = preview()
        token = model.build_job_preview_token(source)
        plan = model.build_preprint_plan(source, slots(slot3_present=False))
        gate = model.build_job_launch_gate(
            source,
            plan,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
            expected_preview_token=token,
        )
        self.assertFalse(gate["candidate"])
        self.assertIn("assigned_slot_empty", gate["blockers"])
        self.assertNotIn("stale_preview", gate["blockers"])

    def test_stale_preview_token_blocks_launch(self):
        source = preview()
        plan = model.build_preprint_plan(source, slots())
        gate = model.build_job_launch_gate(
            source,
            plan,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
            expected_preview_token="0" * 64,
        )
        self.assertFalse(gate["candidate"])
        self.assertIn("stale_preview", gate["blockers"])

    def test_printing_paused_nonready_and_busy_states_fail_closed(self):
        source = preview()
        plan = model.build_preprint_plan(source, slots())
        cases = [
            ("ready", "printing", "idle", "unsafe_print_state"),
            ("ready", "paused", "idle", "unsafe_print_state"),
            ("loading", "standby", "idle", "ifs_not_ready"),
            ("ready", "standby", "running", "operation_in_progress"),
        ]
        for module_state, print_state, op_state, expected in cases:
            with self.subTest(expected=expected):
                gate = model.build_job_launch_gate(
                    source,
                    plan,
                    module_state=module_state,
                    print_state=print_state,
                    operation_state=op_state,
                )
                self.assertFalse(gate["candidate"])
                self.assertIn(expected, gate["blockers"])

    def test_invalid_resolved_tool_map_blocks_launch_candidate(self):
        source = preview()
        source["resolved_tool_map"] = [3, 9]
        plan = model.build_preprint_plan(source, slots())
        gate = model.build_job_launch_gate(
            source,
            plan,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )
        self.assertFalse(gate["candidate"])
        self.assertIn("invalid_resolved_tool_map", gate["blockers"])

    def test_zmod_provider_plan_preserves_complete_mapping_and_requires_explicit_leveling(self):
        source = preview()
        plan = model.build_zmod_print_zcolor_plan(source)
        self.assertEqual(plan["provider"], "zmod")
        self.assertEqual(plan["command"], "PRINT_ZCOLOR")
        self.assertFalse(plan["execution_enabled"])
        self.assertFalse(plan["ready"])
        self.assertEqual(plan["missing_parameters"], ["LEVELING"])
        self.assertEqual(plan["parameters"]["FILENAME"], source["filename"])
        self.assertEqual(plan["parameters"]["ALLOWED_TOOL_COUNT"], 2)
        self.assertEqual(plan["parameters"]["T0"], 3)
        self.assertEqual(plan["parameters"]["T1"], 1)
        self.assertNotIn("LEVELING", plan["parameters"])

        selected = model.build_zmod_print_zcolor_plan(source, leveling=1)
        self.assertTrue(selected["ready"])
        self.assertEqual(selected["parameters"]["LEVELING"], 1)
        self.assertFalse(selected["execution_enabled"])

    def test_zmod_provider_plan_rejects_invalid_leveling(self):
        plan = model.build_zmod_print_zcolor_plan(preview(), leveling=2)
        self.assertFalse(plan["ready"])
        self.assertIn("invalid_leveling", plan["blockers"])
        self.assertNotIn("LEVELING", plan["parameters"])

    def test_capability_keeps_start_and_mapping_write_disabled(self):
        caps = model.get_ifs_capabilities()
        self.assertFalse(caps["actions"]["start_job"])
        self.assertFalse(caps["mapping"]["apply_preprint_mapping"])
        self.assertTrue(caps["mapping"]["preprint_preview"])


if __name__ == "__main__":
    unittest.main()
