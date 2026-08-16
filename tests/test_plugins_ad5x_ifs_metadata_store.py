from __future__ import annotations

import asyncio
import json
import os
import pathlib
import stat
import tempfile
import unittest

from tests import test_plugins_ad5x_ifs_backend as backend_tests


component_module = backend_tests.component_module


class MetadataRequest:
    def __init__(self, **params):
        self.params = params

    def get(self, name, default=None):
        return self.params.get(name, default)

    def get_int(self, name):
        return int(self.params[name])

    def get_boolean(self, name, default=False):
        value = self.params.get(name, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        raise TypeError(name)


class IFSMetadataStoreTests(unittest.TestCase):
    def setUp(self):
        self._old_ffconfig = component_module.FFCONFIG_PATH
        self._old_mapping = component_module.FILE_MAPPING_PATH
        self._old_store = component_module.IFS_METADATA_STORE_PATH
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.ffconfig = self.root / "Adventurer5M.json"
        self.mapping = self.root / "file.json"
        self.store = self.root / "state" / "ifs_metadata.json"
        component_module.FFCONFIG_PATH = str(self.ffconfig)
        component_module.FILE_MAPPING_PATH = str(self.mapping)
        component_module.IFS_METADATA_STORE_PATH = str(self.store)
        self.ffconfig.write_text(
            json.dumps(
                {
                    "FFMInfo": {
                        "channel": 1,
                        "ffmType1": "PETG",
                        "ffmColor1": "#161616",
                        "ffmType2": "PLA",
                        "ffmColor2": "#161616",
                        "ffmType3": "PLA",
                        "ffmColor3": "#F330F9",
                        "ffmType4": "TPU",
                        "ffmColor4": "#161616",
                    }
                }
            ),
            encoding="utf-8",
        )
        self.mapping.write_text(json.dumps([1, 1, 1, 4]), encoding="utf-8")

    def tearDown(self):
        component_module.FFCONFIG_PATH = self._old_ffconfig
        component_module.FILE_MAPPING_PATH = self._old_mapping
        component_module.IFS_METADATA_STORE_PATH = self._old_store
        self._tmp.cleanup()

    def make_live_component(self, print_state="standby"):
        api = backend_tests.FakeKlippyAPIs(
            objects=["ad5x_ifs", backend_tests.HEAD],
            initial=backend_tests.live_initial(print_state=print_state, head=True),
        )
        server = backend_tests.FakeServer(api)
        component = component_module.load_component(backend_tests.FakeConfig(server))
        asyncio.run(server.handlers["server:klippy_ready"]())
        return component, server, api

    @staticmethod
    def slot(module, number):
        return next(item for item in module["slots"] if item["slot"] == number)

    def test_rich_manual_metadata_is_persisted_and_overlays_legacy_fields(self):
        component, _server, api = self.make_live_component()
        result = asyncio.run(
            component._handle_ifs_metadata(
                MetadataRequest(
                    slot=3,
                    spool={
                        "brand": " ERYONE ",
                        "series": "Silk",
                        "name": "Triple Color",
                        "material": "PLA+",
                        "variant": "Fast",
                        "remaining_g": 712.5,
                    },
                    appearance={
                        "color_mode": "tricolor",
                        "colors": ["#f330f9", "#27c4f4", "#ffd43b"],
                        "finish": "silk",
                    },
                )
            )
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "updated")
        self.assertEqual(api.gcodes, [])

        payload = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "1.0")
        saved = payload["slots"]["3"]
        self.assertEqual(saved["spool"]["source"], "manual")
        self.assertEqual(saved["spool"]["brand"], "ERYONE")
        self.assertEqual(saved["appearance"]["color_mode"], "tricolor")
        self.assertEqual(
            saved["appearance"]["colors"],
            ["#F330F9", "#27C4F4", "#FFD43B"],
        )
        self.assertEqual(stat.S_IMODE(self.store.stat().st_mode), 0o644)
        self.assertEqual(list(self.store.parent.glob(".ifs_metadata.json.tmp.*")), [])

        module = result["snapshot"]["modules"]["ifs"]
        slot3 = self.slot(module, 3)
        self.assertEqual(slot3["spool"]["source"], "manual")
        self.assertEqual(slot3["spool"]["material"], "PLA+")
        self.assertEqual(slot3["appearance"]["finish"], "silk")
        self.assertEqual(slot3["material"], "PLA+")
        self.assertEqual(slot3["color"], "#F330F9")
        self.assertEqual(module["metadata_store"]["status"], "ok")
        self.assertTrue(module["capabilities"]["integrations"]["manual_store"])

    def test_clear_restores_flashforge_fallback_without_touching_hardware(self):
        component, _server, api = self.make_live_component()
        asyncio.run(
            component._handle_ifs_metadata(
                MetadataRequest(
                    slot=2,
                    spool={"brand": "Kingroon", "material": "ABS"},
                    appearance={"colors": ["#123456"], "finish": "matte"},
                )
            )
        )
        result = asyncio.run(
            component._handle_ifs_metadata(MetadataRequest(slot=2, clear=True))
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"], "cleared")
        self.assertEqual(api.gcodes, [])
        payload = json.loads(self.store.read_text(encoding="utf-8"))
        self.assertNotIn("2", payload["slots"])

        slot2 = self.slot(result["snapshot"]["modules"]["ifs"], 2)
        self.assertEqual(slot2["spool"]["source"], "flashforge")
        self.assertEqual(slot2["material"], "PLA")
        self.assertEqual(slot2["color"], "#161616")

    def test_corrupt_store_fails_closed_and_is_not_overwritten(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        original = "{this is not json\n"
        self.store.write_text(original, encoding="utf-8")
        component, _server, api = self.make_live_component()
        result = asyncio.run(
            component._handle_ifs_metadata(
                MetadataRequest(
                    slot=1,
                    spool={"brand": "Nope", "material": "PLA"},
                    appearance={"colors": ["#FFFFFF"]},
                )
            )
        )
        self.assertFalse(result["ok"])
        self.assertIn("invalid", result["error"])
        self.assertEqual(self.store.read_text(encoding="utf-8"), original)
        self.assertEqual(api.gcodes, [])

    def test_finish_only_metadata_on_empty_slot_is_stale_not_present(self):
        component, _server, _api = self.make_live_component()
        result = asyncio.run(
            component._handle_ifs_metadata(
                MetadataRequest(
                    slot=4,
                    spool={},
                    appearance={"finish": "silk"},
                )
            )
        )
        self.assertTrue(result["ok"])
        slot4 = self.slot(result["snapshot"]["modules"]["ifs"], 4)
        self.assertFalse(slot4["present"])
        self.assertEqual(slot4["metadata_status"], "stale")
        self.assertEqual(slot4["appearance"]["finish"], "silk")
        self.assertFalse(slot4["permissions"]["load_slot"])

    def test_metadata_edit_is_non_mechanical_and_allowed_while_printing(self):
        component, _server, api = self.make_live_component(print_state="printing")
        result = asyncio.run(
            component._handle_ifs_metadata(
                MetadataRequest(
                    slot=1,
                    spool={"name": "Active print spool", "material": "PETG"},
                    appearance={"colors": ["#101010"]},
                )
            )
        )
        self.assertTrue(result["ok"])
        self.assertEqual(api.gcodes, [])
        module = result["snapshot"]["modules"]["ifs"]
        self.assertEqual(module["write_blocked_reason"], "unsafe_print_state")
        self.assertEqual(self.slot(module, 1)["spool"]["name"], "Active print spool")

    def test_empty_assignment_is_rejected_instead_of_creating_noise(self):
        component, _server, _api = self.make_live_component()
        result = asyncio.run(
            component._handle_ifs_metadata(
                MetadataRequest(slot=1, spool={}, appearance={})
            )
        )
        self.assertFalse(result["ok"])
        self.assertIn("empty", result["error"])
        self.assertFalse(self.store.exists())

    def test_invalid_store_structure_is_reported_by_snapshot_without_breaking_ifs(self):
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(
            json.dumps({"schema_version": "99", "slots": {}}),
            encoding="utf-8",
        )
        component, _server, _api = self.make_live_component()
        snapshot = asyncio.run(component._handle_snapshot(None))
        module = snapshot["modules"]["ifs"]
        self.assertTrue(module["available"])
        self.assertEqual(module["metadata_store"]["status"], "invalid")
        self.assertEqual(module["metadata_store"]["error"], "unsupported_schema")
        self.assertEqual(self.slot(module, 1)["spool"]["source"], "flashforge")


if __name__ == "__main__":
    unittest.main()
