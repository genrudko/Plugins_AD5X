from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "moonraker" / "components" / "plugins_ad5x_ifs_interop.py"


def load_module():
    spec = importlib.util.spec_from_file_location("plugins_ad5x_ifs_interop_test", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load IFS interop module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


interop = load_module()


def slot(number, present=True, material="PETG", colors=None, **spool_extra):
    spool = {"brand": "Example", "name": "Test spool %d" % number, "material": material}
    spool.update(spool_extra)
    return {
        "slot": number,
        "present": present,
        "spool": spool,
        "appearance": {"colors": colors or ["#123456"]},
    }


class IFSInteropTests(unittest.TestCase):
    def test_architecture_profile_makes_expert_canonical(self):
        profile = interop.get_architecture_profile()
        self.assertEqual(profile["architecture_version"], "2.0")
        self.assertEqual(profile["ui"]["canonical_expertise"], "expert")
        self.assertEqual(profile["ui"]["expertise_levels"], ["auto", "hybrid", "expert"])
        self.assertEqual(profile["topology"]["ifs_slot_count"], 4)
        self.assertEqual(profile["topology"]["external_source"]["id"], "external:bypass")
        self.assertFalse(profile["topology"]["external_source"]["runtime_supported"])

    def test_orca_projection_uses_stable_keys_and_zero_based_string_lanes(self):
        projection = interop.build_orca_lane_data_projection([slot(1), slot(2), slot(3), slot(4)])
        self.assertTrue(projection["publishable"])
        self.assertEqual(list(projection["records"]), ["lane1", "lane2", "lane3", "lane4"])
        self.assertEqual(
            [projection["records"]["lane%d" % n]["lane"] for n in range(1, 5)],
            ["0", "1", "2", "3"],
        )

    def test_empty_lane_does_not_leak_stale_metadata(self):
        record = interop.build_orca_lane_record(
            slot(4, present=False, material="TPU", colors=["#ABCDEF"], spoolman_spool_id=99)
        )
        self.assertEqual(record["lane"], "3")
        self.assertIsNone(record["material"])
        self.assertIsNone(record["color"])
        self.assertIsNone(record["spool_id"])
        self.assertIsNone(record["helix_material"])

    def test_multicolor_projects_representative_primary_color(self):
        record = interop.build_orca_lane_record(
            slot(1, colors=["#ff0000", "#00FF00", "#0000FF"])
        )
        self.assertEqual(record["color"], "#FF0000")

    def test_specialty_material_is_preserved_but_not_guessed_for_orca(self):
        record = interop.build_orca_lane_record(slot(1, material="ASA-GF"))
        self.assertIsNone(record["material"])
        self.assertEqual(record["helix_material"], "ASA-GF")
        explicit = interop.build_orca_lane_record(slot(1, material="ASA-GF", orca_material="ASA"))
        self.assertEqual(explicit["material"], "ASA")
        self.assertEqual(explicit["helix_material"], "ASA-GF")

    def test_base_materials_are_safe_passthrough(self):
        for material in ("PLA", "PETG", "ABS", "ASA", "TPU"):
            with self.subTest(material=material):
                self.assertEqual(
                    interop.build_orca_lane_record(slot(1, material=material))["material"],
                    material,
                )

    def test_spoolman_filament_id_is_not_orca_filament_id(self):
        record = interop.build_orca_lane_record(
            slot(1, spoolman_spool_id=42, spoolman_filament_id=777)
        )
        self.assertEqual(record["spool_id"], 42)
        self.assertIsNone(record["filament_id"])
        exact = interop.build_orca_lane_record(
            slot(
                1,
                spoolman_spool_id=42,
                spoolman_filament_id=777,
                orca_filament_id="Generic PLA @System",
                orca_setting_id="GFSL99",
            )
        )
        self.assertEqual(exact["filament_id"], "Generic PLA @System")
        self.assertEqual(exact["orca_setting_id"], "GFSL99")

    def test_v1_spoolman_id_remains_spool_alias(self):
        self.assertEqual(interop.build_orca_lane_record(slot(1, spoolman_id=12))["spool_id"], 12)

    def test_unknown_fields_in_owned_lane_are_preserved(self):
        existing = {
            "lane1": {"lane": "0", "foreign_extension": {"hello": "world"}, "material": "OLD"},
            "some_other_system": {"value": 1},
        }
        projection = interop.build_orca_lane_data_projection([slot(1)], existing)
        lane1 = projection["records"]["lane1"]
        self.assertEqual(lane1["foreign_extension"], {"hello": "world"})
        self.assertEqual(lane1["material"], "PETG")
        self.assertNotIn("some_other_system", projection["records"])

    def test_duplicate_inner_lane_blocks_publication(self):
        existing = {
            "lane1": {"lane": "0", "material": "PLA"},
            "lane0": {"lane": "0", "material": "PETG"},
        }
        projection = interop.build_orca_lane_data_projection([slot(1)], existing)
        self.assertFalse(projection["publishable"])
        self.assertEqual(
            projection["conflicts"],
            [{"lane": "0", "expected_key": "lane1", "conflicting_key": "lane0"}],
        )

    def test_projection_summary_is_bounded_and_deterministic(self):
        projection = interop.build_orca_lane_data_projection([slot(1), slot(2)])
        first = interop.summarize_orca_projection(projection)
        second = interop.summarize_orca_projection(projection)
        self.assertEqual(first, second)
        self.assertEqual(first["record_count"], 4)
        self.assertEqual(len(first["fingerprint"]), 64)
        self.assertTrue(first["requires_moonraker_agent"])
        self.assertEqual(first["target_version"], "2.4.2")


if __name__ == "__main__":
    unittest.main()
