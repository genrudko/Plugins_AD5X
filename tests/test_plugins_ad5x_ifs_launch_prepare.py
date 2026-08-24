from __future__ import annotations
import asyncio, unittest
from tests import test_plugins_ad5x_ifs_backend as backend
from tests import test_plugins_ad5x_ifs_job_preview as preview_tests
from tests import test_plugins_ad5x_ifs_launch_contract as launch_tests
component_module=backend.component_module; model=launch_tests.model; PREVIEW=preview_tests.PREVIEW

class PrepareRequest:
    def __init__(self, filename, preview_token, draft_token, mapping, leveling=1):
        self.params={"filename":filename,"preview_token":preview_token,"draft_token":draft_token,"resolved_tool_map":mapping,"leveling":leveling}
    def get_str(self,name): return str(self.params[name])
    def get(self,name,default=None): return self.params.get(name,default)

def tokens(preview=PREVIEW,mapping=(3,1)):
    token=model.build_job_preview_token(preview)
    draft=model.build_job_mapping_draft(preview,list(mapping),expected_preview_token=token)
    return token,draft["draft_token"]

class IFSLaunchPrepareTests(unittest.TestCase):
    def make_component(self,preview=PREVIEW,print_state="standby"):
        api=backend.FakeKlippyAPIs(objects=["ad5x_ifs",backend.HEAD],initial=backend.live_initial(print_state=print_state,head=True))
        server=backend.FakeServer(api); component=component_module.load_component(backend.FakeConfig(server))
        asyncio.run(server.handlers["server:klippy_ready"]())
        payload=dict(backend.READY); payload["job_preview"]=preview; api.query_result={"ad5x_ifs":payload}
        return component,server,api

    def test_prepare_revalidates_fresh_preview_without_print_zcolor(self):
        component,server,api=self.make_component(); pt,dt=tokens()
        result=asyncio.run(component._handle_ifs_job_launch_prepare(PrepareRequest(PREVIEW["filename"],pt,dt,[3,1],1)))
        self.assertTrue(result["ok"]); self.assertTrue(result["revalidated"])
        self.assertTrue(result["launch_gate"]["candidate"]); self.assertTrue(result["launch_gate"]["provider_launch_plan"]["ready"])
        self.assertFalse(result["launch_gate"]["hardware_acceptance"]["accepted"])
        self.assertEqual(api.gcodes,['ADIFS_JOB_PREVIEW FILENAME="3mf/model/demo/Metadata/plate_1.gcode"'])
        self.assertFalse(any("PRINT_ZCOLOR" in c for c in api.gcodes)); self.assertIn(component_module.IFS_JOB_LAUNCH_PREPARE_ENDPOINT,server.endpoints)

    def test_prepare_rejects_stale_preview_after_rescan(self):
        changed=dict(PREVIEW); changed["requirements"]=[dict(x) for x in PREVIEW["requirements"]]; changed["requirements"][0]["color"]="#FFFFFF"
        component,_server,api=self.make_component(changed); pt,dt=tokens()
        result=asyncio.run(component._handle_ifs_job_launch_prepare(PrepareRequest(PREVIEW["filename"],pt,dt,[3,1])))
        self.assertFalse(result["ok"]); self.assertTrue(result["revalidated"]); self.assertIn("stale_preview",result["mapping_draft"]["blockers"]); self.assertEqual(len(api.gcodes),1)
    def test_prepare_rejects_stale_draft_token_without_print(self):
        component,_server,api=self.make_component(); pt,_=tokens()
        result=asyncio.run(component._handle_ifs_job_launch_prepare(PrepareRequest(PREVIEW["filename"],pt,"0"*64,[3,1])))
        self.assertFalse(result["ok"]); self.assertEqual(result["error"],"stale_draft"); self.assertIn("stale_draft",result["mapping_draft"]["blockers"])
        self.assertFalse(any("PRINT_ZCOLOR" in c for c in api.gcodes))

    def test_prepare_is_blocked_while_printing_before_preview_command(self):
        component,_server,api=self.make_component(print_state="printing"); pt,dt=tokens()
        result=asyncio.run(component._handle_ifs_job_launch_prepare(PrepareRequest(PREVIEW["filename"],pt,dt,[3,1])))
        self.assertFalse(result["ok"]); self.assertFalse(result["revalidated"]); self.assertEqual(api.gcodes,[])

    def test_capability_advertises_prepare_without_start(self):
        caps=model.get_ifs_capabilities()["actions"]; self.assertTrue(caps["prepare_job_launch"]); self.assertFalse(caps["start_job"])

if __name__=="__main__": unittest.main()
