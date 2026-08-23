from __future__ import annotations

import asyncio
import unittest

from tests import test_plugins_ad5x_ifs_backend as backend_tests
from tests import test_plugins_ad5x_ifs_launch_contract as launch_tests


component_module = backend_tests.component_module


class JobPreviewRequest:
    def __init__(self, filename):
        self.filename = filename

    def get_str(self, name):
        if name != "filename":
            raise KeyError(name)
        return self.filename


PREVIEW = {
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
        "material_failure": False,
        "color_failure": False,
        "weak_color": False,
        "duplicate_slot": False,
    },
    "messages": [],
    "error": "",
}


class IFSJobPreviewBackendTests(unittest.TestCase):
    def make_live_component(self, print_state="standby"):
        api = backend_tests.FakeKlippyAPIs(
            objects=["ad5x_ifs", backend_tests.HEAD],
            initial=backend_tests.live_initial(print_state=print_state, head=True),
        )
        server = backend_tests.FakeServer(api)
        component = component_module.load_component(backend_tests.FakeConfig(server))
        asyncio.run(server.handlers["server:klippy_ready"]())
        return component, server, api

    def test_preview_endpoint_delegates_to_bridge_command_and_refreshes_object(self):
        component, _server, api = self.make_live_component()
        payload = dict(backend_tests.READY)
        payload["job_preview"] = PREVIEW
        api.query_result = {"ad5x_ifs": payload}

        result = asyncio.run(
            component._handle_ifs_job_preview(JobPreviewRequest(PREVIEW["filename"]))
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["job_preview"], PREVIEW)
        self.assertEqual(result["preview_token"], launch_tests.model.build_job_preview_token(PREVIEW))
        self.assertRegex(result["preview_token"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            api.gcodes,
            [
                'ADIFS_JOB_PREVIEW FILENAME="3mf/model/demo/Metadata/plate_1.gcode"'
            ],
        )
        snapshot_preview = result["snapshot"]["modules"]["ifs"]["job_preview"]
        self.assertEqual(snapshot_preview, PREVIEW)

    def test_preview_is_blocked_while_printing_before_klipper_command(self):
        component, _server, api = self.make_live_component(print_state="printing")
        result = asyncio.run(
            component._handle_ifs_job_preview(JobPreviewRequest("demo.gcode"))
        )
        self.assertFalse(result["ok"])
        self.assertIn("printing", result["error"])
        self.assertEqual(api.gcodes, [])

    def test_preview_rejects_path_escape_and_gcode_quote_injection(self):
        for filename in ("../printer.cfg", '/usr/data/config/printer.cfg', 'bad" FILE=evil'):
            with self.subTest(filename=filename):
                component, _server, api = self.make_live_component()
                result = asyncio.run(
                    component._handle_ifs_job_preview(JobPreviewRequest(filename))
                )
                self.assertFalse(result["ok"])
                self.assertEqual(api.gcodes, [])

    def test_preview_rejects_unavailable_bridge_result(self):
        component, _server, api = self.make_live_component()
        payload = dict(backend_tests.READY)
        payload["job_preview"] = {
            "available": False,
            "source": "zmod",
            "filename": "demo.gcode",
            "requirements": [],
            "assignments": [],
            "auto_assign": {},
            "messages": [],
            "error": "zmod_color_unavailable",
        }
        api.query_result = {"ad5x_ifs": payload}

        result = asyncio.run(
            component._handle_ifs_job_preview(JobPreviewRequest("demo.gcode"))
        )
        self.assertFalse(result["ok"])
        self.assertIn("zmod_color_unavailable", result["error"])
        self.assertEqual(api.gcodes, ['ADIFS_JOB_PREVIEW FILENAME="demo.gcode"'])

    def test_capability_advertises_source_delegated_slicer_preview(self):
        component, _server, _api = self.make_live_component()
        module = component.get_snapshot()["modules"]["ifs"]
        caps = module["capabilities"]
        self.assertTrue(caps["actions"]["preview_job"])
        self.assertTrue(caps["integrations"]["slicer"])
        self.assertTrue(caps["mapping"]["preprint_preview"])
        self.assertFalse(caps["mapping"]["apply_preprint_mapping"])


if __name__ == "__main__":
    unittest.main()
