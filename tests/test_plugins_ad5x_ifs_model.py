from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"


def load_model():
    spec = importlib.util.spec_from_file_location("plugins_ad5x_ifs_model", MODEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load IFS model")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


model = load_model()


class IFSManagerModelTests(unittest.TestCase):
    def test_legacy_flashforge_color_becomes_solid_standard_appearance(self):
        slot = model.normalize_slot(
            {"slot": 1, "present": True, "stall": False},
            {"material": "PETG", "color": "#161616"},
            active_slot=1,
            filament_at_toolhead=True,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )

        self.assertEqual(slot["material"], "PETG")
        self.assertEqual(slot["color"], "#161616")
        self.assertEqual(
            slot["appearance"],
            {
                "color_mode": "solid",
                "colors": ["#161616"],
                "finish": "standard",
            },
        )
        self.assertEqual(slot["spool"]["source"], "flashforge")
        self.assertEqual(slot["spool"]["material"], "PETG")
        self.assertEqual(slot["metadata_status"], "assigned")

    def test_dual_silk_and_tricolor_matte_are_first_class_metadata(self):
        dual = model.normalize_slot(
            {"slot": 2, "present": True, "stall": False},
            {
                "spool": {
                    "source": "manual",
                    "brand": "ERYONE",
                    "series": "Silk",
                    "material": "PLA",
                    "name": "Red Blue Dual",
                },
                "appearance": {
                    "color_mode": "dual",
                    "colors": ["#ff0000", "#0000ff"],
                    "finish": "silk",
                },
            },
            active_slot=1,
            filament_at_toolhead=True,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )
        self.assertEqual(dual["appearance"]["color_mode"], "dual")
        self.assertEqual(dual["appearance"]["colors"], ["#FF0000", "#0000FF"])
        self.assertEqual(dual["appearance"]["finish"], "silk")
        self.assertEqual(dual["spool"]["brand"], "ERYONE")

        tri = model.normalize_appearance(
            appearance={
                "color_mode": "tricolor",
                "colors": ["#112233", "#445566", "#778899"],
                "finish": "matte",
            }
        )
        self.assertEqual(tri["color_mode"], "tricolor")
        self.assertEqual(tri["finish"], "matte")
        self.assertEqual(len(tri["colors"]), 3)

    def test_gradient_rainbow_and_invalid_values_fail_soft(self):
        gradient = model.normalize_appearance(
            appearance={
                "color_mode": "gradient",
                "colors": ["#000000", "#ffffff", "bad", "#FFFFFF"],
                "finish": "metallic",
            }
        )
        self.assertEqual(gradient["color_mode"], "gradient")
        self.assertEqual(gradient["colors"], ["#000000", "#FFFFFF"])
        self.assertEqual(gradient["finish"], "metallic")

        invalid = model.normalize_appearance(
            legacy_color="not-a-color",
            appearance={
                "color_mode": "dual",
                "colors": ["bad"],
                "finish": "mystery",
            },
        )
        self.assertEqual(invalid["color_mode"], "solid")
        self.assertEqual(invalid["colors"], [])
        self.assertEqual(invalid["finish"], "standard")

    def test_empty_slot_hides_stale_metadata_from_current_identity(self):
        slot = model.normalize_slot(
            {"slot": 4, "present": False, "stall": False},
            {
                "material": "TPU",
                "color": "#161616",
                "spool": {"source": "flashforge", "name": "Previous spool"},
            },
            active_slot=1,
            filament_at_toolhead=True,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )
        self.assertFalse(slot["present"])
        self.assertEqual(slot["metadata_status"], "stale")
        self.assertEqual(slot["spool"]["material"], "")
        self.assertNotIn("material", slot)
        self.assertTrue(slot["stale_metadata_available"])
        self.assertEqual(slot["current_identity_status"], "empty")
        self.assertFalse(slot["permissions"]["select_slot"])
        self.assertFalse(slot["permissions"]["load_slot"])
        self.assertEqual(slot["permissions"]["blocked_reason"], "slot_empty")

    def test_finish_only_metadata_is_hidden_when_slot_empty(self):
        slot = model.normalize_slot(
            {"slot": 4, "present": False, "stall": False},
            {"appearance": {"finish": "silk"}},
            active_slot=1,
            filament_at_toolhead=False,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )
        self.assertEqual(slot["appearance"]["finish"], "standard")
        self.assertEqual(slot["metadata_status"], "stale")
        self.assertTrue(slot["stale_metadata_available"])
        self.assertEqual(slot["current_identity_status"], "empty")

    def test_permissions_are_backend_owned_and_fail_closed(self):
        active = model.compute_slot_permissions(
            slot=1,
            present=True,
            active_slot=1,
            filament_at_toolhead=True,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )
        self.assertFalse(active["select_slot"])
        self.assertFalse(active["load_slot"])
        self.assertTrue(active["unload_slot"])

        other = model.compute_slot_permissions(
            slot=2,
            present=True,
            active_slot=1,
            filament_at_toolhead=True,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )
        self.assertTrue(other["select_slot"])
        self.assertTrue(other["load_slot"])
        self.assertFalse(other["unload_slot"])

        for state in ("printing", "paused", "unknown"):
            with self.subTest(state=state):
                blocked = model.compute_slot_permissions(
                    slot=2,
                    present=True,
                    active_slot=1,
                    filament_at_toolhead=True,
                    module_state="ready",
                    print_state=state,
                    operation_state="idle",
                )
                self.assertFalse(blocked["select_slot"])
                self.assertFalse(blocked["load_slot"])
                self.assertFalse(blocked["unload_slot"])
                self.assertEqual(blocked["blocked_reason"], "unsafe_print_state")

        busy = model.compute_slot_permissions(
            slot=2,
            present=True,
            active_slot=1,
            filament_at_toolhead=True,
            module_state="ready",
            print_state="standby",
            operation_state="running",
        )
        self.assertEqual(busy["blocked_reason"], "operation_in_progress")

    def test_capabilities_are_separate_from_runtime_permissions(self):
        capabilities = model.get_ifs_capabilities()
        self.assertEqual(capabilities["schema_version"], "1.0")
        self.assertEqual(capabilities["slot_count"], 4)
        self.assertTrue(capabilities["actions"]["select_slot"])
        self.assertTrue(capabilities["actions"]["load_slot"])
        self.assertTrue(capabilities["actions"]["unload_slot"])
        self.assertTrue(capabilities["actions"]["preview_job"])
        self.assertFalse(capabilities["actions"]["eject_slot"])
        self.assertFalse(capabilities["actions"]["recovery"])
        self.assertTrue(capabilities["metadata"]["multi_color"])
        self.assertTrue(capabilities["metadata"]["finish"])
        self.assertTrue(capabilities["integrations"]["manual_store"])
        self.assertFalse(capabilities["integrations"]["spoolman"])
        self.assertTrue(capabilities["integrations"]["slicer"])
        self.assertFalse(capabilities["metadata"]["rfid"])
        self.assertTrue(capabilities["mapping"]["preprint_preview"])
        self.assertFalse(capabilities["mapping"]["apply_preprint_mapping"])
        self.assertTrue(capabilities["mapping"]["equivalent_spool_preview"])
        self.assertFalse(capabilities["mapping"]["endless_spool"])

    def test_spool_fields_are_normalized_without_inventing_missing_data(self):
        spool = model.normalize_spool_metadata(
            {
                "source": "spoolman",
                "brand": " Polymaker ",
                "series": "PolyLite",
                "name": "PLA Pro",
                "material": "PLA",
                "variant": "Pro",
                "spoolman_id": 42,
                "remaining_g": 612.5,
            }
        )
        self.assertEqual(spool["source"], "spoolman")
        self.assertEqual(spool["brand"], "Polymaker")
        self.assertEqual(spool["spoolman_id"], 42)
        self.assertEqual(spool["remaining_g"], 612.5)

        missing = model.normalize_spool_metadata({"source": "bogus", "spoolman_id": -1})
        self.assertEqual(missing["source"], "unknown")
        self.assertIsNone(missing["spoolman_id"])
        self.assertIsNone(missing["remaining_g"])


if __name__ == "__main__":
    unittest.main()
