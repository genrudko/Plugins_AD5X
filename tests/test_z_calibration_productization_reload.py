from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRODUCTIZER_PATH = ROOT / "installer" / "z_calibration_productization.py"
POLICY_PATH = ROOT / "z_calibration_rc_policy.cfg"

_spec = importlib.util.spec_from_file_location("zcal_productization_reload", PRODUCTIZER_PATH)
assert _spec and _spec.loader
product = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(product)


def hook_bytes(commands: list[str]) -> bytes:
    return (
        "[gcode_macro _USER_START_PRINT]\n"
        "gcode:\n"
        + "".join(f"    {command}\n" for command in commands)
    ).encode("utf-8")


def live_payload(
    commands: list[str],
    *,
    mesh_test: int,
    cc_enabled: int,
    policy_loaded: bool,
) -> str:
    status = {
        "configfile": {
            "settings": {
                "gcode_macro _user_start_print": {
                    "gcode": "\n".join(commands),
                }
            }
        },
        "save_variables": {
            "variables": {
                "mesh_test": mesh_test,
                "cc_enabled": cc_enabled,
                "load_zoffset": 1,
                "print_leveling": 0,
            }
        },
    }
    if policy_loaded:
        status["gcode_macro _AD5X_Z_SAVED_CHECK_POLICY"] = {
            "policy_id": product.POLICY_ID,
            "max_auto_alignment": product.POLICY_MAX_AUTO,
        }
    return json.dumps({"result": {"status": status}})


class ZCalibrationReloadLifecycleTests(unittest.TestCase):
    def make_applied(self, root: Path):
        owner = root / "user.cfg"
        original = hook_bytes([product.CC])
        owner.write_bytes(original)
        variables = root / "variables.cfg"
        variables.write_text(
            "[Variables]\nmesh_test = 2\ncc_enabled = 1\nother = 9\n",
            encoding="utf-8",
        )
        policy_source = root / "policy-source.cfg"
        policy_source.write_bytes(POLICY_PATH.read_bytes())
        policy_dest = root / "generated" / "zcal_owner_rc.cfg"
        state = root / "state" / "zcal-rc-productization"
        plan = {
            "schema": 1,
            "owner_path": str(owner),
            "state_dir": str(state),
            "variables_file": str(variables),
            "policy_dest": str(policy_dest),
            "baseline_source": "current",
            "original_hook_b64": base64.b64encode(original).decode("ascii"),
            "original_mesh_test": {"present": True, "value": 2},
            "original_cc_enabled": {"present": True, "value": 1},
            "policy_original_present": False,
            "policy_original_b64": "",
        }
        product.apply_plan(plan, policy_source)
        return owner, variables, policy_dest, state

    def test_uninstall_keeps_provenance_until_post_reload_verification(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            owner, variables, policy_dest, state = self.make_applied(Path(td))
            product.uninstall(state, variables, keep_state=True)

            self.assertEqual(product.hook_commands(owner), [product.CC])
            self.assertFalse(policy_dest.exists())
            self.assertTrue((state / "manifest.json").is_file())

            product.verify_uninstalled(
                live_payload(
                    [product.CC],
                    mesh_test=2,
                    cc_enabled=1,
                    policy_loaded=False,
                ),
                state,
            )
            product.finalize_uninstall(state)
            self.assertFalse(state.exists())

    def test_uninstall_verifier_rejects_stale_policy_after_disk_restore(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, variables, _, state = self.make_applied(Path(td))
            product.uninstall(state, variables, keep_state=True)
            with self.assertRaisesRegex(product.ProductizationError, "policy macro still loaded"):
                product.verify_uninstalled(
                    live_payload(
                        [product.CC],
                        mesh_test=2,
                        cc_enabled=1,
                        policy_loaded=True,
                    ),
                    state,
                )
            self.assertTrue(state.exists())

    def test_uninstall_verifier_rejects_wrong_restored_saved_variables(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            _, variables, _, state = self.make_applied(Path(td))
            product.uninstall(state, variables, keep_state=True)
            with self.assertRaisesRegex(product.ProductizationError, "mesh_test value"):
                product.verify_uninstalled(
                    live_payload(
                        [product.CC],
                        mesh_test=3,
                        cc_enabled=1,
                        policy_loaded=False,
                    ),
                    state,
                )
            self.assertTrue(state.exists())


if __name__ == "__main__":
    unittest.main()
