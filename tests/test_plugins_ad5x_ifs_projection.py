from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_model.py"


def load_model():
    spec = importlib.util.spec_from_file_location("plugins_ad5x_ifs_projection_model", MODEL_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load IFS model")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


model = load_model()


class IFSZModProjectionTests(unittest.TestCase):
    def test_solid_plain_material_can_be_in_sync_losslessly(self):
        projection = model.build_zmod_compat_projection(
            slot=1,
            spool={"material": "PLA"},
            appearance={
                "color_mode": "solid",
                "colors": ["#161616"],
                "finish": "standard",
            },
            current={"material": "PLA", "color": "#161616"},
        )
        self.assertTrue(projection["write_ready"])
        self.assertEqual(projection["sync_state"], "in_sync")
        self.assertFalse(projection["lossy"])
        self.assertEqual(projection["desired"], {"material": "PLA", "color": "#161616"})
        self.assertEqual(projection["write_blockers"], [])

    def test_rich_tricolor_silk_projects_primary_color_and_reports_loss(self):
        projection = model.build_zmod_compat_projection(
            slot=3,
            spool={
                "brand": "ERYONE",
                "series": "Silk",
                "name": "Triple Color",
                "material": "PLA",
                "variant": "",
                "spoolman_id": 42,
                "remaining_g": 612.5,
            },
            appearance={
                "color_mode": "tricolor",
                "colors": ["#F330F9", "#27C4F4", "#FFD43B"],
                "finish": "silk",
            },
            current={"material": "PLA", "color": "#161616"},
        )
        self.assertTrue(projection["write_ready"])
        self.assertEqual(projection["desired"], {"material": "PLA", "color": "#F330F9"})
        self.assertEqual(projection["sync_state"], "diverged")
        self.assertTrue(projection["lossy"])
        self.assertIn("appearance.colors[1:]", projection["omitted_fields"])
        self.assertIn("appearance.finish", projection["omitted_fields"])
        self.assertIn("spool.brand", projection["omitted_fields"])
        self.assertIn("spool.spoolman_id", projection["omitted_fields"])
        self.assertIn("spool.remaining_g", projection["omitted_fields"])

    def test_finish_does_not_silently_reclassify_pla_as_zmod_silk(self):
        projection = model.build_zmod_compat_projection(
            slot=2,
            spool={"material": "PLA"},
            appearance={
                "color_mode": "solid",
                "colors": ["#FFFFFF"],
                "finish": "silk",
            },
            current={"material": "PLA", "color": "#FFFFFF"},
        )
        self.assertEqual(projection["desired"]["material"], "PLA")
        self.assertEqual(projection["sync_state"], "in_sync")
        self.assertTrue(projection["lossy"])
        self.assertIn("appearance.finish", projection["omitted_fields"])

    def test_zmod_silk_is_only_used_when_material_explicitly_is_silk(self):
        projection = model.build_zmod_compat_projection(
            slot=2,
            spool={"material": "SILK"},
            appearance={"color_mode": "solid", "colors": ["#FFFFFF"], "finish": "silk"},
            current={"material": "SILK", "color": "#FFFFFF"},
        )
        self.assertTrue(projection["write_ready"])
        self.assertEqual(projection["desired"]["material"], "SILK")

    def test_unrepresentable_rich_material_fails_closed(self):
        projection = model.build_zmod_compat_projection(
            slot=1,
            spool={"material": "PLA+"},
            appearance={"color_mode": "solid", "colors": ["#123456"], "finish": "standard"},
            current={"material": "PLA", "color": "#123456"},
        )
        self.assertFalse(projection["write_ready"])
        self.assertEqual(projection["sync_state"], "unsupported")
        self.assertIn("unsupported_material", projection["write_blockers"])
        self.assertEqual(projection["desired"]["material"], "")

    def test_missing_primary_color_fails_closed(self):
        projection = model.build_zmod_compat_projection(
            slot=4,
            spool={"material": "TPU"},
            appearance={"color_mode": "solid", "colors": [], "finish": "standard"},
            current={"material": "TPU", "color": "#161616"},
        )
        self.assertFalse(projection["write_ready"])
        self.assertEqual(projection["sync_state"], "unsupported")
        self.assertIn("missing_primary_color", projection["write_blockers"])

    def test_normalized_slot_keeps_zmod_truth_separate_from_manual_overlay(self):
        slot = model.normalize_slot(
            {"slot": 3, "present": True, "stall": False},
            {
                "material": "PLA",
                "color": "#F330F9",
                "zmod_compat": {"material": "PLA", "color": "#161616"},
                "spool": {
                    "source": "manual",
                    "brand": "ERYONE",
                    "material": "PLA",
                },
                "appearance": {
                    "color_mode": "tricolor",
                    "colors": ["#F330F9", "#27C4F4", "#FFD43B"],
                    "finish": "silk",
                },
            },
            active_slot=1,
            filament_at_toolhead=True,
            module_state="ready",
            print_state="standby",
            operation_state="idle",
        )
        compat = slot["compatibility"]["zmod"]
        self.assertEqual(compat["current"], {"material": "PLA", "color": "#161616"})
        self.assertEqual(compat["desired"], {"material": "PLA", "color": "#F330F9"})
        self.assertEqual(compat["sync_state"], "diverged")

    def test_capability_exposes_preview_but_not_projection_write(self):
        caps = model.get_ifs_capabilities()
        self.assertTrue(caps["compatibility"]["zmod_projection_preview"])
        self.assertFalse(caps["compatibility"]["zmod_projection_write"])


if __name__ == "__main__":
    unittest.main()
