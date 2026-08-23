from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_spoolman.py"


def load_module():
    spec = importlib.util.spec_from_file_location("plugins_ad5x_ifs_spoolman_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load IFS Spoolman module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spoolman = load_module()


def example_spool(**overrides):
    payload = {
        "id": 42,
        "remaining_weight": 612.5,
        "remaining_length": 205000.0,
        "initial_weight": 1000.0,
        "used_weight": 387.5,
        "used_length": 130000.0,
        "location": "IFS",
        "archived": False,
        "filament": {
            "id": 77,
            "name": "PolyTerra Charcoal Black",
            "material": "PLA",
            "color_hex": "161616",
            "multi_color_hexes": None,
            "settings_extruder_temp": 220,
            "settings_bed_temp": 60,
            "vendor": {"id": 9, "name": "Polymaker"},
        },
    }
    payload.update(overrides)
    return payload


class IFSSpoolmanTests(unittest.TestCase):
    def test_normalizes_spool_and_filament_identity_separately(self):
        item = spoolman.normalize_spoolman_spool(example_spool())
        self.assertEqual(item["spoolman_spool_id"], 42)
        self.assertEqual(item["spoolman_filament_id"], 77)
        self.assertEqual(item["spool"]["spoolman_id"], 42)
        self.assertEqual(item["spool"]["spoolman_spool_id"], 42)
        self.assertEqual(item["spool"]["spoolman_filament_id"], 77)
        self.assertEqual(item["spool"]["brand"], "Polymaker")
        self.assertEqual(item["spool"]["material"], "PLA")
        self.assertEqual(item["inventory"]["remaining_g"], 612.5)
        self.assertEqual(item["spool"]["nozzle_temp"], 220)
        self.assertEqual(item["spool"]["bed_temp"], 60)
        self.assertEqual(item["appearance"]["colors"], ["#161616"])
        self.assertEqual(item["spool"]["orca_filament_id"], "")

    def test_multicolor_is_imported_without_inventing_finish(self):
        raw = example_spool()
        raw["filament"]["color_hex"] = None
        raw["filament"]["multi_color_hexes"] = "FF0000,00ff00,0000FF"
        item = spoolman.normalize_spoolman_spool(raw)
        self.assertEqual(item["appearance"]["color_mode"], "tricolor")
        self.assertEqual(
            item["appearance"]["colors"], ["#FF0000", "#00FF00", "#0000FF"]
        )
        self.assertEqual(item["appearance"]["finish"], "standard")

    def test_binding_preserves_plugins_ad5x_rich_only_fields(self):
        existing = {
            "spool": {
                "series": "My Series",
                "variant": "Glow",
                "orca_material": "PLA",
                "orca_filament_id": "Generic PLA @System",
            },
            "appearance": {"colors": ["#FFFFFF"], "finish": "glow"},
        }
        merged = spoolman.merge_spoolman_binding(
            existing, spoolman.normalize_spoolman_spool(example_spool())
        )
        self.assertEqual(merged["spool"]["source"], "spoolman")
        self.assertEqual(merged["spool"]["series"], "My Series")
        self.assertEqual(merged["spool"]["variant"], "Glow")
        self.assertEqual(merged["spool"]["orca_filament_id"], "Generic PLA @System")
        self.assertEqual(merged["appearance"]["finish"], "glow")
        self.assertEqual(merged["appearance"]["colors"], ["#161616"])

    def test_unbind_keeps_copied_identity_but_removes_dynamic_spoolman_state(self):
        bound = spoolman.merge_spoolman_binding(
            {"appearance": {"finish": "matte"}},
            spoolman.normalize_spoolman_spool(example_spool()),
        )
        detached = spoolman.unbind_spoolman_record(bound, keep_metadata=True)
        self.assertIsNotNone(detached)
        self.assertEqual(detached["spool"]["source"], "manual")
        self.assertEqual(detached["spool"]["brand"], "Polymaker")
        self.assertNotIn("spoolman_spool_id", detached["spool"])
        self.assertNotIn("spoolman_filament_id", detached["spool"])
        self.assertNotIn("remaining_g", detached["spool"])
        self.assertEqual(detached["appearance"]["finish"], "matte")

    def test_unbind_can_clear_local_copy_without_deleting_external_entity(self):
        bound = spoolman.merge_spoolman_binding(
            {}, spoolman.normalize_spoolman_spool(example_spool())
        )
        self.assertIsNone(spoolman.unbind_spoolman_record(bound, keep_metadata=False))

    def test_binding_summary_tracks_four_physical_slots(self):
        slots = [
            {"slot": 1, "present": True, "active": True, "spool": {"spoolman_spool_id": 42, "spoolman_filament_id": 77}},
            {"slot": 2, "present": True, "active": False, "spool": {}},
            {"slot": 3, "present": False, "active": False, "spool": {"spoolman_id": 99}},
            {"slot": 4, "present": True, "active": False, "spool": {}},
        ]
        summary = spoolman.summarize_bindings(slots)
        self.assertEqual([item["slot"] for item in summary], [1, 2, 3, 4])
        self.assertEqual(summary[0]["spool_id"], 42)
        self.assertEqual(summary[2]["spool_id"], 99)

    def test_fallback_search_matches_vendor_material_name_location_and_id(self):
        items = [example_spool(), example_spool(id=99, location="Shelf B")]
        self.assertEqual(
            [item["spoolman_spool_id"] for item in spoolman.fallback_filter_library(items, "polymaker")],
            [42, 99],
        )
        self.assertEqual(
            [item["spoolman_spool_id"] for item in spoolman.fallback_filter_library(items, "Shelf B")],
            [99],
        )


if __name__ == "__main__":
    unittest.main()
