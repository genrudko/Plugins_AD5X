from __future__ import annotations

import asyncio
import unittest

from tests import test_plugins_ad5x_ifs_backend as backend_tests
from tests import test_plugins_ad5x_ifs_launch_contract as launch_tests

component_module = backend_tests.component_module
model = launch_tests.model


class MappingDraftRequest:
    def __init__(self, preview_token, resolved_tool_map, leveling=None):
        self.params = {"preview_token": preview_token, "resolved_tool_map": resolved_tool_map}
        if leveling is not None:
            self.params["leveling"] = leveling
    def get_str(self, name):
        return str(self.params[name])
    def get(self, name, default=None):
        return self.params.get(name, default)


class IFSMappingDraftTests(unittest.TestCase):
    def make_live_component(self):
        initial = backend_tests.live_initial()
        raw = dict(initial["ad5x_ifs"])
        raw["job_preview"] = launch_tests.preview()
        initial["ad5x_ifs"] = raw
        api = backend_tests.FakeKlippyAPIs(objects=["ad5x_ifs", backend_tests.HEAD], initial=initial)
        server = backend_tests.FakeServer(api)
        component = component_module.load_component(backend_tests.FakeConfig(server))
        asyncio.run(server.handlers["server:klippy_ready"]())
        return component, server, api

    def test_draft_binds_complete_manual_map_to_exact_preview(self):
        preview = launch_tests.preview()
        token = model.build_job_preview_token(preview)
        draft = model.build_job_mapping_draft(preview, [2, 1], token)
        self.assertEqual(draft["status"], "ready")
        self.assertRegex(draft["draft_token"], r"^[0-9a-f]{64}$")
        self.assertTrue(draft["modified"])
        self.assertEqual(draft["provider_resolved_tool_map"], [3, 1])
        self.assertEqual(draft["assignments"], [{"tool": 0, "slot": 2}, {"tool": 1, "slot": 1}])

    def test_stale_or_invalid_draft_fails_closed(self):
        preview = launch_tests.preview()
        stale = model.build_job_mapping_draft(preview, [2, 1], "0" * 64)
        self.assertIn("stale_preview", stale["blockers"])
        for mapping in ([2], [2, 9], [True, 1], "2,1"):
            with self.subTest(mapping=mapping):
                draft = model.build_job_mapping_draft(preview, mapping)
                self.assertEqual(draft["status"], "blocked")
                self.assertIn("invalid_resolved_tool_map", draft["blockers"])
                self.assertEqual(draft["draft_token"], "")

    def test_manual_duplicate_is_explicit_but_not_rejected(self):
        preview = launch_tests.preview()
        token = model.build_job_preview_token(preview)
        draft = model.build_job_mapping_draft(preview, [1, 1], token)
        self.assertEqual(draft["status"], "ready")
        self.assertIn("manual_duplicate_slot", draft["warnings"])

    def test_empty_physical_slot_blocks_launch_candidate(self):
        component, _server, api = self.make_live_component()
        preview = component.get_snapshot()["modules"]["ifs"]["job_preview"]
        result = asyncio.run(component._handle_ifs_job_mapping_draft(MappingDraftRequest(model.build_job_preview_token(preview), [4, 1])))
        self.assertTrue(result["ok"])
        self.assertIn("assigned_slot_empty", result["launch_gate"]["blockers"])
        self.assertFalse(result["launch_gate"]["candidate"])
        self.assertFalse(result["launch_gate"]["write_enabled"])
        self.assertEqual(api.gcodes, [])

    def test_capabilities_keep_apply_and_start_disabled(self):
        caps = model.get_ifs_capabilities()
        self.assertTrue(caps["mapping"]["draft_preprint_mapping"])
        self.assertFalse(caps["mapping"]["apply_preprint_mapping"])
        self.assertFalse(caps["actions"]["start_job"])

    def test_endpoint_is_registered_read_only_and_uses_manual_map(self):
        component, server, api = self.make_live_component()
        self.assertIn(component_module.IFS_JOB_MAPPING_DRAFT_ENDPOINT, server.endpoints)
        preview = component.get_snapshot()["modules"]["ifs"]["job_preview"]
        result = asyncio.run(component._handle_ifs_job_mapping_draft(MappingDraftRequest(model.build_job_preview_token(preview), [2, 1])))
        self.assertTrue(result["ok"])
        self.assertEqual(result["mapping_draft"]["resolved_tool_map"], [2, 1])
        self.assertEqual(result["preprint_plan"]["rows"][0]["assignment"]["slot"], 2)
        self.assertTrue(result["launch_gate"]["candidate"])
        self.assertFalse(result["launch_gate"]["write_enabled"])
        self.assertEqual(result["launch_gate"]["mapping_source"], "manual")
        provider_plan = result["launch_gate"]["provider_launch_plan"]
        self.assertEqual(provider_plan["parameters"]["T0"], 2)
        self.assertEqual(provider_plan["parameters"]["T1"], 1)
        self.assertEqual(provider_plan["missing_parameters"], ["LEVELING"])
        self.assertFalse(provider_plan["execution_enabled"])
        self.assertEqual(api.gcodes, [])

    def test_draft_can_materialize_inert_provider_plan_with_explicit_leveling(self):
        component, _server, api = self.make_live_component()
        preview = component.get_snapshot()["modules"]["ifs"]["job_preview"]
        token = model.build_job_preview_token(preview)
        result = asyncio.run(component._handle_ifs_job_mapping_draft(MappingDraftRequest(token, [2, 1], leveling=1)))
        provider_plan = result["launch_gate"]["provider_launch_plan"]
        self.assertTrue(result["ok"])
        self.assertTrue(provider_plan["ready"])
        self.assertEqual(provider_plan["parameters"]["LEVELING"], 1)
        self.assertFalse(provider_plan["execution_enabled"])
        self.assertEqual(api.gcodes, [])

    def test_invalid_explicit_leveling_blocks_launch_candidate_without_gcode(self):
        component, _server, api = self.make_live_component()
        preview = component.get_snapshot()["modules"]["ifs"]["job_preview"]
        token = model.build_job_preview_token(preview)
        result = asyncio.run(component._handle_ifs_job_mapping_draft(MappingDraftRequest(token, [2, 1], leveling=2)))
        self.assertTrue(result["ok"])
        self.assertFalse(result["launch_gate"]["candidate"])
        self.assertIn("invalid_leveling", result["launch_gate"]["blockers"])
        self.assertFalse(result["launch_gate"]["provider_launch_plan"]["ready"])
        self.assertEqual(api.gcodes, [])

    def test_endpoint_rejects_stale_preview_without_gcode(self):
        component, _server, api = self.make_live_component()
        result = asyncio.run(component._handle_ifs_job_mapping_draft(MappingDraftRequest("0" * 64, [2, 1])))
        self.assertFalse(result["ok"])
        self.assertIn("stale_preview", result["mapping_draft"]["blockers"])
        self.assertEqual(api.gcodes, [])


if __name__ == "__main__":
    unittest.main()
